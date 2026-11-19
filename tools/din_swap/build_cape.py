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
     fixed "cape freezes at distance" for the poncho; its LOD thresholds are even tighter), its leg
     weights halved (free_cape) and its shape fitted to Din (fit_cape, hang_cape).
  2b. the Canto cape .mcloth un-stiffened (hero_cloth) and given the same shape changes.
  3. the Canto cape material recoloured (denim recipe from v1.2: Color A/B = colour, Fuzz/Weft/Fade
     = 0.7 x colour; same-length float edits).
  NOTE: 2 and 3 override the cape's own vanilla paths, so Canto Bight police NPCs get the same colour,
  cloth behaviour and always-full-detail capes. A side effect outside the player character.

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
CAPE = dict(freedom_gain=10.2,   # .mmb sim-mesh red channel x this (25 -> 255). NOT read by the game; kept so the
                                 # .mmb stays byte-identical to the build confirmed in game
            leg_follow=0.5,      # fraction of the lower cape's thigh-bone weight that is kept (rest -> Hips)
            neck_fit=1,          # 1 = move the upper cape out so it lies ON Din's back plate / bandolier (see fit_cape)
            neck_margin=0.008,   # clearance (m) kept between the cape and the body surface underneath
            neck_reach=0.09,     # radius (m) over which a local push-out fades into the untouched cape
            hang=1,              # 1 = straighten the lower cape so it hangs plumb instead of flaring backwards (see hang_cape)
            hang_top=1.17,       # height (m) below which the straightening applies (just under the neck-fit zone)
            hang_blend=0.10,     # height range (m) over which the straightening fades in
            friction=0.0,        # .mcloth struct +125 (vanilla 0.7; 0 in every other cape)
            friction2=0.0,       # .mcloth struct +133 (vanilla 0.1; 0 in every other cape)
            damping="1,1,1,1,1", # .mcloth chunk 8 (vanilla 1.5,0.5,0.2,1,1; Vader's cape has all ones); "keep" leaves it
            inward=1.5,          # extra inward travel (m) the lower cape gets on its backstop channel, so it can hang
                                 # under its animated pose when the torso pitches (crouch); 0 = vanilla backstop
            inward_top=1.15,     # height (m) above which the backstop stays vanilla (upper back)
            inward_bottom=0.90)  # height (m) at/below which the full `inward` applies
SETTINGS_CHUNKS = (5, 46, 7, 8, 45, 43)   # a settings block: the 149-byte struct and the chunks that vary between capes
LEG_KEYS = ("UpLeg", "Leg", "Butt", "Hips_")
PRIMARY, SECONDARY = ("Color A", "Color B"), ("Fuzz Color", "Weft Color", "Fade Color")


def free_cape(path):
    """In-place `.mmb` edits to the cape (same file length).

    1. On the sim and render meshes, (1 - leg_follow) of each vertex's leg-bone weight moves to Hips, so
       the cape's animated pose swings with the legs half as much (the lower half of the vanilla cape is
       75-97 % weighted to the thigh bones).
    2. The sim mesh's vertex colour red is multiplied by freedom_gain. The game does NOT read cloth
       settings from the `.mmb` vertex colours (they are baked into the `.mcloth`), so this does nothing
       in game; it is kept only so the file stays byte-identical to the build confirmed in game."""
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


def hero_cloth(src, dst):
    """The vanilla Canto `.mcloth` with only what makes it a stiff NPC cape removed (same file length).

    What the tables really are (learned from the poncho, Vader and Lando-standing cloth files, all free-flowing):
      * ids 178-180, slot 2  = per-particle COLLISION RADIUS, not a leash. Free capes have 0-7 cm there
        (Canto 0-3.9 cm) and struct +26 is its maximum. Raising it makes the cloth keep that far away from every
        collision capsule (an "invisible box" under the cape). Left vanilla.
      * ids 12-14, range 3   = backstop: how far (negative metres) a particle may go INSIDE its animated pose.
        Canto 0 ... -17 cm, Lando 0 ... -23 cm, Vader 0 ... -36 cm; the poncho has none.
      * ids 12-14, range 4   = max distance from the animated pose (only Lando has one, 0-26 cm); Canto has none.
    What only the Canto cape has:
      * struct +125 = 0.7 and +133 = 0.1 (0 in every other cape) - read here as friction against the body
        colliders, which is what made the cape stick to the calves; set to `friction` / `friction2`.
      * chunk 8 = (1.5, 0.5, 0.2, 1, 1), the heaviest first value of any cape; replaced by `damping`.
      * (graph side: cloth follow input 0.2 - build_graphs.py.)
    One player-specific change: the animated pose swings rigidly with the upper spine, so when Kay crouches it
    sticks out behind her and a -13 cm backstop would hold the cape up there. Below `inward_top` the backstop is
    deepened by up to `inward` so the cloth can hang; the collision capsules keep it off the body, as they do for
    the poncho, which has no backstop at all."""
    import struct
    import numpy as np
    sys.path.insert(0, HERE)
    import mcloth
    buf = bytearray(open(src, "rb").read()); size = len(buf); rep = None
    secs = mcloth.sections(bytes(buf))
    assert len(secs) == 4 and all("CLOTH_SIM_Cloth0_LOD" in n for n, _, _ in secs), [n for n, _, _ in secs]
    damp = None if CAPE["damping"] == "keep" else [float(x) for x in str(CAPE["damping"]).split(",")]
    for name, off, cs in secs:
        t = mcloth.max_distance(bytes(buf), cs); n = t["n"]; y = t["pos"][:n, 1]
        blocks = settings_chunks(bytes(buf), cs)
        assert len(blocks) == 2
        for blk in blocks:
            po = blk[5][0]
            fr, fr2 = struct.unpack_from("<f", buf, po + 125)[0], struct.unpack_from("<f", buf, po + 133)[0]
            assert buf[po] == 2 and abs(fr - 0.7) < 1e-6 and abs(fr2 - 0.1) < 1e-6, (buf[po], fr, fr2)
            struct.pack_into("<f", buf, po + 125, CAPE["friction"]); struct.pack_into("<f", buf, po + 133, CAPE["friction2"])
            p8, n8 = blk[8]
            was8 = struct.unpack_from("<5f", buf, p8)
            assert n8 == 20 and abs(was8[0] - 1.5) < 1e-6, was8
            if damp is not None:
                assert len(damp) == 5; struct.pack_into("<5f", buf, p8, *damp)
        # backstop channel: deepen below inward_top
        ch = mcloth.particle_channel(bytes(buf), cs)
        assert ch["count"] == len(t["pos"]) and ch["lo"] < -0.1 and abs(ch["hi"]) < 0.02, ch
        raw = np.frombuffer(bytes(buf), np.uint8, ch["count"], ch["off"])
        old = ch["lo"] + raw[:n].astype(float) * ch["step"]
        u = np.clip((CAPE["inward_top"] - y) / (CAPE["inward_top"] - CAPE["inward_bottom"]), 0.0, 1.0)
        new = old - CAPE["inward"] * (u * u * (3.0 - 2.0 * u))
        if CAPE["inward"] > 0:
            lo, hi = float(new.min()), float(max(new.max(), ch["hi"]))
            step = (hi - lo) / 254.0
            codes = np.clip(np.round((new - lo) / step), 0, 254).astype(np.uint8)
            buf[ch["off"]:ch["off"] + n] = codes.tobytes()                     # padding entries keep their bytes
            d = mcloth.typed(bytes(buf), cs)
            struct.pack_into("<3f", buf, d[14][0][0] + mcloth.BACKSTOP_RANGE * 12, step, lo, hi)
            chk = mcloth.particle_channel(bytes(buf), cs)
            got = chk["lo"] + np.frombuffer(bytes(buf), np.uint8, n, chk["off"]).astype(float) * chk["step"]
            assert np.abs(got - new).max() <= step * 0.51 + 1e-6, float(np.abs(got - new).max())
        # the collision radii and pins are untouched
        chk_t = mcloth.max_distance(bytes(buf), cs)
        assert np.array_equal(chk_t["dist"], t["dist"]) and int(chk_t["pinned"][:n].sum()) == 37 and abs(t["dist"][:n].max() - 0.0392157) < 2e-4
        if rep is None:
            band = lambda a, lo_, hi_: float(a[(y >= lo_) & (y < hi_)].mean() * 100)
            rep = (f"collision radii untouched (0-{t['dist'][:n].max() * 100:.1f} cm), 37 pins untouched; "
                   f"+125 {fr:g} -> {CAPE['friction']:g}, +133 {fr2:g} -> {CAPE['friction2']:g}; "
                   f"chunk 8 {tuple(round(x, 2) for x in was8)} -> {tuple(damp) if damp else 'kept'}; "
                   f"backstop (inward travel) upper back {band(old, 1.15, 9):.1f} cm kept, hips {band(old, 0.85, 1.15):.1f} -> {band(new, 0.85, 1.15):.1f} cm, "
                   f"legs {band(old, 0, 0.85):.1f} -> {band(new, 0, 0.85):.1f} cm; {len(secs)} sim LOD sections")
    assert len(buf) == size
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, "wb").write(buf)
    return rep


def settings_chunks(buf, cs):
    """[{chunk id: (payload offset, size)}] - one dict per settings block of a sim section (see SETTINGS_CHUNKS)"""
    T = [(cid, po, size - 8) for (off, cid, typ, size, po) in cs if typ == 0x11]
    out = []
    for k, (cid, po, n) in enumerate(T):
        if cid == 5 and n == 149:
            d = {5: (po, n)}
            for c, po2, n2 in T[k + 1:k + 12]:
                if c in SETTINGS_CHUNKS and c not in d: d[c] = (po2, n2)
            assert set(d) == set(SETTINGS_CHUNKS), sorted(d)
            out.append(d)
    return out


def fit_cape(mmb_path, mcloth_path):
    """Move the top of the cape out of Din's body (in place, same file lengths).

    The Canto cape is cut for a slim police uniform: on Din its whole collar / shoulder band sits INSIDE
    the back plate, jacket and bandolier (up to several cm), so the cape appears to grow out of the
    middle of his back with a ragged edge. Those particles are the pinned ones, so they
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


def hang_cape(mmb_path, mcloth_path):
    """Make the lower cape hang plumb (in place, same file lengths).

    The Canto cape is authored as an A-line: below the shoulder blades its rest surface slopes away
    from the body, to the tune of ~6 cm at the hem, because it was modelled over the police officer's
    long coat. Din has no coat, and the cape's animated pose is built from this shape, so it should be
    where a cape would really hang from his back plate: straight down. This removes the backward slope
    of the centre line below
    `hang_top` with a shear (z only, a function of height, fading in over `hang_blend`), applied to the
    same copies fit_cape writes: .mmb CLOTH_SIM, CLOTH_RENDER (all LODs), .mcloth rest positions."""
    import struct
    import numpy as np
    from scipy.spatial import cKDTree
    sys.path.insert(0, HERE)
    import mmbio, mcloth, neck_probe as npb
    a = mmbio.parse_header(mmb_path); mb = bytearray(open(mmb_path, "rb").read())
    sim = next(m for m in a.meshes if "CLOTH_SIM" in m.name); ren = next(m for m in a.meshes if "CLOTH_RENDER" in m.name)

    def fpos(m, l):
        return np.frombuffer(bytes(mb), np.uint8, l.vertex_count * m.vertex_stride, l.data_offset).reshape(-1, m.vertex_stride)[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
    S0 = fpos(sim, sim.lods[0])
    top, w = CAPE["hang_top"], CAPE["hang_blend"]
    mid = (np.abs(S0[:, 0]) < 0.12) & (S0[:, 1] < top)
    slope = float(np.polyfit(S0[mid, 1], S0[mid, 2], 1)[0])            # dz/dy of the centre line; > 0 = flares backwards going down
    assert 0.0 < slope < 0.2, slope

    def shifted(P):
        t = np.clip(top - P[:, 1], 0.0, None)
        f = np.where(t < w, t * t / (2.0 * w), t - w / 2.0)             # C1: no kink where the straightening starts
        Q = P.copy(); Q[:, 2] += slope * f
        return Q
    S = shifted(S0)
    # the straightened cape must still clear the body in bind pose
    bpos = npb.body_samples(spacing=0.006, ymin=0.25)[0]
    low = S[:, 1] < top
    gap0 = cKDTree(bpos).query(S0[low])[0]; gap1 = cKDTree(bpos).query(S[low])[0]
    assert gap1.min() > 0.012, f"straightened cape comes within {gap1.min() * 100:.1f} cm of the body"

    def put(m, l, P):
        for v in range(l.vertex_count): struct.pack_into("<3f", mb, l.data_offset + v * m.vertex_stride, *P[v])
    put(sim, sim.lods[0], S)
    for l in ren.lods: put(ren, l, shifted(fpos(ren, l)))
    assert len(mb) == os.path.getsize(mmb_path)
    open(mmb_path, "wb").write(mb)
    cb = bytearray(open(mcloth_path, "rb").read())
    for name, off, cs in mcloth.sections(bytes(cb)):
        t = mcloth.max_distance(bytes(cb), cs)
        assert t["n"] == len(S0) and np.abs(t["pos"][:t["n"]] - S0).max() < 1e-6, "cloth particles != sim mesh vertices"
        for v in range(t["n"]): struct.pack_into("<3f", cb, t["pos_off"] + v * 16, *S[v])
    assert len(cb) == os.path.getsize(mcloth_path)
    open(mcloth_path, "wb").write(cb)
    moved = S[:, 2] - S0[:, 2]
    return (f"centre line sloped {slope * 100:.1f} cm per metre; hem moved {moved.max() * 100:.1f} cm toward the body; "
            f"clearance to the body below {top:.2f} m: {gap0.min() * 100:.1f}-{np.median(gap0) * 100:.1f} cm (min-median) -> "
            f"{gap1.min() * 100:.1f}-{np.median(gap1) * 100:.1f} cm")


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
    cloth["mcloth"] = hero_cloth(os.path.join(SRC, os.path.basename(MCLOTH_REL)), os.path.join(STAGE, MCLOTH_REL))
    if CAPE["neck_fit"]:
        cloth["neck fit"] = fit_cape(out_mmb, os.path.join(STAGE, MCLOTH_REL))
    if CAPE["hang"]:
        cloth["hang"] = hang_cape(out_mmb, os.path.join(STAGE, MCLOTH_REL))
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
        for k in ("neck_fit", "neck_margin", "neck_reach", "hang", "hang_top", "hang_blend",
                  "friction", "friction2", "inward", "inward_top", "inward_bottom"):
            if a.startswith(f"cape_{k}="): CAPE[k] = float(a.split("=", 1)[1])
        if a.startswith("cape_damping="): CAPE["damping"] = a.split("=", 1)[1]
    for k, v in build(col).items(): print(f"   {k}: {v}")
