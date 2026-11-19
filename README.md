# OutlawMando — Mandalorian Beskar for Star Wars Outlaws, plus a Snowdrop modding toolkit

An add-on for the **"Play as Boba Fett"** mod for **Star Wars Outlaws** (Snowdrop engine) that turns
the outfit into Din Djarin, and the Linux-side toolkit built to make it.

- **v2.x (current):** a full Din Djarin character model replaces the Boba Fett geometry. The model
  is cut into the outfit's gear pieces, refitted to the game skeleton, re-skinned and re-textured,
  and given a cloth-simulated back cape. See [`docs/DIN-SWAP.md`](docs/DIN-SWAP.md) and
  [`tools/din_swap/`](tools/din_swap/).
- **v1.x (older):** a material reskin of the Boba outfit (chrome beskar plus a reshaped helmet).
  The record is in [`docs/HELMET-RESIZE.md`](docs/HELMET-RESIZE.md) and [`docs/FINDINGS.md`](docs/FINDINGS.md).

No game files, model files or packaged builds are in this repo. The tools read them from a
private workspace folder next to the repo (see [`docs/DIN-SWAP.md`](docs/DIN-SWAP.md)).

## What's here

| Path | What it is |
|------|------------|
| [`tools/din_swap/`](tools/din_swap/) | The v2 pipeline: model → game meshes, textures, materials, borrowed cloth cape; deploy/revert; validation |
| [`tools/`](tools/) | Format tools: `bv2.py` (`.mmaterial`/`.mgraphobject` containers), `matconst.py` (material constants), `alias_string.py` (same-length texture path aliasing), `mmb_core.py` (`.mmb` meshes), `berg.py`/`find_assets.py` (`.sdfdata` archives), `force_lod0.py`, `scale_helmet.py` and others |
| [`scripts/build_din_package.sh`](scripts/build_din_package.sh) | Builds and checks the release archive |
| [`loader/`](loader/) | A `dstorage.dll` proxy that re-enables and intercepts DirectStorage. Research only, not used by the mod |
| [`docs/`](docs/) | Reverse-engineering notes |

## Requirements to play

- Star Wars Outlaws (PC).
- **Raindrop** (DTZxPorter's `dinput8.dll` loader). It is the loader that serves loose meshes,
  textures and cloth files. The `version.dll` "Universal Snowdrop Modloader" does not.
- "Play as Boba Fett" and its requirements ("Hide Kay's Accessories", "Hide Kay's Clothes").

The release archive is `helix/` plus `README.txt`; install it over the Boba mod.

## Lessons that cost a release

- **An override on a vanilla path changes every character that loads that path.** v1.2 and v2.0
  hid the player's bare head with a 0-byte override of a generic head graph
  (`chr_head_2_silver_human_sea_m_001.mgraphobject`), and many NPCs lost their heads. Since 2.1 the
  head entry is removed from the player's own gear list (`character_visuals_player.mcharactervisuals`,
  plain text) instead. To hide or change a part of one character, edit that character's gear list.
- The borrowed cape still overrides the Canto Bight police cape's own files, so those NPCs share its
  colour and cloth settings.

## License

MIT for the original code here (tools, loader). Third-party:
- `loader/sdk/dstorage.h`, `dstorageerr.h` are Microsoft's DirectStorage headers (MIT).
- Oodle (`oo2core_*.dll`) and game binaries are not included and are not MIT.
- Star Wars Outlaws assets belong to Ubisoft; Star Wars / The Mandalorian are © Lucasfilm/Disney.
  None are included. The tools operate on files you export from your own copy of the game.

See [`LICENSE`](LICENSE).
