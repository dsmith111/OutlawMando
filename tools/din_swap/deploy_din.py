#!/usr/bin/env python3
"""
deploy_din.py — copy the Din staging tree into the game folder (loose overrides served by Raindrop),
with a full backup + manifest so it can be reverted exactly.

  python3 deploy_din.py            # dry run: show what would change
  python3 deploy_din.py --apply    # back up anything it overwrites, then copy
  python3 deploy_din.py --revert   # restore backups, delete files this deploy added
  python3 deploy_din.py --redeploy # after rebuilding staging: revert, then apply the new staging
  python3 deploy_din.py --status   # compare game tree with staging / manifest
  python3 deploy_din.py --apply --only helmet   # subset, e.g. to bisect a problem (helmet | textures | meshes | cape)
  python3 deploy_din.py --redeploy --without cape   # everything except a group (e.g. keep Boba's poncho)

Game root: $OMTK_GAME_ROOT or the default Steam path. Fully quit and relaunch the game to see changes.
"""
import hashlib, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
STAGE = os.path.join(ROOT, "local/din_swap/staging")
STATE = os.path.join(ROOT, "local/din_swap/deploy")
MANIFEST = os.path.join(STATE, "manifest.json")
GAME = os.environ.get("OMTK_GAME_ROOT", "/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws")
VISUALS_REL = "helix/game system data/juice/character/character_visuals_player.mcharactervisuals"
# Files that EARLIER versions of the mod put in the game folder and the current build must not leave there.
# A retired file is moved to the backup (so --revert puts it back) only if it is still what we put there
# (size check) and only when the staged file that takes over its job is part of this deploy.
RETIRED = {
    # v1.2 / v2.0 hid the player's head with this 0-byte override, which also removed the head of every NPC
    # that loads the same head graph. The staged gear list has no head entry any more (build_cape.py).
    "helix/graph objects/gear/chr_head_2_silver_human_sea_m_001.mgraphobject": dict(size=0, needs=VISUALS_REL),
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


GROUPS = {   # --only <group>: deploy a subset (for bisecting if something misbehaves in-game)
    "helmet": ("chr_headw_5_canon_boba_fett_helmet.mmb", "helmet_metal.mmaterial", "mando_dinhead_", "mando_din_flat"),
    "textures": (".dds", ".mmaterial"),
    "meshes": (".mmb",),
    "cape": ("character_visuals_player", "canto_police_cape"),     # the borrowed cape (gear list + its mesh/material)
}
ONLY = None
WITHOUT = None


def staged():
    out = []
    for d, _, fs in os.walk(STAGE):
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, STAGE)
            if ONLY and not any(k in rel for k in GROUPS[ONLY]):
                continue
            if WITHOUT and any(k in rel for k in GROUPS[WITHOUT]):
                continue
            out.append(rel)
    return sorted(out)


def game_running():
    try:
        t = subprocess.run(["tasklist.exe"], capture_output=True, text=True, timeout=20).stdout.lower()
        return "outlaws.exe" in t
    except Exception:
        return False


def plan():
    rows = []
    for rel in staged():
        src = os.path.join(STAGE, rel); dst = os.path.join(GAME, rel)
        if not os.path.exists(dst): act = "add"
        elif sha(src) == sha(dst): act = "same"
        else: act = "replace"
        rows.append((act, rel, os.path.getsize(src)))
    live = {rel for _, rel, _ in rows}
    for rel, rule in RETIRED.items():
        dst = os.path.join(GAME, rel)
        if rule["needs"] in live and os.path.isfile(dst) and os.path.getsize(dst) == rule["size"]:
            rows.append(("retire", rel, rule["size"]))
    return rows


def apply():
    if not os.path.isdir(os.path.join(GAME, "helix")):
        sys.exit(f"game root not found: {GAME}")
    if os.path.exists(MANIFEST):
        sys.exit("a deploy manifest already exists — run --revert first (or --status).")
    if game_running():
        print("NOTE: Outlaws.exe is running; files are copied now but only load after a full quit + relaunch.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(STATE, "backup_" + stamp)
    man = {"stamp": stamp, "game": GAME, "backup_dir": bdir, "files": []}
    for act, rel, size in plan():
        src = os.path.join(STAGE, rel); dst = os.path.join(GAME, rel)
        if act == "retire":           # a leftover of an earlier version: back it up, then remove it
            b = os.path.join(bdir, rel); os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy2(dst, b); assert sha(b) == sha(dst)
            man["files"].append({"rel": rel, "action": act, "sha_old": sha(b)})
            os.remove(dst); assert not os.path.exists(dst)
            print(f"  {act:8s} {rel}")
            continue
        entry = {"rel": rel, "action": act, "sha_new": sha(src)}
        if act == "replace":
            b = os.path.join(bdir, rel); os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy2(dst, b); entry["sha_old"] = sha(b)
            assert entry["sha_old"] == sha(dst)
        if act in ("add", "replace"):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            assert sha(dst) == entry["sha_new"], f"copy verification failed: {rel}"
        man["files"].append(entry)
        print(f"  {act:8s} {rel}")
    os.makedirs(STATE, exist_ok=True)
    json.dump(man, open(MANIFEST, "w"), indent=1)
    print(f"deployed. manifest: {MANIFEST}\nbackup of replaced files: {bdir}")


def revert():
    if not os.path.exists(MANIFEST):
        sys.exit("no deploy manifest — nothing to revert.")
    man = json.load(open(MANIFEST))
    for e in man["files"]:
        dst = os.path.join(man["game"], e["rel"])
        if e["action"] == "add":
            if os.path.exists(dst):
                if sha(dst) != e["sha_new"]:
                    print(f"  KEEP (modified since deploy) {e['rel']}"); continue
                os.remove(dst); print(f"  removed  {e['rel']}")
        elif e["action"] == "replace":
            b = os.path.join(man["backup_dir"], e["rel"])
            shutil.copyfile(b, dst); assert sha(dst) == e["sha_old"]
            print(f"  restored {e['rel']}")
        elif e["action"] == "retire":
            if os.path.exists(dst):
                print(f"  KEEP (reappeared since deploy) {e['rel']}"); continue
            b = os.path.join(man["backup_dir"], e["rel"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(b, dst); assert sha(dst) == e["sha_old"]
            print(f"  put back {e['rel']}")
    os.rename(MANIFEST, MANIFEST + ".reverted_" + time.strftime("%Y%m%d_%H%M%S"))
    print("reverted to the pre-deploy state.")


def status():
    for act, rel, size in plan():
        label = {"same": "IN GAME", "replace": "differs", "add": "missing", "retire": "STALE"}[act]
        print(f"  {label:8s} {size:9d}  {rel}")
    print("manifest:", MANIFEST if os.path.exists(MANIFEST) else "(none — not deployed by this tool)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--only" in args:
        ONLY = args[args.index("--only") + 1]
        assert ONLY in GROUPS, f"--only must be one of {list(GROUPS)}"
        args = [a for a in args if a not in ("--only", ONLY)]
    if "--without" in args:
        WITHOUT = args[args.index("--without") + 1]
        assert WITHOUT in GROUPS, f"--without must be one of {list(GROUPS)}"
        args = [a for a in args if a not in ("--without", WITHOUT)]
    arg = args[0] if args else "--dry-run"
    if arg == "--redeploy":            # staging changed: put the game back to the pre-deploy state, then deploy again
        if os.path.exists(MANIFEST): revert()
        apply()
    elif arg == "--apply": apply()
    elif arg == "--revert": revert()
    elif arg == "--status": status()
    else:
        print(f"DRY RUN — game root: {GAME}")
        for act, rel, size in plan():
            print(f"  {act:8s} {size:9d}  {rel}")
        print("run with --apply to deploy (replaced files are backed up; --revert undoes it).")
