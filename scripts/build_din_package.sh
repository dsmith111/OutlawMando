#!/usr/bin/env bash
# Assemble the Nexus release package for the Din Djarin MODEL SWAP (v2.x of "Mandalorian Beskar").
#
#   repo/scripts/build_din_package.sh            -> <workspace>/dist/MandalorianBeskar_v2.2/ + .zip
#   VERSION=2.3 repo/scripts/build_din_package.sh
#
# <workspace> is the folder this repo is checked out in (as `repo/`); it holds the private inputs and
# outputs that never go into git: local/ (vanilla game files, staging tree) and dist/ (packages).
#
# The package is built from the Din staging tree (local/din_swap/staging, produced by
# tools/din_swap/build_all.sh), never from the game folder. The cape and the gear graphs are rebuilt
# into the package with the settings pinned below, so a release does not depend on whatever experiment
# the staging tree currently holds.
#
# Ships ONLY: the 10 Din outfit meshes, the borrowed cape (mesh + cloth + material + graph), 14 outfit
# materials, 10 textures, the edited gear list, 11 more edited gear graphs, README.txt.
# Does NOT bundle: the base "Play as Boba Fett" mod, Raindrop, any loader / DirectStorage binaries.
#
# History of what is pinned here:
#   2.1  no file at the shared head graph's path (the 0-byte head-hide of 1.2 / 2.0 blanked NPC heads); the head
#        entry is removed from the player's gear list instead. The checks fail if that file comes back.
#   2.2  cloth = hero_cloth (vanilla cloth minus the Canto-only friction / damping, deeper backstop), cape graph with
#        follow 0, the ten worn Boba gear graphs wired to the first-person signal, Kay's accessories graph restored
#        with its meshes off (grapple rope). All confirmed in game.
set -euo pipefail
VERSION="${VERSION:-2.2}"
RELEASE_CAPE_ARGS=(cape_friction=0 cape_friction2=0 cape_damping=1,1,1,1,1 cape_inward=1.5
                   cape_inward_top=1.15 cape_inward_bottom=0.90 cape_neck_fit=1 cape_hang=1)

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
rm -rf "$OUT/helix/graph objects"       # rebuilt below from the vanilla exports

echo "== 3. cape and gear graphs rebuilt with the release configuration"
( cd "$TOOLS" && DIN_CAPE_STAGE="$OUT" python3 build_cape.py "${RELEASE_CAPE_ARGS[@]}" ) | grep -o "'mcloth': '[^']*'" | cut -c1-230 | sed 's/^/   /'
( cd "$TOOLS" && DIN_GRAPH_STAGE="$OUT" python3 build_graphs.py ) | sed 's/^/   /' | cut -c1-150

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
    - A free-flowing cloth back cape in place of Boba's poncho.

REQUIREMENTS (install first, in this order)
  1. Star Wars Outlaws (PC).
  2. The "Play as Boba Fett" mod + everything IT requires ("Hide Kay's
     Accessories" and "Hide Kay's Clothes"). This is an override ADD-ON for that
     setup. Install all of it first.
  3. The Raindrop loader (dinput8.dll). REQUIRED - this mod ships loose meshes,
     cloth data and uncompressed textures that only Raindrop serves; the
     version.dll loader will NOT load them. This does not bundle Raindrop - get it
     from its own page.

INSTALL
  Mod manager: install this archive AFTER "Play as Boba Fett" and "Hide Kay's
    Clothes" and let it OVERWRITE their files.
  Manual: copy the "helix" folder into your game root
    ...\\Star Wars Outlaws\\
  so files land at ...\\Star Wars Outlaws\\helix\\... - overwrite when asked.
  Fully quit and restart the game afterwards.

UPDATING
  From 2.1: install over it. Nothing to delete.
  From 1.x or 2.0 - DELETE ONE OLD FILE: versions up to 2.0 installed an empty
  file that hid the heads of many NPCs along with the player's. Installing over
  an old version does not remove it. Delete this file from your game folder:
      helix\\graph objects\\gear\\chr_head_2_silver_human_sea_m_001.mgraphobject
  If your mod manager uninstalled the old version first, it is already gone.
  Any other leftover 1.x files are no longer used and do no harm.

IMPORTANT
  - This version replaces ONE file of the "Play as Boba Fett" mod:
      helix\\game system data\\juice\\character\\character_visuals_player.mcharactervisuals
    It is that mod's outfit list with two changes: the cape slot loads the new
    cape instead of the poncho, and the bare head under the helmet is no longer
    listed, so it cannot poke through the helmet.
  - It also replaces ONE file of "Hide Kay's Clothes":
      helix\\graph objects\\gear\\chr_acc_1_gold_kay_001.mgraphobject
    That mod ships it empty. The grappling hook's rope needs the attachment
    points inside it, so this version ships a working copy with Kay's holster,
    wire pouch and rope coil switched off.
  - If you reinstall or update either of those mods later, install this mod on
    top of them again.
  - Keep DirectStorage DISABLED (as Raindrop setups normally are). With it on, the
    game resets these materials and the outfit will not look right.

KNOWN ISSUES
  - In first-person moments (vents, lockpicking) the outfit now hides, but the
    cape can still be seen.
  - The cape is borrowed from another in-game outfit (the Canto Bight police
    cape) and reuses its files, so Canto Bight police officers get the same brown
    colour and the same looser cape movement.
  - The rope fix covers Kay's standard accessories. A few of her outfit sets use
    their own accessories file; with one of those equipped the rope may still be
    invisible.
  - Small clipping can show in extreme poses.

UNINSTALL
  Delete the "helix" files this archive added, then reinstall "Play as Boba Fett"
  and "Hide Kay's Clothes" to restore the two files named under IMPORTANT.

CHANGES
  2.2
  - Cape: moves freely now. It no longer sticks to the legs or holds a rigid
    shape.
  - First-person moments (crawling through vents, lockpicking): the outfit hides
    instead of blocking the view.
  - Grappling hook: the rope is visible again.
  2.1
  - Fixed: many NPCs had invisible heads. The player's head is now hidden
    through the outfit list, so no other character is affected. If you are
    updating from 2.0 or older, delete the old file named above.
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
import mcloth, bv2g, build_graphs
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
expect = {".mmb": 11, ".mcloth": 1, ".mmaterial": 15, ".dds": 10, ".mcharactervisuals": 1, ".mgraphobject": 12, ".txt": 1}
for ext, n in expect.items(): need(len(by_ext.get(ext, [])) == n, f"expected {n} {ext} files, found {len(by_ext.get(ext, []))}")
need(set(by_ext) == set(expect), f"unexpected file types: {sorted(set(by_ext) - set(expect))}")
# never the shared head graph (v1.2 / v2.0 bug: it blanked NPC heads), and no empty files
need(old_head_hide not in files, "the old head-hide override is in the package (it hides NPC heads)")
empty = [f for f in files if os.path.getsize(os.path.join(out, f)) == 0]
need(not empty, f"empty files in the package: {empty}")

# --- gear graphs: exactly the twelve we edit, each carrying exactly its edit
G = "helix/graph objects/gear/"
want = sorted(G + n + ".mgraphobject" for n in build_graphs.WORN + [build_graphs.ACCESSORIES, build_graphs.CAPE])
need(sorted(by_ext.get(".mgraphobject", [])) == want, "unexpected set of gear graphs")
def const(g, n, ty, value):
    d = g.nodes[n][1]
    return d.get("type") == "native:Constant" and d.get("valueType") == ty and d.get("value") == value and isinstance(d.get("value"), type(value))
for f in by_ext.get(".mgraphobject", []):
    g = bv2g.Graph(os.path.join(out, f)); name = os.path.basename(f)[:-13]
    src = {(c[4], c[5]): (c[2], c[3]) for c in g.connections}
    hc = [n for n in g.nodes if g.node_type(n) == "HC_GearPrefabNode_MeshSkinned"]
    if name in build_graphs.WORN:
        need(hc and all(src[(m, p)] == (2, 151) for m in hc for p in (1002, 1003)), f"{name}: mesh visibility does not follow gear input 151")
    elif name == build_graphs.CAPE:
        cloth = [n for n in g.nodes if g.node_type(n) == "prefab:Cloth"]
        need(len(cloth) == 1 and const(g, src[(cloth[0], 7)][0], "float", 0), f"{name}: cloth follow input is not 0")
        need(all(const(g, src[(m, p)][0], "bool", True) for m in hc for p in (1002, 1003)), f"{name}: the shared cape graph must keep its own visibility (NPCs wear it)")
    else:
        meshes = [n for n in g.nodes if g.node_type(n) == "prefab:MeshSkinned"]
        need(len(meshes) == 3 and all(const(g, src[(m, 0)][0], "bool", False) for m in meshes), f"{name}: accessory meshes are not switched off")
        need(any(g.node_type(n) == "HC_PrefabNodeGrapplingHookRopeInfo" for n in g.nodes), f"{name}: rope info node missing")

# --- the gear list is the base mod's file with exactly two edits: poncho graph -> cape graph, head entry removed
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
# every gear graph the list names is either packaged or left to the base game
listed = [m.decode() for m in re.findall(rb'myGearGraph "([^"]+)"', raw_b.split(b"character_visuals_pet")[0])]
need(set(listed) == set(G + n + ".mgraphobject" for n in build_graphs.WORN + [build_graphs.CAPE]), f"gear list and packaged graphs disagree: {sorted(set(listed) ^ set(want))}")

# --- every private texture a packaged material points at is in the package
missing = set()
for m in by_ext[".mmaterial"]:
    for ref in re.findall(rb"helix/[ -~]*?mando[ -~]*?\.dds", open(os.path.join(out, m), "rb").read()):
        if ref.decode() not in files: missing.add(ref.decode())
need(not missing, f"materials reference textures that are not packaged: {sorted(missing)}")
unref = [f for f in by_ext[".dds"] if not any(f.encode() in open(os.path.join(out, m), "rb").read() for m in by_ext[".mmaterial"])]
need(not unref, f"packaged textures no material uses: {unref}")

# --- the cloth is the configuration confirmed in game (2.2): vanilla collision radii, pins and collision
#     switches; the Canto-only friction and damping gone; backstop deepened below the upper back
buf = open(os.path.join(out, by_ext[".mcloth"][0]), "rb").read()
for name, off, cs in mcloth.sections(buf):
    t = mcloth.max_distance(buf, cs); n = t["n"]
    need(abs(t["dist"][:n].max() - 0.0392157) < 2e-4 and int(t["pinned"][:n].sum()) == 37, f"{name}: collision radii or pins are not vanilla")
    T = [(cid, po, size - 8) for (o_, cid, typ, size, po) in cs if typ == 0x11]
    structs = [buf[po:po + 149] for cid, po, sz in T if cid == 5 and sz == 149]
    f32 = lambda s, o_: struct.unpack_from("<f", s, o_)[0]
    need(len(structs) == 2 and all(s[0] == 2 and s[1] == 1 and s[94] == 1 and s[99] == 1 and abs(f32(s, 26) - 0.0392157) < 1e-5
                                   and f32(s, 125) == 0 and f32(s, 133) == 0 for s in structs), f"{name}: settings struct is not the release configuration")
    need(all(struct.unpack_from("<5f", buf, po) == (1, 1, 1, 1, 1) for cid, po, sz in T if cid == 8), f"{name}: damping chunk")
    need(all(buf[po:po + 2] == b"\x01\x00" for cid, po, sz in T if cid == 43), f"{name}: collision switch")
    ch = mcloth.particle_channel(buf, cs)
    need(ch["lo"] < -1.0, f"{name}: backstop was not deepened ({ch['lo']:.3f})")
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
