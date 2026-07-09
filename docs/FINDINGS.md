# Snowdrop / Star Wars Outlaws — reverse-engineering notes

Everything below was found by direct inspection of a retail Outlaws install and is what the
tools in this repo are built on. It's enough to parse and edit materials natively on Linux
(no Windows GUI extractor required for editing).

## `.mmaterial` / `.mgraphobject` — the `BV2` container

- Magic `ff 42 56 32` (`\xffBV2`).
- Layout: `magic(4)` → opaque header (its length scales with the string count) →
  NUL-terminated, ordinal-indexed **string table** → tagged body.
- String references in the body are little-endian `u16` where `index = u16 >> 5` and
  `tag = u16 & 0x1F`. References are by **index**, not offset.
- **Editing rule that matters:** changing a material file's byte **length** crashes the game
  on character load (the header can't absorb a length change when treated as opaque). Only
  **same-length, in-place** edits are safe. `tools/bv2.py` round-trips byte-exact.

### Material constants
Each named constant is a small map record (tag `0x18` = 6 keys, `0x14` = 5 keys) plus a `0x1c`
delimiter. Float values are stored as runs of `0x03` + `float32` emitted **just before** the
constant's definition record; the run length matches the type (float=1, float2=2, float3=3,
float4=4). `tools/matconst.py` reads/writes these in place.

**Safe to edit** (proven in-game): `float3` color constants — `L1 Color Overlay`, `L2 Color`,
`Paint Color R/G/B`, `Rust Stains Color`, `Dirt Color` — and the `float2` `Paint Roughness BC`.
**Crashes:** enabling the paint layer (`Paint` 0→1), zeroing weathering *scalars*
(`*Amount`, `Scratch`, roughness-detail, mask-contrast…), and any length change.
**Not present / not editable:** `L2 Roughness`, `L2 Metalness` (engine defaults, unserialized)
— so base gloss/metalness can't be changed via constants.

## `BERG` archives — `sdf-A-*.sdfdata`

- Each archive starts `BERG` + `u32(0x2a)`, then **interleaves**: uncompressed `\xffBV2`
  objects (materials, graph objects, some meshes) and compressed data blocks.
- The index `sdf.sdftoc` is `WEST` magic and fully hashed (no plaintext paths).
- Bulk compression is **Oodle** (Kraken/Leviathan), statically linked in `Outlaws.exe`
  (no `oo2core` DLL ships with the game). Some data is zlib
  (`[sentinel u32=0xDABC02E3][typeA][typeB][usize][csize]` + zlib payload).
- `tools/berg.py` walks blocks; `tools/find_assets.py` scans all archives for keyword strings
  in raw + zlib content. This is how the Boba materials and mesh archives were located.

## `.mmb` skeletal meshes

Format (per AlexP0/SWOutlawsMeshTool): magic `MMB\x13`, version 19, bones → meshes → LODs.
LOD vertex data lives at `lod.data_offset`. `position_type 0` = 8-byte vertex
(`int16 xn,yn,zn` normalized /32767, then `int16 w` magnitude; world pos = `xn/32767*w`, …);
`position_type 1` = `float3`. `tools/mmb_core.py` is a headless port of that parser;
`tools/scale_helmet.py` uniformly scales a `.mmb` in place (same length).

**Important caveat:** this `.mmb` format is what the **standalone extractor** produces. The
game's *runtime* meshes inside the archives use a **different, compact, quantized format** — see
[`HELMET-RESIZE.md`](HELMET-RESIZE.md). Loose `.mmb` overrides are **ignored** by the game.

## Delivery / the modloader

- Mods are loose-file overrides placed under the game's `helix/` tree. The Universal Snowdrop
  Modloader (`version.dll`) hooks `CreateFile`/`OpenFileStream` and serves them.
- This works for **materials** but **not meshes/textures** in the default configuration —
  those can stream through DirectStorage, which bypasses the file hook (see the helmet doc).
