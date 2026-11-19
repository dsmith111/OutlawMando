# v2: Din Djarin model swap (`tools/din_swap/`)

Rebuilds every Boba gear mesh the player wears from a Din Djarin model, writes matching textures and
materials, and gives the cape slot a real cloth-simulated cape. Nothing touches the game until you
deploy, and every deploy can be reverted exactly.

## Workspace layout

The tools resolve paths relative to the folder this repo is checked out in (`<workspace>/repo`).
Everything outside `repo/` is private input or output and never goes into git:

```
<workspace>/
  repo/                        this repository
  downloaded_models/extracted/ the source model, glTF + original TGA textures
  local/mesh_edit/             helmet_ORIGINAL.mmb, helmet_v6_forcelod0.mmb (v1.2 helmet, fit reference)
  local/din_swap/containers/   vanilla game exports: Boba gear .mmb (vest, shirt, bracers, gloves, pants,
                               boots, belt, pouches, kneepads), the Stormtrooper helmet donor material,
                               cape/ (Canto Bight police cape .mmb/.mcloth/material, and the base mod's
                               character_visuals_player file as *.BASEMOD.mcharactervisuals)
  local/din_swap/staging/      build output (a helix/ tree)
  local/din_swap/deploy/       deploy manifest + backups
  dist/                        release packages
```

Game files are exported with DTZxPorter's Hunter. The source model is "Mandalorian Armored -
Fortnite" by Yxboireal on Sketchfab (CC-BY-4.0); a package built from it must carry that credit,
which `scripts/build_din_package.sh` writes into the release README.

Python 3 with numpy, scipy and Pillow. Blender (headless) only for the preview renders.

## Commands

```sh
tools/din_swap/build_all.sh                  # textures, meshes, materials, cape, then validation
python3 tools/din_swap/deploy_din.py --redeploy   # revert the previous deploy, deploy staging
python3 tools/din_swap/deploy_din.py --status     # compare game folder with staging
python3 tools/din_swap/deploy_din.py --revert     # put the game folder back
scripts/build_din_package.sh                 # release archive into <workspace>/dist/ (rebuilds cape + graphs with pinned settings)
```

The game root defaults to a Steam library path; set `OMTK_GAME_ROOT` to override it. Fully quit and
relaunch the game to see a change.

## What gets built

| Piece | How |
|-------|-----|
| Meshes | `build_din.py`: each model joint rides a fit group (torso, limbs, helmet …) with its own transform from model to game bind pose; skin weights are remapped to game bones; geometry is written into the vanilla containers' LOD0 with `mmbio.py` |
| Textures | `build_textures.py`: single-level DDS carriers at mod-private paths |
| Materials | `build_materials.py`: the Stormtrooper armour material copied over each piece's material, texture paths aliased (same byte length) to the carriers |
| Cape | `build_cape.py`: the cape slot in the player's gear list points at the Canto Bight police cape; its cloth is un-stiffened in the `.mcloth` (friction and damping values only this cape has; `hero_cloth`), its mesh is fitted around the neck plates, its material recoloured |
| Head | `build_cape.py`: the head entry is removed from the player's gear list (hides the bare head under the helmet, for the player only) |
| Gear graphs | `build_graphs.py` (reader: `bv2g.py`), same-length connection edits: the ten worn Boba gear graphs take mesh visibility from gear input 151 (= not in first person, as Kay's own gear does); Kay's accessories graph is shipped again with its meshes off (the grapple rope attaches to its joints); the cape's cloth "follow" input is set to 0 |

## Format facts this relies on

Each is documented where it is implemented:

- **`.mmb` skinned meshes** (`mmbio.py`): int16 positions scaled per vertex, N × uint16 weights summing to
  32767, N × uint8 bone indices (N = 8, or 4 for boots). Game space is left-handed, Y up, +Z front.
- **Loose textures must be single-level DDS.** With a mip chain the game shows only the smallest mips.
  A loose albedo is sampled as linear (store `(v/255)^2.2`).
- **Normal maps** are A = X, G = Y (green up), R = copy of G, B = ambient occlusion.
- **`.mcloth`** (`mcloth.py`): flat chunk stream; particles are the cloth sim mesh's vertices in order;
  the quantised per-particle table in ids 178-180 is the collision radius (not a leash), the backstop and
  max-distance limits live in ids 12-14, and each settings block is a 149-byte struct plus a few chunks.
  The game reads a loose `.mcloth`; it does not read the sim mesh's vertex colours.
- **Gear lists** (`character_visuals_*.mcharactervisuals`) are plain text. A part that is not listed is
  not built. A 0-byte `.mgraphobject` override also hides a part, but for every character that loads it.
- **`.mgraphobject`** (`bv2g.py`): numbered entries with a trailing kind table; nodes, properties and the
  connection list (`[src node][src pin][dst node][dst pin]`) can be read and re-pointed in place. Scalar
  numbers in records are not IEEE floats (6-bit exponent, 25-bit mantissa; `bv2g.number`).
- **Why a cape is stiff or free**: compare its `.mcloth` settings with a cape that behaves the way you
  want before changing anything. The Canto police cape differed from the free capes only in two
  friction-like values, its damping and the graph's follow input.

## Known gaps

- The cape is still drawn in first-person moments: its graph sits on the Canto Bight police cape's own
  path, and the first-person edit could hide the cape on NPCs. A private copy of the graph is the next step.
- The cape's mesh, material, cloth and graph overrides sit on the Canto Bight police cape's own paths, so
  those NPCs get them too.
- Only Kay's standard accessories graph is restored for the grapple rope; three outfit variants are not.
