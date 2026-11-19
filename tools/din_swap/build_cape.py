#!/usr/bin/env python3
"""
build_cape.py — give Din a real, cloth-simulated back cape by borrowing one that already exists in
the game: the Canto Bight police cape (`chr_acc_2_silver_canto_police_cape`).

Why borrow: a cape's simulation (particles, constraints, and the binding of every render vertex to
the sim cage) lives in its `.mcloth`, which cannot be authored, so Din's own cape mesh can never get
cloth physics. But the character's gear list is plain text, and each entry is just a path to a gear
graph — so the cape slot can point at any existing cape, which brings its own mesh, material,
cloth file and collision shapes. The Canto cape is rigged to the same bind skeleton as the Boba gear
(bind matrices identical), is symmetric, and hangs from both shoulders to the calves.

Staged files (nothing touches the game; deploy_din.py does that):
  1. character_visuals_player.mcharactervisuals — the base mod's file with two edits:
     the poncho entry now loads the Canto cape's gear graph, and the head entry is removed
     (see drop_gear_entry: this is how the bare head is hidden, for the player only).
  2. the Canto cape .mmb with its CLOTH_RENDER submesh forced to LOD0 (same in-place float edit that
     fixed "cape freezes at distance" for the poncho; its LOD thresholds are even tighter), and its
     cloth freed up (see free_cape).
  3. the Canto cape material recoloured (denim recipe from v1.2: Color A/B = colour, Fuzz/Weft/Fade
     = 0.7 x colour; same-length float edits).
  NOTE: 2 and 3 override the cape's own vanilla paths, so Canto Bight police NPCs get the same colour
  and always-full-detail capes. Harmless, but it is a side effect outside the player character.

Usage: python3 build_cape.py [cape_color=r,g,b]   (linear; default = the v1.2 cape colour)
"""
import os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
sys.path.insert(0, os.path.join(HERE, ".."))
import matconst  # noqa: E402

SRC = os.path.join(ROOT, "local/din_swap/containers/cape")
# Output root. DIN_CAPE_STAGE redirects the four cape files into another tree (the release packager uses
# this to write a release-configured cape into dist/ without touching the dev staging tree).
STAGE = os.environ.get("DIN_CAPE_STAGE") or os.path.join(ROOT, "local/din_swap/staging")
VISUALS_REL = "helix/game system data/juice/character/character_visuals_player.mcharactervisuals"
OLD_GRAPH = b"helix/graph objects/gear/chr_acc_5_canon_boba_fett_poncho.mgraphobject"
NEW_GRAPH = b"helix/graph objects/gear/chr_acc_2_silver_canto_police_cape.mgraphobject"
# The base mod's gear list gives the player a generic human head. It must not show (it pokes through
# Din's helmet). v1.2 / v2.0 hid it with a 0-byte override AT THIS PATH — but many NPCs load the same
# head graph, so they all lost their heads. From v2.1 the entry is removed from the player's list instead
# and nothing is shipped at this path.
HEAD_GRAPH = b"helix/graph objects/gear/chr_head_2_silver_human_sea_m_001.mgraphobject"
MMB_REL = "helix/baked/art/characters/characters/chr_accessories/chr_acc_2_silver_canto_police_cape/chr_acc_2_silver_canto_police_cape.mmb"
MCLOTH_REL = MMB_REL[:-4] + ".mcloth"
MAT_REL = "helix/materials/mat_chr_acc_2_silver_canto_police_cape_denim.mmaterial"
CAPE_COLOR = [0.150, 0.062, 0.028]          # the rusty brown the user settled on for the cape in v1.2
# Cloth behaviour (see free_cape): the Canto cape is authored as a cheap NPC cape.
CAPE = dict(freedom_gain=10.2,   # .mmb sim-freedom channel x this (25 -> 255) — NOT read by the game (rev 7), kept for consistency
            leg_follow=0.5,      # fraction of the lower cape's thigh-bone weight that is kept (rest -> Hips)
            max_dist=0.40,       # .mcloth: max distance (m) a particle may stray, from free_bottom down (vanilla 0.039)
            limit_radius=1,      # .mcloth: 1 = also raise the limit radius in the settings blocks (rev 9, untested in game);
                                 #          0 = table only = exactly rev 8, the build the user confirmed (used for releases)
            free_top=1.15,       # .mcloth: above this height (m, bind pose) the vanilla max distance is kept (back plate zone)
            free_bottom=0.80,    # .mcloth: at/below this height (upper thigh) max_dist applies; smooth ramp between
            neck_fit=1,          # 1 = move the upper cape out so it lies ON Din's back plate / bandolier (see fit_cape)
            neck_margin=0.008,   # clearance (m) kept between the cape and the body surface underneath
            neck_reach=0.09)     # radius (m) over which a local push-out fades into the untouched cape
LEG_KEYS = ("UpLeg", "Leg", "Butt", "Hips_")
PRIMARY, SECONDARY = ("Color A", "Color B"), ("Fuzz Color", "Weft Color", "Fade Color")


def free_cape(path):
    """In-place edits (same file length) that turn the Canto cape from 'dragged by the legs' into cloth.

    Measured on the exported meshes — the CLOTH_SIM submesh's vertex colour RED is the per-particle
    simulation freedom (0 = pinned to the skinned position, 255 = free):
        Boba poncho (flowed well):  0 at the shoulder -> 255 at the hem, no leg-bone weights at all
        Vader / Lando capes:        0 at the neck -> 255 almost immediately
        Canto police cape:          0 at the neck -> 25, then CAPPED AT 25 for the lower 70 %,
                                    with the lower half 75-97 % weighted to the thigh bones
    i.e. it can stray ~10 % from a skinned position that follows the thighs: "glued to the shins,
    snaps forward through the calves, minor physics" (the user's description in game).
    1. freedom: red x freedom_gain (clipped) on the sim mesh -> 255 over the lower cape, pins unchanged.
    2. leg following: on sim + render LOD0, (1 - leg_follow) of each vertex's leg-bone weight moves to
       Hips, so the skinned base swings with the legs half as much.
    Whether the game reads these from the .mmb at runtime or from values baked into the .mcloth is NOT
    known yet — this build is the test."""
    import struct
    import numpy as np
    sys.path.insert(0, HERE)
    import mmbio
    a = mmbio.parse_header(path); buf = bytearray(open(path, "rb").read()); names = [b.name for b in a.bones]
    rep = {}
    for m in a.meshes:
        if "CLOTH" not in m.name: continue
        lay = mmbio.vertex_layout(a, m)
        assert lay == dict(plen=12, ptype=1, S=8, wsize=2, isize=1) and m.normal_type == "float" and m.color_count == 1, (m.name, lay)
        l = m.lods[0]; n = l.vertex_count; vs = m.vertex_stride; ns = m.normals_stride
        binds = list(m.mesh_bones.keys())
        is_leg = np.array([any(k in names[b] for k in LEG_KEYS) for b in binds])
        hips = binds.index(names.index("Hips"))
        before = after = 0.0
        for v in range(n):
            o = l.data_offset + v * vs + 12
            w = np.array(struct.unpack_from("<8H", buf, o), np.int64); ix = np.array(struct.unpack_from("<8B", buf, o + 16))
            used = w > 0
            legw = int(w[used & is_leg[ix]].sum()); before += legw / 32767.0
            if legw == 0: continue
            acc = {}
            for wi, bi in zip(w[used], ix[used]):
                acc[int(bi)] = acc.get(int(bi), 0.0) + float(wi) * (CAPE["leg_follow"] if is_leg[bi] else 1.0)
            acc[hips] = acc.get(hips, 0.0) + legw * (1.0 - CAPE["leg_follow"])
            items = sorted(acc.items(), key=lambda t: -t[1])[:8]
            tot = sum(x for _, x in items); q = [int(round(x / tot * 32767)) for _, x in items]; q[0] += 32767 - sum(q)
            nw = q + [0] * (8 - len(q)); ni = [b for b, _ in items] + [0] * (8 - len(items))
            struct.pack_into("<8H", buf, o, *nw); struct.pack_into("<8B", buf, o + 16, *ni)
            after += sum(x for (b, _), x in zip(items, q) if is_leg[b]) / 32767.0
        rep[m.name] = f"leg-bone weight per vertex {before / n:.2f} -> {after / n:.2f}"
        if "SIM" in m.name:
            noff = l.data_offset + (l.vertex_data_offset_b - l.vertex_data_offset_a)
            r_old = np.array([buf[noff + v * ns + 28] for v in range(n)])
            r_new = np.clip(np.rint(r_old * CAPE["freedom_gain"]), 0, 255).astype(int)
            for v in range(n): buf[noff + v * ns + 28] = int(r_new[v])
            rep[m.name] += f"; freedom (red) max {r_old.max()} -> {r_new.max()}, pinned particles {int((r_old == 0).sum())} -> {int((r_new == 0).sum())}"
    assert len(buf) == os.path.getsize(path)
    open(path, "wb").write(buf)
    b = mmbio.parse_header(path)                     # still parses, weights still sum correctly
    for m in b.meshes:
        d = mmbio.read_lod(b, m.index, 0)
        assert (d.bw_raw.sum(1) == 32767).all(), m.name
    return rep


def free_cloth(src, dst):
    """The real cloth-freedom fix (same file length): rewrite the per-particle MAX DISTANCE table of the
    cape's `.mcloth` (format notes: mcloth.py).

    Rev 7 showed the game does not take cloth freedom from the `.mmb` vertex colours; it is baked here.
    The Canto cape lets a particle stray at most red/255 * 0.4 m from its animated position — 0 at the
    neck, ramping to 3.9 cm at the shoulder blades and then 3.9 cm all the way to the hem. That is an
    NPC cape that is effectively skinned, hence "glued to the shins / minor physics".
    New table: unchanged above `free_top` (the upper back keeps lying on the body exactly as authored,
    pins untouched), then a smooth ramp to `max_dist` at `free_bottom` (hip level) and below — the same
    order of freedom a fully painted (red 255) hero cape gets. All four sim LOD sections carry identical
    tables and get the identical patch.
    Rev 8 changed only this table and nothing changed in game (the file IS read: its last-access time
    moves when the game loads the character). Each settings block also stores the limit radius itself
    (= the table's maximum, 0.0392157); rev 9 raises that to the new maximum as well."""
    import struct
    import numpy as np
    sys.path.insert(0, HERE)
    import mcloth
    buf = bytearray(open(src, "rb").read()); size = len(buf); rep = None; nblocks = 0
    secs = mcloth.sections(bytes(buf))
    assert len(secs) == 4 and all("CLOTH_SIM_Cloth0_LOD" in n for n, _, _ in secs), [n for n, _, _ in secs]
    for name, off, cs in secs:
        t = mcloth.max_distance(bytes(buf), cs); n = t["n"]
        old = t["dist"][:n]; y = t["pos"][:n, 1]
        assert t["lo"] == 0.0 and (old[t["pinned"][:n]] == 0).all()
        u = np.clip((CAPE["free_top"] - y) / (CAPE["free_top"] - CAPE["free_bottom"]), 0.0, 1.0)
        ramp = u * u * (3.0 - 2.0 * u)
        gain = 1.0 + (CAPE["max_dist"] / old.max() - 1.0) * ramp
        new = old * gain
        mcloth.set_max_distance(buf, t, new)
        # the limit radius in every settings block of this section (rev 8 left it at 3.9 cm -> no change in game)
        blocks = mcloth.settings_blocks(bytes(buf), cs)
        assert len(blocks) == 2, len(blocks)
        for po in blocks:
            mode, radius = buf[po], struct.unpack_from("<f", buf, po + mcloth.LIMIT_OFF)[0]
            assert mode == 2 and abs(radius - old.max()) < 2e-4, (mode, radius, old.max())
            if CAPE["limit_radius"]:
                struct.pack_into("<f", buf, po + mcloth.LIMIT_OFF, float(new.max()))
                nblocks += 1
        chk = mcloth.max_distance(bytes(buf), cs)
        assert np.abs(chk["dist"][:n] - new).max() <= chk["step"] * 0.51 and ((chk["dist"][:n] == 0) == (old == 0)).all()
        if rep is None:
            band = lambda lo, hi: float(chk["dist"][:n][(y >= lo) & (y < hi)].mean() * 100)
            rep = (f"max distance {old.max() * 100:.1f} cm -> {chk['dist'][:n].max() * 100:.1f} cm at the hem; pinned particles "
                   f"{int((old == 0).sum())} unchanged; by height: shoulders (>1.34 m) {band(1.34, 9):.1f} cm, "
                   f"upper back (1.18-1.34) {band(1.18, 1.34):.1f} cm, waist (1.02-1.18) {band(1.02, 1.18):.1f} cm, "
                   f"hips and below {band(0, 1.02):.1f} cm; {len(secs)} sim LOD sections patched")
    assert len(buf) == size
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(buf)
    return rep + (f"; limit radius in {nblocks} settings blocks -> {CAPE['max_dist'] * 100:.1f} cm" if nblocks
                  else "; limit radius in the settings blocks left at 3.9 cm (rev 8 behaviour)")


def fit_cape(mmb_path, mcloth_path):
    """Move the top of the cape out of Din's body (in place, same file lengths).

    The Canto cape is cut for a slim police uniform: on Din its whole collar / shoulder band sits INSIDE
    the back plate, jacket and bandolier (up to several cm), so the cape appears to grow out of the
    middle of his back with a ragged edge. Those particles are the pinned ones (max distance 0), so they
    go exactly where their rest position says. This computes, in bind pose, how far each part of the
    upper cape must move along its own outward normal to sit `neck_margin` above every body surface
    that should be UNDER a cape (everything except helmet and pauldrons), spreads that smoothly
    (`neck_reach`), and applies the same displacement field to every copy of the cape:
        .mmb  CLOTH_SIM positions (skinned animation targets), CLOTH_RENDER positions of all LODs
        .mcloth particle rest positions (id 11) of all four sim LOD sections
    so whichever copy the game uses, they agree. The render mesh is bound to the sim cage inside the
    .mcloth (barycentric + offset), so it follows the cage."""
    import struct
    import numpy as np
    from scipy.spatial import cKDTree
    sys.path.insert(0, HERE)
    import mmbio, mcloth, meshutil, neck_probe as npb
    a = mmbio.parse_header(mmb_path); mb = bytearray(open(mmb_path, "rb").read())
    sim = next(m for m in a.meshes if "CLOTH_SIM" in m.name); ren = next(m for m in a.meshes if "CLOTH_RENDER" in m.name)

    def fpos(m, l):
        return np.frombuffer(bytes(mb), np.uint8, l.vertex_count * m.vertex_stride, l.data_offset).reshape(-1, m.vertex_stride)[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
    S0 = fpos(sim, sim.lods[0]); R0 = fpos(ren, ren.lods[0])
    stris = mmbio.read_lod(a, sim.index, 0).tris
    # every render vertex rides on its nearest sim vertices (the game uses sim triangles; same idea)
    stree = cKDTree(S0)

    def binding(P, k=4):
        dd, ii = stree.query(P, k=k); w = 1.0 / np.maximum(dd, 1e-5) ** 2
        return ii, w / w.sum(1, keepdims=True)
    ri, rw = binding(R0)
    bpos, bnrm, blab, names = npb.body_samples(cover_only=True); btree = cKDTree(bpos)
    S = S0.copy(); R = R0.copy(); log = []
    for it in range(8):
        nS = npb.outward(S, meshutil.vertex_normals(S, stris))
        nR = (rw[:, :, None] * nS[ri]).sum(1); nR /= np.maximum(np.linalg.norm(nR, axis=1, keepdims=True), 1e-9)
        hS, _ = npb.column_heights(S, nS, btree, bpos, blab, bnrm=bnrm)
        hR, _ = npb.column_heights(R, nR, btree, bpos, blab, bnrm=bnrm)
        need = np.clip(hS + CAPE["neck_margin"], 0, None)                      # -inf -> 0
        needR = np.clip(hR + CAPE["neck_margin"], 0, None)
        for k in range(ri.shape[1]):                                           # a render vertex's need goes to the cage verts carrying it
            np.maximum.at(need, ri[:, k], np.where(rw[:, k] > 0.15, needR, 0.0))
        log.append((int((hR > -CAPE["neck_margin"] + 1e-4).sum()), float(need.max())))
        if need.max() < 5e-4: break
        dist = np.linalg.norm(S[:, None, :] - S[None, :, :], axis=2) / CAPE["neck_reach"]
        fall = np.clip(1.0 - dist ** 2, 0, None) ** 2                           # smooth bump, 1 at the vertex, 0 at neck_reach
        d = (need[None, :] * fall).max(1)
        dS = d[:, None] * nS
        S += dS; R += (rw[:, :, None] * dS[ri]).sum(1)
    moved = np.linalg.norm(S - S0, axis=1)
    # --- write back: .mmb
    def put(m, l, P):
        for v in range(l.vertex_count): struct.pack_into("<3f", mb, l.data_offset + v * m.vertex_stride, *P[v])
    put(sim, sim.lods[0], S)
    dS = S - S0
    for li, l in enumerate(ren.lods):
        P0 = fpos(ren, l); ii, ww = binding(P0); put(ren, l, P0 + (ww[:, :, None] * dS[ii]).sum(1))
    assert len(sim.lods) == 1 and len(mb) == os.path.getsize(mmb_path)
    open(mmb_path, "wb").write(mb)
    # --- write back: .mcloth rest positions (same particle order as the sim mesh, verified exact)
    cb = bytearray(open(mcloth_path, "rb").read()); nsec = 0
    for name, off, cs in mcloth.sections(bytes(cb)):
        t = mcloth.max_distance(bytes(cb), cs)
        assert t["n"] == len(S0) and np.abs(t["pos"][:t["n"]] - S0).max() < 1e-6, "cloth particles != sim mesh vertices"
        for v in range(t["n"]): struct.pack_into("<3f", cb, t["pos_off"] + v * 16, *S[v])
        nsec += 1
    assert len(cb) == os.path.getsize(mcloth_path)
    open(mcloth_path, "wb").write(cb)
    top = moved > 1e-4
    return (f"{int(top.sum())} of {len(S0)} cage vertices moved (mean {moved[top].mean() * 100:.1f} cm, max {moved.max() * 100:.1f} cm; "
            f"lowest moved y {S0[top, 1].min():.2f} m); render verts still under a body surface per pass: {[x[0] for x in log]}; "
            f"{len(ren.lods)} render LODs + {nsec} cloth sections rewritten")


def drop_gear_entry(txt, graph):
    """Remove the whole `GearGraphInfoList { GearGraphInfo { myGearGraph "<graph>" } }` block from a gear list.

    A part that is not in a character's gear list is simply not built — the base mod itself removes
    Kay's own head and hair this way. Unlike a 0-byte override of the graph, this touches nobody else
    who uses the same graph."""
    lines = txt.split(b"\r\n")
    hit = [i for i, l in enumerate(lines) if graph in l]
    assert len(hit) == 1, f"expected exactly one entry loading {graph.decode()}"
    start = max(j for j in range(hit[0]) if lines[j].strip().startswith(b"GearGraphInfoList"))
    depth, end = 0, None
    for j in range(start + 1, len(lines)):
        t = lines[j].strip()
        if t == b"{": depth += 1
        elif t == b"}":
            depth -= 1
            if depth == 0: end = j; break
    assert end is not None and end > hit[0], "unbalanced gear list block"
    block = lines[start:end + 1]
    assert sum(b"myGearGraph" in l for l in block) == 1, "the block holds more than the one gear graph"
    return b"\r\n".join(lines[:start] + lines[end + 1:])


def build(color=CAPE_COLOR):
    # 1. gear list
    txt = open(os.path.join(SRC, "character_visuals_player.BASEMOD.mcharactervisuals"), "rb").read()
    assert txt.count(OLD_GRAPH) == 1, "expected exactly one poncho entry in the base mod's gear list"
    out = os.path.join(STAGE, VISUALS_REL); os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(drop_gear_entry(txt.replace(OLD_GRAPH, NEW_GRAPH), HEAD_GRAPH))
    # 2. mesh: force the visible cloth to LOD0 (in place, same length)
    src_mmb = os.path.join(SRC, os.path.basename(MMB_REL)); out_mmb = os.path.join(STAGE, MMB_REL)
    os.makedirs(os.path.dirname(out_mmb), exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "..", "force_lod0.py"), src_mmb, out_mmb, "CLOTH_RENDER"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.getsize(out_mmb) == os.path.getsize(src_mmb)
    lod_line = next(l.strip() for l in r.stdout.splitlines() if "thresholds=" in l)
    cloth = free_cape(out_mmb)
    cloth["mcloth"] = free_cloth(os.path.join(SRC, os.path.basename(MCLOTH_REL)), os.path.join(STAGE, MCLOTH_REL))
    if CAPE["neck_fit"]:
        cloth["neck fit"] = fit_cape(out_mmb, os.path.join(STAGE, MCLOTH_REL))
    # 3. material recolour
    src_mat = os.path.join(SRC, os.path.basename(MAT_REL)); out_mat = os.path.join(STAGE, MAT_REL)
    os.makedirs(os.path.dirname(out_mat), exist_ok=True)
    mm, cs = matconst.load_constants(src_mat); raw = mm.build(); done = []
    for cn in PRIMARY + SECONDARY:
        c = next((x for x in cs if x.name == cn and x.values and len(x.values) == 3), None)
        if c is None: continue
        matconst.set_const(mm, c, list(color) if cn in PRIMARY else [v * 0.7 for v in color]); done.append(cn)
    new = mm.build(); assert len(new) == len(raw), "material length changed"
    open(out_mat, "wb").write(new)
    return dict(visuals="poncho slot -> chr_acc_2_silver_canto_police_cape; head entry removed", lod=lod_line, cloth=cloth, recoloured=done, color=list(color))


if __name__ == "__main__":
    col = CAPE_COLOR
    for a in sys.argv[1:]:
        if a.startswith("cape_color="): col = [float(x) for x in a.split("=", 1)[1].split(",")]
        if a.startswith("cape_freedom="): CAPE["freedom_gain"] = float(a.split("=", 1)[1])
        if a.startswith("cape_leg_follow="): CAPE["leg_follow"] = float(a.split("=", 1)[1])
        for k in ("max_dist", "limit_radius", "free_top", "free_bottom", "neck_fit", "neck_margin", "neck_reach"):
            if a.startswith(f"cape_{k}="): CAPE[k] = float(a.split("=", 1)[1])
    for k, v in build(col).items(): print(f"   {k}: {v}")
