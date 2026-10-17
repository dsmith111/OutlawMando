# The helmet-resize experiment: DirectStorage, Oodle, and (finally) Raindrop

Goal: shrink the oversized Boba helmet toward Din Djarin proportions.

## RESOLVED — it works via Raindrop
The resize **works** using **Raindrop** (DTZxPorter's `dinput8.dll` loader), which — unlike the
Universal Snowdrop Modloader (`version.dll`) — *does* serve loose `.mmb` mesh overrides. The
whole DirectStorage/Oodle detour below was chasing the wrong loader. Working setup:
- Disable `version.dll`; install Raindrop `dinput8.dll` in the game root.
- Drop the scaled helmet `.mmb` (from `tools/scale_helmet.py`, now supporting per-axis
  `sx,sy,sz`) at its real path; Raindrop serves it, and it serves the recolor materials too.
- The helmet is same-length-edited, so no re-encoding/DirectStorage is needed at all.

Two follow-on fitment facts:
- The player head clips through a shrunk helmet. The head (`chr_head_2_silver_human_sea_m_001`,
  a per-outfit head swapped in by the visuals file) **can't be shrunk** — its `head_mesh` uses
  **PCA-compressed** positions. So it's **hidden** with a zero-byte `.mgraphobject` override
  (the same trick the base mod uses for gear). Leaves a tiny throat gap, normally collar-covered.
- Final shipped shape is a non-uniform scale (narrower width, near-full height/depth) — a
  Mando-ish silhouette rather than a uniform shrink.

### v1.2 packaging fix: bald head/nose clipping

The working game install contains this **zero-byte file**:
`helix/graph objects/gear/chr_head_2_silver_human_sea_m_001.mgraphobject`.
It hides the head by overriding its graph; merely omitting a loose head mesh does not hide
the head asset in the game's archives.

The shipped `MandalorianBeskar_v1.1.zip` omitted this override even though it included the
smaller helmet. All 43 assets in that archive match the working install byte-for-byte;
the head-hide graph is a separate, required override that the build script never copied.
This explains why the developer install worked while users saw the bald head and nose.

The v1.2 build explicitly generates the empty graph and checks that it is present and
exactly zero bytes. This is the only graph override the add-on ships; the base mod's
character visuals and other gear-hiding graphs remain dependencies. Keep empty files
when archiving or installing the mod.

Deleting `chr_headw_5_canon_boba_fett_helmet.mmb` removes the smaller Din helmet override
and lets the game fall back to Boba's larger helmet. That can mask the clipping, but loses
the custom shape. Install v1.2 over v1.1 to restore the helmet and add the missing graph.

Everything below is the (still interesting) record of the detour before Raindrop was found.

---

The rest of this doc is the story of why this first turned into a deep dive into Snowdrop's
streaming pipeline, what got unlocked, and why the *DirectStorage* route was blocked.

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
