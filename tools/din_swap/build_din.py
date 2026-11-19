#!/usr/bin/env python3
"""
build_din.py — full-body Din Djarin model swap (Phase 2).

Rebuilds every Boba gear mesh the player wears from the Fortnite "Cosmos" Mandalorian (glTF):

  container (game .mmb)   submesh            <- Fortnite geometry                         textures
  helmet                  helmet_mesh        <- whole helmet                              Head
  vest                    vest_mesh          <- chest plate, back plate, pauldrons        Armor
                          cord_mesh          <- (hidden stub)
  shirt                   shirt_mesh         <- jacket, sleeves, neck seal, bandolier,    Body
                                                elbow pieces
  bracers                 bracers_mesh       <- gauntlets                                 Armor
  gloves                  gloves_mesh        <- gloves                                    Body
  pants                   pants_mesh         <- legs, knee pieces, shin cartridges        Body
                          acc_mesh           <- (hidden stub)
  boots                   metal_mesh         <- boots                                     Body
                          boots_mesh         <- (hidden stub)
  belt                    belt_mesh          <- belt pouches, holster, blaster            Body
                          metal_mesh/denim   <- (hidden stubs)
  pouches                 pouches_mesh       <- thigh plates                              Armor
  kneepads                both               <- (hidden stubs)
  (poncho = Boba's cloth cape, untouched: it is a cloth-sim prefab)

Why this split: each game .mmb only carries the bones of its own body region, and each submesh is
bound to one material file (= one texture set). Hidden stubs are a 1 mm triangle inside the chest.

Fit (Fortnite bind pose -> game bind pose). Every Fortnite joint belongs to a GROUP; each group has
one transform; a vertex is moved by the blend of its groups' transforms, weighted by its Fortnite
skin weights (so seams between segments stay closed):
  torso   affine  A + diag(sx,sy,sz)(p - a), anchored on the shoulder line
  head    the helmet's own placement (neck seal + cap ride with the helmet, pushed a little up into it)
  pelvis  translation onto the game's Hips
  limbs   per segment: rotate the source bone direction onto the game's, scale along the bone to the
          game's bone length, separate radial scale (arm, forearm, thigh, shin, foot)
  hand    frame-to-frame (wrist, knuckle direction, palm direction) + uniform scale

Weights: spine/neck/clavicle/fingers/foot by name; arm, forearm, thigh and shin by POSITION along
the game bone onto the game's twist helpers (root bone -> Twist1 at 1/3 -> Twist2 at 2/3), which is
how the vanilla meshes are weighted. Bones a container does not have fall back along the chain.

Usage: python3 -I build_din.py [param=value ...]
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gltf_load   # noqa: E402
import meshutil    # noqa: E402
import mmbio       # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
GLTF = os.path.join(ROOT, "downloaded_models/extracted/fortnite_gltf_pkg/source_unzipped/scene.gltf")
CONT = os.path.join(ROOT, "local/din_swap/containers")          # vanilla copies of the Hunter exports
REF_HELMET = os.path.join(ROOT, "local/mesh_edit/helmet_v6_forcelod0.mmb")      # shipped (user-tuned) footprint
WORK = os.path.join(ROOT, "local/din_swap/work")
STAGE = os.path.join(ROOT, "local/din_swap/staging")
CH = "helix/baked/art/characters/characters"

STUB = None
CONTAINERS = {   # name -> (vanilla source, game path, {submesh: region or STUB})
    "helmet":   (os.path.join(ROOT, "local/mesh_edit/helmet_ORIGINAL.mmb"),
                 f"{CH}/chr_headwear/chr_headw_5_canon_boba_fett_helmet/chr_headw_5_canon_boba_fett_helmet.mmb", {"helmet_mesh": "helmet"}),
    "vest":     (f"{CONT}/vest.mmb", f"{CH}/chr_top/chr_top_5_canon_boba_fett_vest/chr_top_5_canon_boba_fett_vest.mmb",
                 {"vest_mesh": "torso_armor", "cord_mesh": STUB}),
    "shirt":    (f"{CONT}/shirt.mmb", f"{CH}/chr_top/chr_top_5_canon_boba_fett_shirt/chr_top_5_canon_boba_fett_shirt.mmb",
                 {"shirt_mesh": "upper"}),
    "bracers":  (f"{CONT}/bracers.mmb", f"{CH}/chr_accessories/chr_acc_5_canon_boba_fett_bracers/chr_acc_5_canon_boba_fett_bracers.mmb",
                 {"bracers_mesh": "gauntlets"}),
    "gloves":   (f"{CONT}/gloves.mmb", f"{CH}/chr_accessories/chr_acc_5_canon_boba_fett_gloves/chr_acc_5_canon_boba_fett_gloves.mmb",
                 {"gloves_mesh": "hands"}),
    "pants":    (f"{CONT}/pants.mmb", f"{CH}/chr_bottom/chr_botm_5_canon_boba_fett_pants/chr_botm_5_canon_boba_fett_pants.mmb",
                 {"pants_mesh": "legs", "acc_mesh": STUB}),
    "boots":    (f"{CONT}/boots.mmb", f"{CH}/chr_bottom/chr_botm_5_canon_boba_fett_boots/chr_botm_5_canon_boba_fett_boots.mmb",
                 {"metal_mesh": "feet", "boots_mesh": STUB}),
    "belt":     (f"{CONT}/belt.mmb", f"{CH}/chr_top/chr_top_5_canon_boba_fett_belt/chr_top_5_canon_boba_fett_belt.mmb",
                 {"belt_mesh": "hips", "metal_mesh": STUB, "denim_mesh": STUB}),
    "pouches":  (f"{CONT}/pouches.mmb", f"{CH}/chr_accessories/chr_acc_5_canon_boba_fett_pouches/chr_acc_5_canon_boba_fett_pouches.mmb",
                 {"pouches_mesh": "thighs"}),
    "kneepads": (f"{CONT}/kneepads.mmb", f"{CH}/chr_accessories/chr_acc_5_canon_boba_fett_kneepads/chr_acc_5_canon_boba_fett_kneepads.mmb",
                 {"kneepads_mesh": STUB, "kneepads_acc_mesh": STUB}),
}
REGION_TEX = {"helmet": "Head", "torso_armor": "Armor", "gauntlets": "Armor", "thighs": "Armor",
              "upper": "Body", "hands": "Body", "legs": "Body", "feet": "Body", "hips": "Body"}

# ---- fit parameters (tunable from the command line: key=value) ------------------------------
P = dict(
    helmet_scale=None,        # None = match the shipped helmet's width
    helmet_dy=0.0, helmet_dz=0.0,
    torso_sx=1.00, torso_sy=1.12, torso_sz=1.10,
    torso_zc_src=-0.017,      # depth centre of the Fortnite torso
    torso_zc_dst=-0.040,      # depth centre in game space (keeps the source's helmet-to-chest relation)
    neck_raise=0.030,         # neck seal top is pushed this far up into the (closed, empty) helmet
    arm_radial=1.0,           # girth factors relative to each segment's length scale
    fore_radial=0.92,         # game forearm is 20% longer than Fortnite's; keep the gauntlet from ballooning
    thigh_radial=1.0, calf_radial=1.0,
    hand_scale=None,          # None = knuckle-distance ratio
    acc_lift=0.004,           # bandolier / cartridges are raised this far off the surface they lie on
    foot_lift=0.010,          # raise the soles to the game's ground plane (vanilla boot soles sit at y ~ +0.003)
)

SIDES = {"l": "Left", "r": "Right"}


# ------------------------------------------------------------------------------------------------
# Fortnite joint naming
# ------------------------------------------------------------------------------------------------
def base(n):
    """Strip Sketchfab's single numeric suffix: 'spine_05_08' -> 'spine_05'."""
    parts = n.split("_")
    if len(parts) > 1 and parts[-1].isdigit():
        parts = parts[:-1]
    return "_".join(parts)


def core_side(n):
    """base name -> (core without side / _end / _MSTR, side 'l'|'r'|None)."""
    toks = [t for t in n.split("_") if t not in ("end", "MSTR")]
    side = "l" if "l" in toks else "r" if "r" in toks else None
    return "_".join(t for t in toks if t not in ("l", "r")), side


def joint_group(n):
    """Which fit transform a Fortnite joint rides on. Returns a group key."""
    c, side = core_side(n)
    if c == "pelvis": return "pelvis"
    if c in ("neck_01", "neck_02", "head", "dyn_helmet", "head_alt"): return "head"
    if c.startswith(("upperarm", "deform_deltoid", "deform_elbow_fr", "dyn_shoulderpad")): return "arm_" + side
    if c.startswith(("lowerarm", "deform_elbow_bk", "dyn_gauntlet")): return "fore_" + side
    if c.startswith(("hand", "index", "middle", "ring", "pinky", "thumb")): return "hand_" + side
    if c.startswith(("dyn_holster", "dyn_blaster")): return "thigh_r"      # holster hangs off the right thigh
    if c.startswith(("thigh", "deform_thigh")): return "thigh_" + side
    if c.startswith(("calf", "deform_knee")): return "calf_" + side
    if c.startswith(("foot", "ball")): return "foot_" + side
    return "torso"        # spine, clavicle, pectoral, root, cape/backpack


GROUPS = ["torso", "head", "pelvis"] + [f"{g}_{s}" for g in ("arm", "fore", "hand", "thigh", "calf", "foot") for s in "lr"]


def group_weights(g, pt):
    """(N, len(GROUPS)) Fortnite skin weight per fit group."""
    gi = np.array([GROUPS.index(joint_group(base(n))) for n in g.joint_names])
    W = np.zeros((len(pt.pos), len(GROUPS)))
    for s in range(pt.joints.shape[1]):
        np.add.at(W, (np.arange(len(pt.pos)), gi[pt.joints[:, s]]), pt.weights[:, s])
    return W


# ------------------------------------------------------------------------------------------------
# geometry helpers
# ------------------------------------------------------------------------------------------------
def rot_between(a, b):
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(a @ b)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def frame(a1, a2):
    """Orthonormal frame (columns) from a primary axis and a secondary direction."""
    x = a1 / np.linalg.norm(a1)
    y = a2 - x * (a2 @ x); y /= np.linalg.norm(y)
    return np.stack([x, y, np.cross(x, y)], 1)


def idx_components(n, tris):
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for a, b, c in tris:
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
        ra, rc = find(a), find(c)
        if ra != rc: parent[rc] = ra
    return np.array([find(i) for i in range(n)])


# ------------------------------------------------------------------------------------------------
# the fit
# ------------------------------------------------------------------------------------------------
class Fit:
    def __init__(self, g, U, helmet_xf):
        """g: Fortnite model; U: union game skeleton {bone: 4x4 world bind}; helmet_xf: (scale, src_c, dst_c)."""
        self.g, self.U = g, U
        self.h_s, self.h_src, self.h_dst = helmet_xf
        J = {base(n): g.joint_pos[k] for k, n in enumerate(g.joint_names)}
        self.J = J
        Bp = lambda n: U[n][:3, 3]
        sh_src = 0.5 * (J["upperarm_l"] + J["upperarm_r"]); sh_dst = 0.5 * (Bp("LeftArm") + Bp("RightArm"))
        self.a = np.array([0.0, sh_src[1], P["torso_zc_src"]])
        self.A = np.array([0.0, sh_dst[1], P["torso_zc_dst"]])
        self.pelvis_src, self.pelvis_dst = J["pelvis"], Bp("Hips")
        self.seg = {}
        for s, S in SIDES.items():
            for key, (j0, j1, B0, B1, radial) in {
                "arm": (f"upperarm_{s}", f"lowerarm_{s}", f"{S}Arm", f"{S}ForeArm", P["arm_radial"]),
                "fore": (f"lowerarm_{s}", f"hand_{s}", f"{S}ForeArm", f"{S}Hand", P["fore_radial"]),
                "thigh": (f"thigh_{s}", f"calf_{s}", f"{S}UpLeg", f"{S}Leg", P["thigh_radial"]),
                "calf": (f"calf_{s}", f"foot_{s}", f"{S}Leg", f"{S}Foot", P["calf_radial"]),
                "foot": (f"foot_{s}", f"ball_{s}", f"{S}Foot", f"{S}ToeBase", 1.0),
            }.items():
                p0, p1, Q0, Q1 = J[j0], J[j1], Bp(B0), Bp(B1)
                ax = (p1 - p0) / np.linalg.norm(p1 - p0)
                self.seg[f"{key}_{s}"] = dict(p0=p0, Q0=Q0, Q1=Q1, ax=ax, R=rot_between(p1 - p0, Q1 - Q0),
                                              s=float(np.linalg.norm(Q1 - Q0) / np.linalg.norm(p1 - p0)), radial=radial,
                                              lift=np.array([0.0, P["foot_lift"] if key == "foot" else 0.0, 0.0]))
            # hand: frame-to-frame
            Fs = frame(J[f"middle_01_{s}"] - J[f"hand_{s}"], J[f"index_01_{s}"] - J[f"pinky_01_{s}"])
            Fd = frame(Bp(f"{S}HandMiddle1") - Bp(f"{S}Hand"), Bp(f"{S}HandIndex1") - Bp(f"{S}HandPinky1"))
            hs = P["hand_scale"] or float(np.linalg.norm(Bp(f"{S}HandMiddle1") - Bp(f"{S}Hand")) / np.linalg.norm(J[f"middle_01_{s}"] - J[f"hand_{s}"]))
            self.seg[f"hand_{s}"] = dict(p0=J[f"hand_{s}"], Q0=Bp(f"{S}Hand"), R=Fd @ Fs.T, s=hs, hand=True)

    # ---- per-group point / normal transforms ----
    def xf(self, key, p, n):
        if key == "torso":
            q = p - self.a
            S = np.array([P["torso_sx"], P["torso_sy"], P["torso_sz"]])
            return self.A + q * S, n / S
        if key == "head":
            return self.h_dst + self.h_s * (p - self.h_src) + np.array([0.0, P["neck_raise"], 0.0]), n
        if key == "pelvis":
            return self.pelvis_dst + (p - self.pelvis_src), n
        sg = self.seg[key]
        q = p - sg["p0"]
        if sg.get("hand"):
            return sg["Q0"] + sg["s"] * q @ sg["R"].T, n @ sg["R"].T
        ax = sg["ax"]
        along = (q @ ax)[:, None] * ax[None, :]
        q2 = sg["s"] * along + sg["s"] * sg["radial"] * (q - along)
        nal = (n @ ax)[:, None] * ax[None, :]
        n2 = nal + (n - nal) / sg["radial"]
        return sg["Q0"] + q2 @ sg["R"].T + sg["lift"], n2 @ sg["R"].T

    def apply(self, pt, idx, W):
        p, n = pt.pos[idx], pt.nrm[idx]
        Wv = W[idx]
        P_ = np.zeros_like(p); N_ = np.zeros_like(n)
        for gi, key in enumerate(GROUPS):
            w = Wv[:, gi:gi + 1]
            if not (w > 0).any():
                continue
            pp, nn = self.xf(key, p, n)
            P_ += w * pp; N_ += w * nn
        N_ /= np.maximum(np.linalg.norm(N_, axis=1, keepdims=True), 1e-12)
        return P_, N_


# ------------------------------------------------------------------------------------------------
# weights: Fortnite joints -> game bones
# ------------------------------------------------------------------------------------------------
DIRECT = {"pelvis": "Hips", "root": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2",
          "spine_04": "Spine3", "spine_05": "Spine3", "neck_01": "Neck", "neck_02": "Neck1", "head": "Head",
          "dyn_helmet": "Head", "head_alt": "Head"}
FINGER = {"index": "Index", "middle": "Middle", "ring": "Ring", "pinky": "Pinky", "thumb": "Thumb"}
CHAINS = {   # positional chains: bone at t=0, 1/3, 2/3..1 along the game segment
    "arm": ("RFX_D_{S}_Shoulder", "D_RFX_{S}_Arm_Twist1", "D_RFX_{S}_Arm_Twist2"),
    "fore": ("{S}ForeArm", "D_RFX_{S}_ForeArm_Twist1", "D_RFX_{S}_ForeArm_Twist2"),
    "thigh": ("{S}UpLeg", "D_RFX_{S}_UpLeg_Twist1", "D_RFX_{S}_UpLeg_Twist2"),
    "calf": ("{S}Leg", "D_RFX_{S}_Leg_Twist1", "D_RFX_{S}_Leg_Twist2"),
}


def fallback(b):
    """Next bone to try when a container's skeleton does not have `b`."""
    S = "Left" if "Left" in b else "Right" if "Right" in b else ""
    t = {
        f"D_RFX_{S}_Arm_Twist2": f"D_RFX_{S}_Arm_Twist1", f"D_RFX_{S}_Arm_Twist1": f"RFX_D_{S}_Shoulder",
        f"RFX_D_{S}_Shoulder": f"{S}Arm", f"{S}Arm": f"{S}Shoulder", f"{S}Shoulder": "Spine3",
        f"D_RFX_{S}_ForeArm_Twist2": f"D_RFX_{S}_ForeArm_Twist1", f"D_RFX_{S}_ForeArm_Twist1": f"{S}ForeArm",
        f"{S}ForeArm": f"D_RFX_{S}_Arm_Twist2", f"{S}Hand": f"D_RFX_{S}_ForeArm_Twist2",
        f"D_RFX_{S}_UpLeg_Twist2": f"D_RFX_{S}_UpLeg_Twist1", f"D_RFX_{S}_UpLeg_Twist1": f"{S}UpLeg", f"{S}UpLeg": "Hips",
        f"D_RFX_{S}_Leg_Twist1": f"{S}Leg", f"D_RFX_{S}_Leg_Twist2": f"D_RFX_{S}_Leg_Twist1",
        f"{S}Leg": f"D_RFX_{S}_UpLeg_Twist2", f"{S}Foot": f"D_RFX_{S}_Leg_Twist2", f"{S}ToeBase": f"{S}Foot",
        "Head": "Neck1", "Neck1": "Neck", "Neck": "Spine3", "Spine3": "Spine2", "Spine2": "Spine1", "Spine1": "Spine",
        "Spine": "Hips",
    }
    if b in t:
        return t[b]
    if S and "Hand" in b and b != f"{S}Hand":
        return f"{S}Hand"                      # any finger bone -> the hand
    return None


def resolve(b, have):
    seen = 0
    while b not in have:
        b = fallback(b); seen += 1
        if b is None or seen > 12:
            return "Hips"
    return b


def to_container(named, have, bone_index):
    """[{bone name: w}] -> [[(container bone index, w)]] with fallbacks for bones the container lacks."""
    out = []
    for acc in named:
        res = {}
        for b, w in acc.items():
            r = resolve(b, have); res[r] = res.get(r, 0) + w
        tot = sum(res.values())
        out.append([(bone_index[b], w / tot) for b, w in res.items() if w / tot > 1e-4])
    return out


def map_weights(g, pt, idx, pos_new, fit, pauldron_w):
    """Fortnite skin weights -> game bone NAMES (container-independent). Returns [{bone: w}]."""
    names = [base(n) for n in g.joint_names]
    info = [(core_side(n), joint_group(n)) for n in names]
    out = []
    for row, v in enumerate(idx):
        acc = {}
        seg_w = {}
        for s in range(pt.joints.shape[1]):
            w = pt.weights[v, s]
            if w <= 0: continue
            j = pt.joints[v, s]
            (c, side), grp = info[j]
            S = SIDES.get(side, "")
            if c.startswith("dyn_shoulderpad"):
                for b, k in pauldron_w[side].items(): acc[b] = acc.get(b, 0) + w * k
            elif c in DIRECT:
                acc[DIRECT[c]] = acc.get(DIRECT[c], 0) + w
            elif c.startswith(("clavicle", "deform_pectoral")):
                acc[f"{S}Shoulder"] = acc.get(f"{S}Shoulder", 0) + w
            elif grp.startswith("hand"):
                toks = c.split("_")
                if toks[0] == "hand":
                    b = f"{S}Hand"
                elif toks[1] == "metacarpal":
                    b = f"{S}InHand{FINGER[toks[0]]}"
                else:
                    b = f"{S}Hand{FINGER[toks[0]]}{int(toks[1])}"
                acc[b] = acc.get(b, 0) + w
            elif grp.startswith("foot"):
                b = f"{S}Foot" if c.startswith("foot") else f"{S}ToeBase"
                acc[b] = acc.get(b, 0) + w
            elif grp.split("_")[0] in CHAINS:
                seg_w[grp] = seg_w.get(grp, 0) + w          # positional, resolved below
            else:
                acc["Spine3"] = acc.get("Spine3", 0) + w     # cape/backpack leftovers ride the chest
        for grp, w in seg_w.items():
            kind, side = grp.split("_")
            sg = fit.seg[grp]; S = SIDES[side]
            axis = sg["Q1"] - sg["Q0"]
            t = float(np.clip((pos_new[row] - sg["Q0"]) @ axis / (axis @ axis), 0.0, 1.0))
            b0, b1, b2 = (x.format(S=S) for x in CHAINS[kind])
            if t <= 1 / 3:
                k = t * 3; parts = {b0: 1 - k, b1: k}
            elif t <= 2 / 3:
                k = (t - 1 / 3) * 3; parts = {b1: 1 - k, b2: k}
            else:
                parts = {b2: 1.0}
            for b, k in parts.items():
                if k > 0: acc[b] = acc.get(b, 0) + w * k
        tot = sum(acc.values())
        out.append({b: w / tot for b, w in acc.items()})
    return out


def ride_surface(acc_pos, surf_pos, surf_nrm, surf_named, lift, k=3):
    """Chest accessories (bandolier, cartridges) take the weights of the surface they lie on.

    In the source they have their own spine/clavicle weights; on the game rig that put the upper strap
    99% on Spine3 above a chest plate that is 71% Spine3 / 29% lower spine, with ~5 mm of clearance,
    so any spine bend slid the strap under the plate (seen in game). Copying the weights of the k
    nearest surface vertices (plates + jacket) makes each accessory vertex move exactly with what is
    underneath it; `lift` raises it along that surface's normal for a little extra clearance."""
    named = []; offs = np.zeros_like(acc_pos)
    for i, p in enumerate(acc_pos):
        d = np.linalg.norm(surf_pos - p, axis=1)
        nn = np.argpartition(d, k)[:k]
        wts = 1.0 / (d[nn] + 1e-4); wts /= wts.sum()
        acc = {}
        for j, wj in zip(nn, wts):
            for b, w in surf_named[j].items(): acc[b] = acc.get(b, 0) + wj * w
        named.append(acc)
        offs[i] = surf_nrm[nn[np.argmin(d[nn])]] * lift
    return named, acc_pos + offs


def reference_pauldron_weights():
    """Average bone weights of Boba's own shoulder plates (how the game rigs a shoulder plate)."""
    a = mmbio.parse_header(f"{CONT}/vest.mmb")
    names = [b.name for b in a.bones]
    d = mmbio.read_lod(a, [m.name for m in a.meshes].index("vest_mesh"), 0)
    comp = meshutil.components(d.pos, d.tris, 1e-4)
    res = {}
    for side, sign in (("l", -1), ("r", 1)):
        best = None
        for c in range(comp.max() + 1):
            m = comp == c
            if m.sum() > 100 and d.pos[m].mean(0)[0] * sign > 0.2:
                best = m
        acc = {}
        for s in range(d.bw.shape[1]):
            for j, w in zip(d.bi[best, s], d.bw[best, s]):
                if w > 0: acc[names[j]] = acc.get(names[j], 0) + w
        tot = sum(acc.values())
        acc = {k: v / tot for k, v in acc.items() if v / tot >= 0.02}
        tot = sum(acc.values())
        res[side] = {k: v / tot for k, v in acc.items()}
    return res


# ------------------------------------------------------------------------------------------------
# which geometry goes to which region
# ------------------------------------------------------------------------------------------------
def classify(g):
    """Returns ({part: per-vertex region string array ('' = unused)},
                {part: per-vertex bool 'chest accessory' = bandolier + cartridges}).

    Chest accessories lie on the chest and back plates and are re-weighted to the surface under them
    (see ride_surface)."""
    out = {}; chest_acc = {}
    names = [base(n) for n in g.joint_names]
    grp = [joint_group(n) for n in names]
    kind = np.array([k.split("_")[0] for k in grp])
    core = [core_side(n)[0] for n in names]
    for pt in g.parts:
        nm = pt.material.replace("M_MED_Cosmos_", "")
        reg = np.full(len(pt.pos), "", dtype=object)
        acc_mask = np.zeros(len(pt.pos), bool)
        if nm == "Head":
            reg[:] = "helmet"
        elif nm in ("Armor", "Body"):
            comp = meshutil.components(pt.pos, pt.tris)
            shell = idx_components(len(pt.pos), pt.tris)

            def frac(mask):
                f = {}
                for s in range(pt.joints.shape[1]):
                    for j in np.unique(pt.joints[mask, s]):
                        w = pt.weights[mask, s][pt.joints[mask, s] == j].sum()
                        k = kind[j]
                        if core[j].startswith(("dyn_holster", "dyn_blaster")): k = "pelvis"
                        f[k] = f.get(k, 0) + w
                return f
            for c in range(comp.max() + 1):
                m = comp == c
                # the one-piece body suit (island 0) is split per UV shell; everything else per island
                pieces = [shell == s for s in np.unique(shell[m])] if (nm == "Body" and c == 0) else [m]
                for pm in pieces:
                    f = frac(pm)
                    g_ = lambda *ks: sum(f.get(k, 0) for k in ks)
                    if nm == "Armor":
                        score = {"gauntlets": g_("fore", "hand"), "thighs": g_("thigh", "calf"),
                                 "torso_armor": g_("torso", "head", "arm", "pelvis")}
                    else:
                        score = {"hands": g_("hand"), "feet": g_("foot"), "hips": g_("pelvis"),
                                 "legs": g_("thigh", "calf"), "upper": g_("torso", "head", "arm", "fore")}
                    reg[pm] = max(score, key=score.get)
                    if nm == "Body" and c != 0 and reg[pm][0] == "upper" and g_("arm", "fore") < 0.05 * max(sum(f.values()), 1e-9):
                        acc_mask[pm] = True
        out[nm] = reg; chest_acc[nm] = acc_mask
    return out, chest_acc


def make_geom(pos, nrm, uv, tris, weights):
    uvc = np.clip(uv, 0.0, 1.0)
    tan, _sign = meshutil.tangents(pos, nrm, uvc, tris)
    uv1 = np.stack([uvc[:, 0] * 0.125, 0.125 + uvc[:, 1] * 0.125], 1)     # exactly the vanilla relation
    return mmbio.NewGeom(pos, nrm, tan, np.ones(len(pos)), uvc, tris, weights, uv1)


def stub_geom(hips_index):
    """A 1 mm triangle inside the chest: hides a submesh we do not use."""
    c = np.array([0.0, 1.22, -0.045])
    pos = c + np.array([[0, 0, 0], [0.001, 0, 0], [0, 0.001, 0]])
    nrm = np.tile([0.0, 0.0, 1.0], (3, 1))
    uv = np.array([[0.5, 0.5], [0.501, 0.5], [0.5, 0.501]])
    return make_geom(pos, nrm, uv, np.array([[0, 1, 2]]), [[(hips_index, 1.0)]] * 3)


def build():
    g = gltf_load.load(GLTF)
    parts = {pt.material.replace("M_MED_Cosmos_", ""): pt for pt in g.parts}
    regions, chest_acc = classify(g)

    # ---- union game skeleton ----
    U = {}
    cont = {}
    for name, (src, rel, slots) in CONTAINERS.items():
        a = mmbio.parse_header(src)
        bn, bp, bl, bw = mmbio.bone_tables(a)
        for i, n in enumerate(bn):
            U.setdefault(n, bw[i])
        cont[name] = (a, bn)

    # ---- helmet placement ----
    hp = parts["Head"]
    dref = mmbio.read_lod(mmbio.parse_header(REF_HELMET), 0, 0)
    rmin, rmax = dref.pos.min(0), dref.pos.max(0)
    smin, smax = hp.pos.min(0), hp.pos.max(0)
    hs = P["helmet_scale"] or float((rmax[0] - rmin[0]) / (smax[0] - smin[0]))
    rc = 0.5 * (rmin + rmax); sc = 0.5 * (smin + smax)
    dst_c = np.array([0.0, rc[1] + P["helmet_dy"], rc[2] + P["helmet_dz"]])
    src_c = np.array([0.0, sc[1], sc[2]])

    fit = Fit(g, U, (hs, src_c, dst_c))
    pauldron_w = reference_pauldron_weights()
    GW = {nm: group_weights(g, pt) for nm, pt in parts.items()}
    report = {"params": P, "containers": {}, "slot_textures": {}}
    geom_dump = {}

    # ---- pre-pass: fitted geometry + bone-name weights for every region ----
    R = {}
    for region, tex in REGION_TEX.items():
        if region == "helmet": continue
        pt = parts[tex]
        idx, tris = meshutil.submesh(regions[tex] == region, pt.tris)
        pos, nrm = fit.apply(pt, idx, GW[tex])
        R[region] = dict(pt=pt, idx=idx, tris=tris, pos=pos, nrm=nrm, named=map_weights(g, pt, idx, pos, fit, pauldron_w))
    up = R["upper"]; am = chest_acc["Body"][up["idx"]]
    plates = R["torso_armor"]
    surf_pos = np.concatenate([plates["pos"], up["pos"][~am]])
    surf_nrm = np.concatenate([plates["nrm"], up["nrm"][~am]])
    surf_named = plates["named"] + [n for n, a_ in zip(up["named"], am) if not a_]
    acc_named, acc_pos = ride_surface(up["pos"][am], surf_pos, surf_nrm, surf_named, P["acc_lift"])
    ai = np.where(am)[0]
    for k_, i in enumerate(ai):
        up["named"][i] = acc_named[k_]
    up["pos"][ai] = acc_pos
    report["chest_accessory_verts"] = int(am.sum())

    for name, (src, rel, slots) in CONTAINERS.items():
        a, bn = cont[name]
        have = set(bn); bone_index = {n: i for i, n in enumerate(bn)}
        mi = {m.name: m.index for m in a.meshes}
        assert set(slots) == set(mi), f"{name}: submeshes {sorted(mi)} != planned {sorted(slots)}"
        out = os.path.join(STAGE, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cur = src; tmp_i = 0
        crep = {}
        for slot, region in slots.items():
            if region is STUB:
                geo = stub_geom(bone_index["Hips"]); crep[slot] = "hidden stub"
            elif region == "helmet":
                hpos = dst_c + hs * (hp.pos - src_c)
                geo = make_geom(hpos, hp.nrm, hp.uv, hp.tris, None)
                crep[slot] = dict(source="Head", verts=len(hpos), tris=len(hp.tris), bbox=[hpos.min(0).round(3).tolist(), hpos.max(0).round(3).tolist()])
                geom_dump[f"{name}/{slot}"] = geo
            else:
                tex = REGION_TEX[region]; rg = R[region]
                pt, idx, tris, pos, nrm = rg["pt"], rg["idx"], rg["tris"], rg["pos"], rg["nrm"]
                w = to_container(rg["named"], have, bone_index)
                geo = make_geom(pos, nrm, pt.uv[idx], tris, w)
                used = sorted({bn[b] for r in w for b, _ in r})
                crep[slot] = dict(source=tex, region=region, verts=len(pos), tris=len(tris), max_influences=max(len(r) for r in w),
                                  bbox=[pos.min(0).round(3).tolist(), pos.max(0).round(3).tolist()], bones_used=used)
                geom_dump[f"{name}/{slot}"] = geo
            if region is not STUB:
                report["slot_textures"][f"{rel}::{slot}"] = REGION_TEX[region]
            nxt = out + f".tmp{tmp_i}"; tmp_i += 1
            extra = mmbio.replace_lod0(cur, nxt, mi[slot], geo, force_lod0=True, pos_scale=4)
            if extra and isinstance(crep[slot], dict):
                crep[slot]["extra_bindings"] = [bn[b] for b in extra]
            if cur != src: os.remove(cur)
            cur = nxt
        os.replace(cur, out)
        crep["_file"] = rel; crep["_bytes"] = os.path.getsize(out)
        report["containers"][name] = crep
    json.dump(report, open(os.path.join(WORK, "build_report.json"), "w"), indent=1)
    return report, geom_dump


if __name__ == "__main__":
    np.set_printoptions(precision=3, suppress=True)
    for arg in sys.argv[1:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            assert k in P, f"unknown param {k}"
            P[k] = None if v == "None" else float(v)
    rep, _ = build()
    for name, c in rep["containers"].items():
        print(f"{name}: {c['_bytes']} B")
        for slot, d in c.items():
            if slot.startswith("_"): continue
            if isinstance(d, str): print(f"   {slot:20s} {d}")
            else:
                print(f"   {slot:20s} {d['source']:5s} {d.get('region',''):12s} {d['verts']:5d} v {d['tris']:5d} t  infl<={d.get('max_influences', 1)}  bbox {d['bbox'][0]} .. {d['bbox'][1]}" + (f"  +bindings {d['extra_bindings']}" if d.get('extra_bindings') else ""))
