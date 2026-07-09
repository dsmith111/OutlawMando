# The helmet-resize experiment: DirectStorage, Oodle, and an honest dead-end

Goal: shrink the oversized Boba helmet ~15% toward Din Djarin proportions. This is the story of
why that turned into a deep dive into Snowdrop's streaming pipeline, what got unlocked, and why
the resize itself is blocked.

## 1. Loose meshes are ignored
A loose `.mmb` mesh override placed at the correct `helix/…` path loads but has **no effect** —
the helmet stays the same size. Materials served fine the same way; meshes did not.

## 2. Why: DirectStorage — and it ships *disabled*
`dstorage.dll` is present in the game folder, so meshes/textures stream through **DirectStorage**,
which reads the `.sdfdata` archives by offset and never touches the modloader's `CreateFile` hook.

But there's a twist: the game ships only the DirectStorage **stub** (`dstorage.dll`, ~198 KB) and
**not** its implementation (`dstoragecore.dll`). So `DStorageGetFactory` returns `E_NOTIMPL` and
the game silently falls back to plain file I/O. **DirectStorage is dormant in a stock install.**

## 3. What got built (and works)
- A **`dstorage.dll` proxy** ([`../loader/`](../loader/)) that forwards the real DirectStorage
  calls and **wraps the factory → queue → `EnqueueRequest`**, logging every streamed read. It
  coexists with `version.dll` (different proxy target). ABI mirrored from the real DirectStorage
  1.2.3 header, `static_assert`-verified.
- **Re-enabling DirectStorage** by supplying a matching `dstoragecore.dll` (the game's 2305
  stub happily uses the stock 1.2.3 core). Verified with a test harness: factory returns `S_OK`.
- With the core present, the proxy captured **~84k reads** — DirectStorage interception works.
- A full **Oodle toolchain**: decode via `ooz` (validated on test data) and **encode** via real
  Oodle (`oo2core_8_win64.dll`, e.g. from another game). Our scaled helmet re-compresses with
  Kraken and round-trips perfectly.

All of that is a genuinely novel capability for this game — the foundation for texture mods and
for swapping any mesh whose format is known.

Cross-compiled from Linux with **zig** (`pip install ziglang`, no sudo, no MSVC):
`zig c++ -target x86_64-windows-gnu -shared`. Windows test exes were run via WSL interop.

## 4. Why the resize is still blocked
The reads are all `comp=0` (raw 128 KB pages); the game Oodle-decompresses internally. Tracing
the actual helmet reads showed the rendered mesh is an **uncompressed, compact, quantized mesh**
in `sdf-A-0081` — a pack of low-poly "proxy" headwear meshes the game reads at every camera
distance (confirmed with a nearest-camera capture: no higher-detail `.mmb` LOD ever streamed in).

That compact format is **proprietary and undocumented**: the name is length-prefixed, followed by
tagged sub-fields, then quantized position data interleaved with bone/index data — with no clean
vertex-array delimiter and no mesh-level bounding box to scale. It is **not** the `.mmb` format the
standalone extractor emits (only the name string matches, then it diverges). Scaling it blindly
would corrupt neighboring data and crash. The blocker is **format knowledge**, not delivery
(we can write to it) — and the converter that produces the `.mmb` (DTZxPorter's Hunter) is closed
source, so there's no spec to work from.

**Conclusion: helmet resize is closed** pending the compact-mesh format spec.

## 5. A conflict worth knowing
**Enabling DirectStorage breaks loose-material mods.** Once `dstoragecore.dll` is present, the
game streams *materials* through DirectStorage too, bypassing `version.dll`'s hook — so a loose
`.mmaterial` color mod stops applying. If you ever re-enable DirectStorage for a mesh/texture mod,
the proxy must **also** substitute the material reads, or your colors revert. For the shipped
color mod, DirectStorage is left in its stock (disabled) state.

## 6. If someone picks this up later
The tractable next step is the compact-mesh format spec — most realistically from reverse-
engineering the importer that already reads it, not from raw bytes. With the format known, the
rest is ready: decode the block (`ooz`/Oodle), scale the vertices, re-encode (`oo2core`), and
substitute at read time with the proxy (`../loader/`).
