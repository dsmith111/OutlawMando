#!/usr/bin/env python3
"""
build_textures.py — convert the Fortnite texture sets into carrier textures for the game's
`px_armor_st__col_mat_norm_dirt_dent` donor material (the shader the shipped chrome beskar uses).

  _d  albedo, stored LINEAR (the game does not sRGB-decode a loose albedo carrier). Bare beskar is
      re-centred on bright silver (albedo IS the metal's reflectance here; Fortnite paints it as dark
      steel); painted metal and everything non-metal keep their true colour; the visor goes black.
  _m  R = metalness, G = roughness, B = 21 (as shipped), A = smoothness (the mirror lever).
      By default BOTH come straight from the model's own roughness map (G = rough, A = 255 - rough,
      the donor's own convention). `shine` (0..1) blends the metal toward the v1.2 chrome finish
      (rough 80 / smooth 195):  shine=0 -> the model's own look, shine=1 -> v1.2 chrome.
  _n  THE GAME'S NORMAL-MAP LAYOUT IS NOT RGB.  Measured on vanilla + the donor's own textures:
          A = normal X (toward +u)      G = normal Y, green-UP      R = copy of G      B = ambient occlusion
      (pinned with Boba's helmet dent, which must read as concave). Fortnite's maps are R = X,
      G = Y green-DOWN, so:  A <- R,  G <- 255 - G,  R <- G,  B <- AO (Fortnite _M red channel).
      Vanilla tangents carry no handedness flag, so UV shells that are mirrored relative to the game's
      convention get their Y flipped back per texel (mask rasterised from the mesh).
      (An RGB normal with alpha = 255 means X = +1 everywhere: every normal lies on its side and the
      surface renders as a dark mirror — the first Phase-1 build had exactly that.)

CONTAINER: every carrier is a SINGLE-LEVEL DDS (see bc.py for why: the game streams upper mips
separately and loose files do not get them, so a carrier with a mip chain shows only its blurry tail —
the first two Din builds rendered as flat average colours). `_d` is DXT1 like the vanilla asset; `_m`
and `_n` need an alpha channel, so DXT5 (or uncompressed BGRA8). CONTAINERS below sets format + size
per set and slot; while the limits are being established the three sets deliberately differ.
Usage: python3 -I build_textures.py [shine=0.0] [beskar=212] [key ...]
"""
import os
import struct
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bc          # noqa: E402
import gltf_load   # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
SRC = os.path.join(ROOT, "downloaded_models/extracted/fortnite_rar_pkg/source_unrar/Mandalorian Armoured")
GLTF = os.path.join(ROOT, "downloaded_models/extracted/fortnite_gltf_pkg/source_unzipped/scene.gltf")
STAGE = os.path.join(ROOT, "local/din_swap/staging")
WORK = os.path.join(ROOT, "local/din_swap/work/tex")
STDREL = "helix/baked/art/characters/characters/chr_headwear/chr_headw_2_silver_stormtrooper"

SETS = {   # key -> (source texture stem, glTF part, is_helmet)
    "dinhead": ("Heavy_Head", "Head", True),
    "dinarmor": ("Heavy_BodyArmor_Heavy", "Armor", False),
    "dinbody": ("Heavy_Body", "Body", False),
}
# (format, size) per set and slot — all SINGLE LEVEL. The rev-3 in-game probe showed every variant
# displaying real detail: DXT1 at 256/512/1024, DXT5 at 256/512, uncompressed BGRA8 at 256.
#   _d  uncompressed: the game reads loose albedo as LINEAR (see build_set), and linear-stored dark colours
#       fall apart in DXT1 (perceptual error ~16/255 on dark leather vs ~1.4 uncompressed).
#   _m  DXT5 (needs alpha = smoothness).
#   _n  uncompressed: block artefacts in a normal map show up as facets in reflections on metal.
_STD = {"d": ("BGRA8", 1024), "m": ("DXT5", 512), "n": ("BGRA8", 512)}
CONTAINERS = {"dinhead": dict(_STD), "dinarmor": dict(_STD), "dinbody": dict(_STD)}
WORK_SIZE = 1024

FINISH = dict(shine=0.0,                       # 0 = the model's own roughness, 1 = v1.2 chrome finish
              chrome_rough=80, chrome_smooth=195,  # the v1.2 finish that shine=1 reproduces
              visor_rough=20, visor_smooth=195,    # black glass visor (as shipped)
              m_blue=21, beskar_target=212, beskar_contrast=0.6, beskar_max_sat=0.22,
              albedo_linear=1,                    # 1 = store non-beskar albedo linearised (game reads it raw)
              ao_floor=110)                        # AO is never darker than this (visor / deep seams)


def priv(key, chan):
    """Private carrier path: same byte length as the donor's own texture path (37-char filename)."""
    fn = ("mando_%s_carrier_%s" % (key, chan) + "0" * 40)[:33] + ".dds"
    return STDREL + "/" + fn


def write_uncompressed_dds(path, rgba):
    """BGRA8 DDS with a full box-filtered mip chain (same header the shipped carriers use)."""
    h, w, _ = rgba.shape
    mips = [rgba]
    cur = Image.fromarray(rgba, "RGBA"); cw, ch = w, h
    while cw > 1 or ch > 1:
        cw = max(1, cw // 2); ch = max(1, ch // 2)
        cur = cur.resize((cw, ch), Image.BOX)
        mips.append(np.asarray(cur))
    DDSD = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000
    hdr = struct.pack("<4sIIIIIII11I", b"DDS ", 124, DDSD, h, w, w * 4, 0, len(mips), *([0] * 11))
    pf = struct.pack("<IIIIIIII", 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    caps = struct.pack("<IIIII", 0x1000 | 0x8 | 0x400000, 0, 0, 0, 0)
    out = bytearray(hdr + pf + caps)
    for mp in mips:
        out += mp.astype(np.uint8)[..., [2, 1, 0, 3]].tobytes()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(out)
    return len(mips), len(out)


def load(stem, suf, size):
    im = Image.open(os.path.join(SRC, f"T_M_MED_Cosmos_{stem}_{suf}.tga")).convert("RGB")
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def raster_mask(uv, tris, size, sel):
    """Boolean (size,size) mask of texels covered by the selected triangles (uv: v down)."""
    mask = np.zeros((size, size), bool)
    P = uv * size
    for t in tris[sel]:
        a, b, c = P[t[0]], P[t[1]], P[t[2]]
        x0 = int(max(0, np.floor(min(a[0], b[0], c[0])) - 1)); x1 = int(min(size - 1, np.ceil(max(a[0], b[0], c[0])) + 1))
        y0 = int(max(0, np.floor(min(a[1], b[1], c[1])) - 1)); y1 = int(min(size - 1, np.ceil(max(a[1], b[1], c[1])) + 1))
        if x1 < x0 or y1 < y0: continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12: continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        l2 = 1 - l0 - l1
        eps = -0.75 / max(1.0, np.sqrt(abs(d)))        # ~1 texel of conservative dilation
        inside = (l0 >= eps) & (l1 >= eps) & (l2 >= eps)
        mask[y0:y1 + 1, x0:x1 + 1] |= inside
    return mask


def flip_mask(part, size):
    """Texels whose covering UV shell is mirrored w.r.t. the game's convention (-> invert green).

    Game convention (measured on vanilla meshes): with game-space winding and v-down UVs the UV
    signed area is POSITIVE, i.e. cross(N, T) = +dP/dv, and tangents carry no handedness flag.
    Shells with negative UV area therefore need their green channel inverted. Texels shared by
    both orientations (true mirrored overlap) are left alone (the majority wins)."""
    uv, tris = part.uv, part.tris
    d1 = uv[tris[:, 1]] - uv[tris[:, 0]]; d2 = uv[tris[:, 2]] - uv[tris[:, 0]]
    area = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    neg = area < 0; pos = area > 0
    m_pos = raster_mask(uv, tris, size, pos)
    m_neg = raster_mask(uv, tris, size, neg)
    flip = m_neg & ~m_pos
    stats = dict(tri_mirrored=int(neg.sum()), tri_regular=int(pos.sum()), texel_flip=round(float(flip.mean()), 4),
                 texel_conflict=round(float((m_pos & m_neg).mean()), 4))
    return flip, stats


def vertex_median(part, img, sel_img):
    """Median of img at the part's vertex UVs, restricted to vertices where sel_img is true."""
    size = img.shape[0]
    px = np.clip((part.uv * size).astype(int), 0, size - 1)
    v = img[px[:, 1], px[:, 0]]; m = sel_img[px[:, 1], px[:, 0]]
    return float(np.median(v[m])) if m.any() else None


def build_set(key, size=1024, preview=True):
    stem, part_name, is_helmet = SETS[key]
    D, S, N = load(stem, "D", size), load(stem, "S", size), load(stem, "N", size)
    lum = D.mean(2)
    metal = S[..., 1] / 255.0                                 # Fortnite S: R spec, G metal, B roughness
    srough = S[..., 2]
    if is_helmet:
        dark = np.clip((88.0 - lum) / 22.0, 0.0, 1.0)         # visor glass + black lining
    else:
        dark = np.zeros_like(lum)
    metal = metal * (1.0 - dark)
    # "beskar" = bare, unpainted metal: metallic AND colourless. Painted metal (the red-brown back plate)
    # and anything non-metal keep their own colour.
    sat = (D.max(2) - D.min(2)) / np.maximum(D.max(2), 1.0)
    beskar = metal * np.clip(1.0 - sat / FINISH["beskar_max_sat"], 0.0, 1.0)
    msel = beskar > 0.6
    gm = gltf_load.load(GLTF)
    part = [p for p in gm.parts if p.material.endswith(part_name)][0]
    med_lum = vertex_median(part, lum, msel) or 120.0          # what the plates actually show
    med_rough = vertex_median(part, srough, metal > 0.6) or 150.0

    # ---- _d ----
    # THE GAME SAMPLES A LOOSE ALBEDO CARRIER AS LINEAR (no sRGB decode). Seen in game twice: dark
    # leather (sRGB 40,32,29 = 2% reflectance) rendered as mid tan-grey (16%), and the flat-average
    # bandolier of the rev-2 build was far lighter than Boba's near-black shirt beside it. So:
    #   * everything that is not beskar is stored LINEARISED ((v/255)^2.2) and shows its true colour;
    #   * beskar keeps the code values the user has already seen and liked (~212, read as ~0.83
    #     reflectance = bright silver), re-centred with a soft power curve so painted panel lines
    #     and wear survive. Fortnite paints beskar as dark steel and relies on a stylised shader.
    safe = np.maximum(lum, 1.0)
    tgt = FINISH["beskar_target"] * (safe / med_lum) ** FINISH["beskar_contrast"]
    d_beskar = D * (np.clip(tgt, 0, 250) / safe)[..., None]
    d_true = 255.0 * (D / 255.0) ** 2.2 if FINISH["albedo_linear"] else D
    d = beskar[..., None] * d_beskar + (1.0 - beskar[..., None]) * d_true
    d = d * (1.0 - 0.9 * dark[..., None])                     # visor / black lining -> black
    d = np.clip(d, 0, 250)
    d_rgba = np.concatenate([np.rint(d), np.full((size, size, 1), 255.0)], 2).astype(np.uint8)

    # ---- _m ----
    k = float(FINISH["shine"])
    rough_src = np.clip(srough, 30, 245)                       # the model's own roughness
    rough_chrome = np.clip(FINISH["chrome_rough"] + 0.30 * (srough - med_rough), 72, 125)
    rough_metal = (1 - k) * rough_src + k * rough_chrome
    smooth_metal = (1 - k) * (255.0 - rough_src) + k * FINISH["chrome_smooth"]
    # Non-metal smoothness follows the donor's own textures (medians measured on the Stormtrooper _m:
    # rough 80 -> smooth ~210, 107 -> ~150, 130 -> ~124, 166 -> ~74, >185 -> ~15), i.e. about
    # 330 - 1.6*rough. Plain 255 - rough left rough cloth with a visible satin haze.
    smooth_non = np.clip(330.0 - 1.6 * rough_src, 0.0, 250.0)
    G = rough_src * (1.0 - metal) + rough_metal * metal
    A = smooth_non * (1.0 - metal) + smooth_metal * metal
    if is_helmet:
        G = G * (1.0 - dark) + FINISH["visor_rough"] * dark
        A = A * (1.0 - dark) + FINISH["visor_smooth"] * dark
    m_rgba = np.stack([metal * 255.0, G, np.full_like(G, FINISH["m_blue"]), A], 2)
    m_rgba = np.clip(m_rgba, 0, 255).astype(np.uint8)

    # ---- _n  (game layout: A = X, G = Y green-up, R = G, B = AO) ----
    flip, st = flip_mask(part, size)                           # UV shells mirrored vs the game convention
    nx = N[..., 0]                                              # Fortnite R = X (toward +u)
    ny_up = 255.0 - N[..., 1]                                   # Fortnite G is green-down -> green-up
    ny_up = np.where(flip, 255.0 - ny_up, ny_up)                # mirrored shells: Y back the other way
    ao = np.maximum(load(stem, "M", size)[..., 0], FINISH["ao_floor"])
    n_rgba = np.clip(np.stack([ny_up, ny_up, ao, nx], 2), 0, 255).astype(np.uint8)

    out = {}
    for chan, img in (("d", d_rgba), ("m", m_rgba), ("n", n_rgba)):
        fmt, tsize = CONTAINERS[key][chan]
        if tsize != size:
            img = np.asarray(Image.fromarray(img, "RGBA").resize((tsize, tsize), Image.BOX))
        rel = priv(key, chan)
        nbytes = bc.write_dds(os.path.join(STAGE, rel), img, fmt)
        back = bc.read_dds(os.path.join(STAGE, rel))
        nch = 3 if fmt == "DXT1" else 4
        err = float(np.abs(back[..., :nch] - img[..., :nch].astype(np.float64)).mean())
        out[chan] = (rel, f"{fmt} {tsize}² 1 level, {nbytes} B, encode error {err:.2f}/255")
        if preview:
            os.makedirs(WORK, exist_ok=True)
            Image.fromarray(np.clip(back[..., :3], 0, 255).astype(np.uint8)).resize((512, 512), Image.BILINEAR).save(os.path.join(WORK, f"carrier_{key}_{chan}.png"))
            if chan in ("m", "n"):
                Image.fromarray(np.clip(back[..., 3], 0, 255).astype(np.uint8)).resize((512, 512), Image.BILINEAR).save(os.path.join(WORK, f"carrier_{key}_{chan}_alpha.png"))
    info = dict(key=key, size=size, beskar_median_lum=round(med_lum, 1), beskar_median_rough=round(med_rough, 1), metal_frac=round(float(msel.mean()), 3),
                shine=k, metal_rough_mean=round(float(m_rgba[..., 1][msel].mean()), 1) if msel.any() else None,
                metal_smooth_mean=round(float(m_rgba[..., 3][msel].mean()), 1) if msel.any() else None,
                plate_rough=round(float(vertex_median(part, m_rgba[..., 1].astype(float), msel) or 0), 1),
                plate_smooth=round(float(vertex_median(part, m_rgba[..., 3].astype(float), msel) or 0), 1),
                n_alpha_mean=round(float(n_rgba[..., 3].mean()), 1), n_green_mean=round(float(n_rgba[..., 1].mean()), 1),
                n_ao_mean=round(float(n_rgba[..., 2].mean()), 1),
                metal_albedo_mean=round(float(d_rgba[..., :3][msel].mean()), 1) if msel.any() else None,
                dark_frac=round(float((dark > 0.5).mean()), 3), flip=st, files={c: o[0] for c, o in out.items()},
                containers={c: o[1] for c, o in out.items()})
    return info


if __name__ == "__main__":
    size = WORK_SIZE
    keys = []
    for a in sys.argv[1:]:
        if a.startswith("shine="): FINISH["shine"] = float(a[6:])
        elif a.startswith("beskar="): FINISH["beskar_target"] = float(a[7:])
        elif a.startswith("albedo_linear="): FINISH["albedo_linear"] = int(a[14:])
        else: keys.append(a)
    for key in (keys or list(SETS)):
        print(build_set(key, size))
