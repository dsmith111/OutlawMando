#!/usr/bin/env bash
# Assemble the Nexus release package for the Din Djarin MODEL SWAP (v2.x of "Mandalorian Beskar").
#
#   repo/scripts/build_din_package.sh            -> <workspace>/dist/MandalorianBeskar_v2.1/ + .zip
#   VERSION=2.2 repo/scripts/build_din_package.sh
#
# <workspace> is the folder this repo is checked out in (as `repo/`); it holds the private inputs and
# outputs that never go into git: local/ (vanilla game files, staging tree) and dist/ (packages).
#
# Unlike build_package.sh (v1.x, which copied files out of the game folder), this builds from the Din
# staging tree (local/din_swap/staging, produced by tools/din_swap/build_all.sh), so the package
# never depends on what happens to be deployed in the game.
#
# Ships ONLY: the 10 Din outfit meshes, the borrowed cape (mesh + cloth + material), 14 outfit materials,
# 10 textures, the edited gear list (cape slot repointed, head entry removed), README.txt.
# Does NOT bundle: the base "Play as Boba Fett" mod, Raindrop, any loader / DirectStorage binaries.
#
# v2.1: NO file is shipped at the shared head graph's path any more. v1.2 / v2.0 hid the player's bare head
# with a 0-byte override of helix/graph objects/gear/chr_head_2_silver_human_sea_m_001.mgraphobject, and
# every NPC that loads the same head graph lost its head too. The head is now hidden by leaving it out of
# the player's gear list (build_cape.py: drop_gear_entry). The checks below fail if that file comes back.
#
# The cape is rebuilt here with RELEASE_CAPE_ARGS, i.e. the cloth configuration that was confirmed in
# game (rev 8), NOT whatever experimental cloth settings the dev staging tree currently holds.
set -euo pipefail
VERSION="${VERSION:-2.1}"
RELEASE_CAPE_ARGS=(cape_limit_radius=0)

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$REPO/.." && pwd)"          # the workspace: local/ (inputs, staging) and dist/ (output)
TOOLS="$REPO/tools/din_swap"
STAGE="$ROOT/local/din_swap/staging"
BASE_VISUALS="$ROOT/local/din_swap/containers/cape/character_visuals_player.BASEMOD.mcharactervisuals"
NAME="MandalorianBeskar_v$VERSION"
OUT="$ROOT/dist/$NAME"
ZIP="$ROOT/dist/$NAME.zip"
OLD_HEAD_HIDE="helix/graph objects/gear/chr_head_2_silver_human_sea_m_001.mgraphobject"   # must NOT be in the package

echo "== 1. staging tree must be a valid build"
( cd "$TOOLS" && python3 validate_all.py | tail -1 | grep -q "ALL CONTAINERS VALID" ) \
  || { echo "!! staging is not a valid build - run tools/din_swap/build_all.sh first"; exit 1; }

echo "== 2. copy staging -> $OUT"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -r "$STAGE/helix" "$OUT/helix"

echo "== 3. cape rebuilt with the release cloth configuration (${RELEASE_CAPE_ARGS[*]})"
( cd "$TOOLS" && DIN_CAPE_STAGE="$OUT" python3 build_cape.py "${RELEASE_CAPE_ARGS[@]}" ) | grep -o "'mcloth': '[^']*'" | sed 's/^/   /'

# --- 4. the end-user README (generated here so it always ships) ---
cat > "$OUT/README.txt" <<README
MANDALORIAN BESKAR - Din Djarin for "Play as Boba Fett"
========================================================
Version $VERSION

WHAT IT DOES
  Turns the "Play as Boba Fett" outfit into The Mandalorian (Din Djarin) with a
  full replacement character model - no longer a recoloured Boba Fett:
    - New helmet, chest and back plates, pauldrons, gauntlets, gloves, flight
      suit, bandolier, belt with holster and blaster, thigh plates and boots.
    - Brushed beskar finish taken from the model's own textures (less mirror-like
      than the 1.x chrome).
    - A cloth back cape in place of Boba's poncho.

REQUIREMENTS (install first, in this order)
  1. Star Wars Outlaws (PC).
  2. The "Play as Boba Fett" mod + everything IT requires. This is an override
     ADD-ON for that mod. Install it and its requirements first.
  3. The Raindrop loader (dinput8.dll). REQUIRED - this mod ships loose meshes,
     cloth data and uncompressed textures that only Raindrop serves; the
     version.dll loader will NOT load them. This does not bundle Raindrop - get it
     from its own page.

INSTALL
  Mod manager: install this archive AFTER "Play as Boba Fett" and let it OVERWRITE
    that mod's files.
  Manual: copy the "helix" folder into your game root
    ...\\Star Wars Outlaws\\
  so files land at ...\\Star Wars Outlaws\\helix\\... - overwrite when asked.
  Fully quit and restart the game afterwards.

UPDATING FROM 1.x OR 2.0 - DELETE ONE OLD FILE
  Versions up to 2.0 installed an empty file that hid the heads of many NPCs
  along with the player's. This version does not use it, but installing over an
  old version does not remove it. Delete this file from your game folder:
      helix\\graph objects\\gear\\chr_head_2_silver_human_sea_m_001.mgraphobject
  If your mod manager uninstalled the old version first, it is already gone.
  Any other leftover 1.x files are no longer used and do no harm.

IMPORTANT
  - This version replaces ONE file of the "Play as Boba Fett" mod:
      helix\\game system data\\juice\\character\\character_visuals_player.mcharactervisuals
    It is that mod's outfit list with two changes: the cape slot loads the new
    cape instead of the poncho, and the bare head under the helmet is no longer
    listed, so it cannot poke through the helmet. If you reinstall or update the
    Boba mod later, install this mod on top of it again.
  - Keep DirectStorage DISABLED (as Raindrop setups normally are). With it on, the
    game resets these materials and the outfit will not look right.

KNOWN ISSUES
  - The cape is borrowed from another in-game outfit (the Canto Bight police
    cape). It hangs correctly but moves stiffly, and it can cling to or clip
    through the legs when you run. Better cloth movement is planned for a later
    version.
  - Because the cape reuses that outfit's files, Canto Bight police officers get
    the same brown cape colour.
  - Small clipping can show in extreme poses.

UNINSTALL
  Delete the "helix" files this archive added, then reinstall "Play as Boba Fett"
  to restore its character_visuals_player file.

CHANGES
  2.1
  - Fixed: many NPCs had invisible heads. The player's head is now hidden
    through the outfit list, so no other character is affected. If you are
    updating, delete the old file named above.
  2.0
  - A full Din Djarin model replaces the reshaped Boba Fett outfit.
  - New back cape; the poncho is no longer used.
  - Armor shine now follows the model's own textures.

CREDITS
  Din Djarin model: this work is based on "Mandalorian Armored - Fortnite"
    (https://sketchfab.com/3d-models/mandalorian-armored-fortnite-6dabccb1ba044d85ad6b05a94544973c)
    by Yxboireal (https://sketchfab.com/Yeboireal), licensed under CC-BY-4.0
    (http://creativecommons.org/licenses/by/4.0/). It was cut into outfit pieces,
    re-fitted, re-rigged and re-textured for Star Wars Outlaws.
  Base outfit: the "Play as Boba Fett" mod author. Loader: DTZxPorter (Raindrop).
README

echo "== 5. package checks"
python3 - "$OUT" "$BASE_VISUALS" "$TOOLS" "$OLD_HEAD_HIDE" <<'PY'
import difflib, os, re, struct, sys
out, base_visuals, tools, old_head_hide = sys.argv[1:5]
sys.path.insert(0, tools)
import mcloth
files = sorted(os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs)
fail = []
def need(cond, msg):
    if not cond: fail.append(msg)
low = [f.lower() for f in files]
# nothing that is not ours to ship
bad = [f for f in low if f.endswith((".dll", ".exe", ".bak", ".sdf", ".sdftoc", ".asi")) or "backpack" in f or "oo2core" in f]
need(not bad, f"forbidden files: {bad}")
by_ext = {}
for f in files: by_ext.setdefault(os.path.splitext(f)[1].lower(), []).append(f)
expect = {".mmb": 11, ".mcloth": 1, ".mmaterial": 15, ".dds": 10, ".mcharactervisuals": 1, ".txt": 1}
for ext, n in expect.items(): need(len(by_ext.get(ext, [])) == n, f"expected {n} {ext} files, found {len(by_ext.get(ext, []))}")
need(set(by_ext) == set(expect), f"unexpected file types: {sorted(set(by_ext) - set(expect))}")
# no graph overrides at all, and above all not the shared head graph (v1.2 / v2.0 bug: it blanked NPC heads);
# no empty files either - nothing in this package relies on a 0-byte override any more
need(not by_ext.get(".mgraphobject") and old_head_hide not in files, "the package must not contain any .mgraphobject (the old head-hide override hides NPC heads)")
empty = [f for f in files if os.path.getsize(os.path.join(out, f)) == 0]
need(not empty, f"empty files in the package: {empty}")
# the gear list is the base mod's file with exactly two edits: poncho graph -> cape graph, head entry removed
raw_a = open(base_visuals, "rb").read(); raw_b = open(os.path.join(out, by_ext[".mcharactervisuals"][0]), "rb").read()
a = raw_a.splitlines(); b = raw_b.splitlines()
removed, added = [], []
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
    if tag != "equal": removed += a[i1:i2]; added += b[j1:j2]
gone = [l for l in removed if b"myGearGraph" in l]
need(len(added) == 1 and b"canto_police_cape" in added[0] and len(removed) == 8 and len(gone) == 2
     and b"boba_fett_poncho" in gone[0] and b"chr_head_2_silver_human_sea_m_001" in gone[1],
     f"gear list must differ from the base mod's by the cape line and the removed head entry only (-{len(removed)} +{len(added)} lines)")
need(b"chr_head_" not in raw_b.split(b"character_visuals_pet")[0], "the player's gear list still lists a head")
need(raw_b.count(b"{") == raw_b.count(b"}") == raw_a.count(b"{") - 2 and raw_b.count(b"\n") == raw_b.count(b"\r\n"), "gear list is not well-formed (braces / CRLF)")
# every private texture a packaged material points at is in the package
missing = set()
for m in by_ext[".mmaterial"]:
    for ref in re.findall(rb"helix/[ -~]*?mando[ -~]*?\.dds", open(os.path.join(out, m), "rb").read()):
        if ref.decode() not in files: missing.add(ref.decode())
need(not missing, f"materials reference textures that are not packaged: {sorted(missing)}")
unref = [f for f in by_ext[".dds"] if not any(f.encode() in open(os.path.join(out, m), "rb").read() for m in by_ext[".mmaterial"])]
need(not unref, f"packaged textures no material uses: {unref}")
# the cloth is the configuration confirmed in game (rev 8): table to 0.40 m, limit radius untouched
buf = open(os.path.join(out, by_ext[".mcloth"][0]), "rb").read()
for name, off, cs in mcloth.sections(buf):
    radii = [struct.unpack_from("<f", buf, po + mcloth.LIMIT_OFF)[0] for po in mcloth.settings_blocks(buf, cs)]
    t = mcloth.max_distance(buf, cs)
    need(all(abs(r - 0.0392157) < 1e-5 for r in radii) and abs(t["dist"][:t["n"]].max() - 0.40) < 1e-3, f"{name}: cloth is not the release configuration ({radii})")
if fail:
    print("!! PACKAGE CHECK FAILED"); [print("   -", m) for m in fail]; sys.exit(1)
print(f"   ok: {len(files)} files -", ", ".join(f"{len(v)} {k}" for k, v in sorted(by_ext.items())))
PY

echo "== 6. zip (helix/ + README.txt at the archive root)"
rm -f "$ZIP"
( cd "$OUT" && zip -q -r -X "$ZIP" helix README.txt )
python3 - "$ZIP" "$OUT" "$OLD_HEAD_HIDE" <<'PY'
import os, sys, zipfile
z = zipfile.ZipFile(sys.argv[1]); out = sys.argv[2]; old_head = sys.argv[3]
names = [i for i in z.infolist() if not i.is_dir()]
disk = sorted(os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs)
assert sorted(i.filename for i in names) == disk, "zip contents differ from the package folder"
assert all(i.filename.startswith("helix/") or i.filename == "README.txt" for i in names), "unexpected top-level entry"
assert old_head not in z.namelist() and all(i.file_size > 0 for i in names), "the archive holds the old head-hide override or an empty file"
assert z.testzip() is None
print(f"   ok: {len(names)} files, {sum(i.file_size for i in names) / 1e6:.1f} MB unpacked, {os.path.getsize(sys.argv[1]) / 1e6:.1f} MB zipped")
PY
echo "== package: $OUT"
echo "== archive: $ZIP"
