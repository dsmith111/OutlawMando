#!/usr/bin/env python3
"""neck_probe.py — where does the Din body poke through the borrowed cape (bind pose)?

For every cape vertex (CLOTH_RENDER LOD0 and CLOTH_SIM) a "column test": body surface samples lying in
a thin column along the cape's outward normal. height > 0 = the body is OUTSIDE the cape there.
Prints the penetrations grouped by body submesh. Shared by build_cape.py (neck fix)."""
import glob, os, sys
import numpy as np
from scipy.spatial import cKDTree
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mmbio
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
STAGE = os.path.join(ROOT, "local/din_swap/staging")
CENTRE = np.array([0.0, 1.25, -0.03])        # a point inside the chest: "outward" = away from it


def body_samples(spacing=0.004, ymin=1.05, cover_only=False):
    """Dense surface samples of every staged Din body mesh above ymin -> (points, face normals, labels, names).
    cover_only: just the parts a back cape must lie ON TOP of — drops the helmet and the two pauldrons
    (the cape passes underneath those)."""
    import meshutil
    P, N, L, names = [], [], [], []
    for f in sorted(glob.glob(os.path.join(STAGE, "helix/baked/**/*.mmb"), recursive=True)):
        if "canto_police_cape" in f: continue
        if cover_only and "headw" in f: continue
        a = mmbio.parse_header(f)
        for mi, m in enumerate(a.meshes):
            d = mmbio.read_lod(a, mi, 0)
            if len(d.tris) < 8: continue                       # stub
            tris = d.tris
            if cover_only and "vest" in f:                     # vest = back plate + chest plate + 2 pauldrons (separate shells)
                comp = meshutil.components(d.pos, d.tris)
                side = np.array([abs(d.pos[comp == c][:, 0].mean()) > 0.15 for c in range(comp.max() + 1)])
                tris = tris[~side[comp[tris[:, 0]]]]
            t = d.pos[tris]; keep = t[:, :, 1].max(1) > ymin; t = t[keep]
            if not len(t): continue
            fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); area = np.linalg.norm(fn, axis=1); ok = area > 1e-12
            t = t[ok]; fn = fn[ok] / area[ok, None]; area = area[ok] / 2
            k = np.maximum(1, np.ceil(np.sqrt(area * 2) / spacing)).astype(int)
            lab = len(names); names.append(os.path.basename(f).replace("chr_", "").replace("_5_canon_boba_fett", "")[:-4] + ":" + m.name)
            for kk in np.unique(k):
                sel = k == kk; tt = t[sel]
                i, j = np.meshgrid(np.arange(kk + 1), np.arange(kk + 1), indexing="ij"); msk = i + j <= kk
                u = i[msk] / kk; v = j[msk] / kk; w = 1 - u - v
                pts = w[None, :, None] * tt[:, None, 0] + u[None, :, None] * tt[:, None, 1] + v[None, :, None] * tt[:, None, 2]
                P.append(pts.reshape(-1, 3)); N.append(np.repeat(fn[sel], len(u), 0)); L.append(np.full(len(tt) * len(u), lab))
    return np.concatenate(P), np.concatenate(N), np.concatenate(L), names


def outward(pos, nrm):
    s = np.sign(((pos - CENTRE) * nrm).sum(1)); s[s == 0] = 1
    return nrm * s[:, None]


def column_heights(pos, nout, tree, bpos, blab, radius=0.008, hmin=-0.012, hmax=0.05, bnrm=None):
    """Per cape vertex: highest body sample inside the column (lateral < radius, hmin < h < hmax) along
    its outward normal -> (height or -inf, label of that sample).
    bnrm given: only body surfaces that FACE outward count (the skin the cape has to get out of)."""
    H = np.full(len(pos), -np.inf); Lb = np.full(len(pos), -1)
    for i, idx in enumerate(tree.query_ball_point(pos, hmax + radius)):
        if not idx: continue
        idx = np.asarray(idx); r = bpos[idx] - pos[i]; h = r @ nout[i]
        lat = np.linalg.norm(r - h[:, None] * nout[i], axis=1)
        ok = (lat < radius) & (h > hmin) & (h < hmax)
        if bnrm is not None: ok &= (bnrm[idx] @ nout[i]) > 0.15
        if ok.any():
            j = np.argmax(np.where(ok, h, -np.inf)); H[i] = h[j]; Lb[i] = blab[idx[j]]
    return H, Lb


def cape_meshes(path):
    a = mmbio.parse_header(path); out = {}
    for mi, m in enumerate(a.meshes):
        if "CLOTH" in m.name: out[m.name] = mmbio.read_lod(a, mi, 0)
    return out


if __name__ == "__main__":
    cape = sys.argv[1] if len(sys.argv) > 1 else glob.glob(os.path.join(STAGE, "helix/baked/**/chr_acc_2_silver_canto_police_cape.mmb"), recursive=True)[0]
    bpos, bnrm, blab, names = body_samples(); tree = cKDTree(bpos)
    print("body samples:", len(bpos), "from", len(names), "submeshes")
    for name, d in cape_meshes(cape).items():
        nout = outward(d.pos, d.nrm)
        H, Lb = column_heights(d.pos, nout, tree, bpos, blab)
        up = d.pos[:, 1] > 1.10
        print(f"\n{name}: {len(d.pos)} verts, {int(up.sum())} above 1.10 m; body outside the cape (h > 0) at {int((H > 0).sum())}, within 5 mm under at {int(((H <= 0) & (H > -0.005)).sum())}")
        for lab in np.unique(Lb[H > 0]):
            m = (H > 0) & (Lb == lab); p = d.pos[m]
            print(f"   {names[lab]:44s} n {m.sum():4d}  depth mean {H[m].mean() * 1000:5.1f} max {H[m].max() * 1000:5.1f} mm   x {p[:, 0].min():+.3f}..{p[:, 0].max():+.3f}  y {p[:, 1].min():.3f}..{p[:, 1].max():.3f}  z {p[:, 2].min():+.3f}..{p[:, 2].max():+.3f}")
