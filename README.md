# OutlawMando — Mandalorian Beskar recolor + a Snowdrop/DirectStorage mod toolkit

Turn the "Play as Boba Fett" mod for **Star Wars Outlaws** (Snowdrop engine) into clean,
screen-accurate **Mandalorian beskar** — cool silver armor instead of Boba's dark weathered
green/red metal — and, along the way, a reusable toolkit for reverse-engineering and modding
Snowdrop's file formats on Linux.

> **Status:** The color mod is finished and shippable (see [`mod-src/`](mod-src/) and the
> `nexus/` bundles). A helmet-resize experiment led deep into Snowdrop's asset pipeline and
> uncovered a genuinely novel capability (re-enabling + intercepting DirectStorage), but the
> resize itself is **blocked** by an undocumented mesh format — documented honestly in
> [`docs/HELMET-RESIZE.md`](docs/HELMET-RESIZE.md).

## What's here

| Path | What it is |
|------|------------|
| [`mod-src/`](mod-src/) | The beskar recolor — final `.mmaterial` overrides (main + two optional tones) and how they were made |
| [`tools/`](tools/) | Python tools to parse/edit Snowdrop formats natively on Linux (no Windows GUI extractor needed) |
| [`loader/`](loader/) | A `dstorage.dll` proxy that **re-enables and intercepts DirectStorage** — experimental research, not shipped |
| [`docs/`](docs/) | The reverse-engineering write-ups (formats, the DirectStorage discovery, the helmet dead-end) |
| [`scripts/`](scripts/) | Dev deploy/restore helpers (example paths — edit for your install) |

The packaged, upload-ready mod archives live in `../nexus/` (outside this repo); proprietary
binaries and ripped game assets live in `../local/` and are intentionally **not** committed.

## The mod (short version)

The metal armor pieces use a layered Snowdrop material. Boba's look comes from a paint layer
(green/red/orange) over a bare metal base plus baked rust/dirt. The recolor:

- neutralizes the paint-layer colors and the rust/dirt/stain *colors* to a cool silver,
- lifts the dark base tint (`L1 Color Overlay`) to a bright cool-silver,
- leaves cloth/leather pieces untouched.

All edits are **same-length, in-place float edits** to the material constants — the only kind
that is safe (changing a material file's byte length crashes the game on character load, and
enabling the paint layer or editing weathering *scalars* also crashes). Base roughness/metalness
aren't stored as editable constants, so a true mirror shine isn't reachable via constants — the
result is a clean, cool gunmetal-silver, matte-metallic under reflective light.

Three tones are provided: **main** (cool silver), **gunmetal** (deeper/contrasty), **steel**
(lighter). See [`mod-src/README.md`](mod-src/README.md).

## Requirements / install

- **Star Wars Outlaws** (PC).
- The **Universal Snowdrop Modloader** (`version.dll`).
- The base **"Play as Boba Fett"** mod (this is a *recolor add-on* — it overrides that mod's
  material files; it does not add the Boba appearance itself).

Install with a mod manager, or drop the bundle's `helix/` folder into the game root so the
files land at `…/Star Wars Outlaws/helix/materials/`. See each bundle's `README.txt`.

## The toolkit

Everything needed to inspect and edit Snowdrop `.mmaterial` files was reverse-engineered and
reimplemented in Python (see [`docs/FINDINGS.md`](docs/FINDINGS.md)):

- `tools/bv2.py` — parse/rebuild `\xffBV2` containers (`.mmaterial`, `.mgraphobject`) byte-exact.
- `tools/matconst.py` — read/write named material constants (colors, roughness, etc.).
- `tools/make_tone.py` — generate a beskar tone variant from vanilla materials (proven-safe edits only).
- `tools/berg.py`, `tools/find_assets.py` — walk the `BERG` `.sdfdata` archives and locate assets.
- `tools/mmb_core.py`, `tools/scale_helmet.py` — parse/scale `.mmb` skeletal meshes (see the helmet doc).

## License

MIT for the original code here (tools, loader). Third-party/other:
- `loader/sdk/dstorage.h`, `dstorageerr.h` are Microsoft's DirectStorage headers (MIT).
- The `ooz` Oodle *decompressor* (used during research) and Oodle itself (`oo2core_*.dll`,
  needed for *re-encoding*) are **not included** and are not MIT — obtain them separately.
- `.mmaterial` files are derived from Star Wars Outlaws assets (Ubisoft). Provided for
  interoperability/modding; all game IP belongs to Ubisoft.

See [`LICENSE`](LICENSE).
