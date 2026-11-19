#!/usr/bin/env python3
"""
build_materials.py — material files for the Din pieces (staging tree only; nothing touches the game).

Same proven recipe the v1.2 chrome uses: copy the Stormtrooper
`px_armor_st__col_mat_norm_dirt_dent` donor material over the piece's material path, alias its
_d/_m/_n texture strings (same byte length) to our private carriers, point the shared scratch
detail-normal at a neutral one, Color Tint -> 1.0. See PIECES for which material gets which set.
"""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, ".."))
import bv2, matconst            # noqa: E402
import alias_string as A        # noqa: E402
import numpy as np             # noqa: E402
from build_textures import priv, STAGE, write_uncompressed_dds  # noqa: E402

# Vanilla Stormtrooper helmet material (export it with Hunter; game asset, kept out of the repo).
DONOR = os.environ.get("OMTK_DONOR_MATERIAL") or os.path.join(
    ROOT, "local/din_swap/containers/mat_chr_headw_2_silver_stormtrooper_helmet.mmaterial")
# Neutral detail-normal for the donor's `tt_scratches_01_n` slot (60-byte path, same length).
# In the game's layout a flat normal is R=G=128 (Y=0), B=255 (AO=1), A=128 (X=0). The older shared
# flat (mando_shared_flat.dds) has A=255 = X+1, so the Din materials get their own correct one and
# the shipped v1.2 pieces are left exactly as they are.
FLAT = "helix/baked/art/textures/tech_textures/mando_din_flat_n0.dds"
PIECES = [   # (carrier set, material file) — every material whose submesh now carries Din geometry
    ("dinhead", "mat_chr_headw_5_canon_boba_fett_helmet_metal"),
    # armour plates
    ("dinarmor", "mat_chr_top_5_canon_boba_fett_vest_metal"),          # vest_mesh: chest / back / pauldrons
    ("dinarmor", "mat_chr_acc_5_canon_boba_fett_bracers_metal"),       # bracers_mesh: gauntlets
    ("dinarmor", "mat_chr_acc_5_canon_boba_fett_pouches_linen_rough"), # pouches_mesh: thigh plates
    # everything textured by the Body set. Containers with two/three submeshes get the SAME carriers on
    # all their materials, so the build does not depend on knowing which submesh uses which material.
    ("dinbody", "mat_chr_top_5_canon_boba_fett_vest_denim"),           # cord_mesh (stub)
    ("dinbody", "mat_chr_top_5_canon_boba_fett_shirt_linen_rough"),    # shirt_mesh: jacket, sleeves, neck, bandolier
    ("dinbody", "mat_chr_acc_5_canon_boba_fett_gloves_leather"),       # gloves_mesh (note: this mesh has one UV set)
    ("dinbody", "mat_chr_botm_5_canon_boba_fett_pants_linen_rough"),   # pants_mesh: legs
    ("dinbody", "mat_chr_botm_5_canon_boba_fett_pants_metal"),         # acc_mesh (stub)
    ("dinbody", "mat_chr_botm_5_canon_boba_fett_boots_metal"),         # metal_mesh: boots
    ("dinbody", "mat_chr_botm_5_canon_boba_fett_boots_linen_rough"),   # boots_mesh (stub)
    ("dinbody", "mat_chr_top_5_canon_boba_fett_belt_leather"),         # belt_mesh: belt, holster, blaster
    ("dinbody", "mat_chr_top_5_canon_boba_fett_belt_metal"),           # stub
    ("dinbody", "mat_chr_top_5_canon_boba_fett_belt_denim"),           # stub
]


def build():
    out = []
    os.makedirs(os.path.join(STAGE, "helix/materials"), exist_ok=True)
    assert len(FLAT) == 60
    flat = np.zeros((256, 256, 4), np.uint8); flat[..., 0] = 128; flat[..., 1] = 128; flat[..., 2] = 255; flat[..., 3] = 128
    write_uncompressed_dds(os.path.join(STAGE, FLAT), flat)
    stale = os.path.join(STAGE, "helix/baked/art/textures/tech_textures/mando_shared_flat.dds")
    if os.path.exists(stale): os.remove(stale)
    donor_len = os.path.getsize(DONOR)
    for key, mat in PIECES:
        dst = os.path.join(STAGE, "helix/materials", mat + ".mmaterial")
        shutil.copy(DONOR, dst)
        for chan in ("d", "m", "n"):
            ok, msg = A.alias(dst, "stormtrooper_%s.dds" % chan, priv(key, chan), dst)
            assert ok, f"{key} {chan}: {msg}"
            assert os.path.exists(os.path.join(STAGE, priv(key, chan))), f"missing carrier {priv(key, chan)}"
        ok, msg = A.alias(dst, "tt_scratches_01_n", FLAT, dst); assert ok, f"{key} scratch: {msg}"
        mm, cs = matconst.load_constants(dst)
        c = next(x for x in cs if x.name == "Color Tint"); matconst.set_const(mm, c, [1.0, 1.0, 1.0])
        open(dst, "wb").write(mm.build())
        # ---- validate ----
        assert os.path.getsize(dst) == donor_len, "material length changed"
        m = bv2.BV2.load(dst)
        tex = [s for s in m.strings if s.endswith(".dds")]
        shader = next(s for s in m.strings if s.endswith(".mshader"))
        _, cs = matconst.load_constants(dst)
        tint = next(x for x in cs if x.name == "Color Tint").values
        out.append((mat, shader, tint, tex))
    return out


if __name__ == "__main__":
    for mat, shader, tint, tex in build():
        print(mat, "\n   shader:", shader.split("/")[-1], " tint:", [round(t, 3) for t in tint])
        for t in tex: print("   ", t.split("/")[-1])
