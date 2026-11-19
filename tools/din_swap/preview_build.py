#!/usr/bin/env python3
"""Render what is actually inside the staged .mmb files (read back through mmbio), textured with
the original albedo. Modes: body (full figure), bust, vanilla (the untouched Boba outfit for reference)."""
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mmbio, preview
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
W = os.path.join(ROOT, "local/din_swap/work/preview"); STAGE = os.path.join(ROOT, "local/din_swap/staging")
TEX = os.path.join(ROOT, "downloaded_models/extracted/fortnite_rar_pkg/textures")   # original orientation
TEXFILE = {"Head": "Heavy_Head", "Armor": "Heavy_BodyArmor_Heavy", "Body": "Heavy_Body"}
REPORT = os.path.join(ROOT, "local/din_swap/work/build_report.json")
CH = "helix/baked/art/characters/characters"
REL_HELMET = f"{CH}/chr_headwear/chr_headw_5_canon_boba_fett_helmet/chr_headw_5_canon_boba_fett_helmet.mmb"
REL_VEST = f"{CH}/chr_top/chr_top_5_canon_boba_fett_vest/chr_top_5_canon_boba_fett_vest.mmb"
TEXSET = {"helmet_mesh": "Heavy_Head", "vest_mesh": "Heavy_BodyArmor_Heavy", "cord_mesh": "Heavy_Body"}


def staged_meshes():
    """yield (rel, submesh name, texture set, LodData) for every non-stub staged submesh."""
    rep = json.load(open(REPORT))
    for key, tex in rep["slot_textures"].items():
        rel, slot = key.split("::")
        a = mmbio.parse_header(os.path.join(STAGE, rel))
        mi = [m.name for m in a.meshes].index(slot)
        yield rel, slot, tex, mmbio.read_lod(a, mi, 0), a


def staged_items(tag="st", posed=None):
    items = []
    for rel, slot, tex, d, a in staged_meshes():
        P = d.pos if posed is None else posed(rel, slot, d, a)
        o = os.path.join(W, f"{tag}_{os.path.basename(rel)[:-4]}_{slot}.obj"); preview.write_obj(o, P, d.tris, d.uv0, d.nrm)
        items.append(dict(obj=o, texture=os.path.join(TEX, f"T_M_MED_Cosmos_{TEXFILE[tex]}_D.png"), roughness=0.5))
    return items


def vanilla_items(color=(0.55, 0.45, 0.35)):
    items = []
    C = os.path.join(ROOT, "local/din_swap/containers")
    srcs = [os.path.join(C, f) for f in sorted(os.listdir(C)) if f.endswith(".mmb")] + [os.path.join(ROOT, "local/mesh_edit/helmet_v6_forcelod0.mmb")]
    for p in srcs:
        a = mmbio.parse_header(p)
        for mi, m in enumerate(a.meshes):
            if "SIM" in m.name: continue
            d = mmbio.read_lod(a, mi, 0)
            o = os.path.join(W, f"van_{os.path.basename(p)[:-4]}_{m.name}.obj"); preview.write_obj(o, d.pos, d.tris)
            metal = any(k in m.name for k in ("metal", "vest_mesh", "helmet", "bracers", "kneepads_mesh"))
            items.append(dict(obj=o, color=[0.75, 0.76, 0.8] if metal else list(color)))
    return items


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "body"
    full = [[-0.72, -0.02, -0.35], [0.72, 1.80, 0.35]]
    if mode in ("body", "all"):
        print(preview.render(W, "p2_body", staged_items(), views=("front", "side", "back", "q"), res=(820, 1080), crop=full))
    if mode in ("bust", "all"):
        print(preview.render(W, "p2_bust", staged_items(), views=("front", "back", "q"), res=(900, 820), crop=[[-0.45, 0.98, -0.3], [0.45, 1.80, 0.3]]))
    if mode in ("vanilla", "all"):
        print(preview.render(W, "p2_vanilla", vanilla_items(), views=("front", "side"), res=(820, 1080), crop=full))
