"""Small numpy mesh utilities: welding, connected components, normals, tangents."""
import numpy as np


def weld_map(pos, tol=1e-5):
    """Return (n,) array mapping each vertex to a welded id (by rounded position)."""
    key = np.round(np.asarray(pos) / tol).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    return inv.reshape(-1)


def components(pos, tris, tol=1e-5):
    """Connected components over position-welded vertices. Returns per-vertex component id (0..k-1),
    ordered by descending triangle count."""
    w = weld_map(pos, tol)
    n = int(w.max()) + 1
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    wt = w[tris]
    for a, b, c in wt:
        ra, rb, rc = find(a), find(b), find(c)
        if ra != rb: parent[rb] = ra
        ra = find(a)
        if ra != rc: parent[rc] = ra
    roots = np.array([find(i) for i in range(n)])
    vroot = roots[w]
    troot = vroot[tris[:, 0]]
    uniq, counts = np.unique(troot, return_counts=True)
    order = uniq[np.argsort(-counts)]
    remap = {r: i for i, r in enumerate(order)}
    return np.array([remap.get(r, -1) for r in vroot])


def vertex_normals(pos, tris, weld_tol=None):
    """Area-weighted smooth normals. If weld_tol is given, normals are averaged across
    position-coincident vertices (smooth across UV seams)."""
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    if weld_tol is not None:
        w = weld_map(pos, weld_tol)
        acc = np.zeros((int(w.max()) + 1, 3))
        for k in range(3): np.add.at(acc, w[tris[:, k]], fn)
        vn = acc[w]
    else:
        vn = np.zeros_like(pos)
        for k in range(3): np.add.at(vn, tris[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def tangents(pos, nrm, uv, tris):
    """Per-vertex tangent (dP/du, orthonormalised against the normal) and handedness sign
    (+1 when cross(n, t) points along dP/dv with the given uv convention)."""
    p0, p1, p2 = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    u0, u1, u2 = uv[tris[:, 0]], uv[tris[:, 1]], uv[tris[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = u1 - u0, u2 - u0
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) > 1e-20, 1.0 / np.where(det == 0, 1, det), 0.0)
    T = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
    B = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
    # weight by triangle area so slivers do not dominate
    area = np.linalg.norm(np.cross(e1, e2), axis=1, keepdims=True)
    Tn = T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-20) * area
    Bn = B / np.maximum(np.linalg.norm(B, axis=1, keepdims=True), 1e-20) * area
    vt = np.zeros_like(pos); vb = np.zeros_like(pos)
    for k in range(3):
        np.add.at(vt, tris[:, k], Tn); np.add.at(vb, tris[:, k], Bn)
    t = vt - nrm * (vt * nrm).sum(1, keepdims=True)
    ln = np.linalg.norm(t, axis=1, keepdims=True)
    # fallback for degenerate tangents: any vector perpendicular to the normal
    alt = np.cross(nrm, np.where(np.abs(nrm[:, 1:2]) < 0.9, [[0.0, 1.0, 0.0]], [[1.0, 0.0, 0.0]]))
    alt /= np.maximum(np.linalg.norm(alt, axis=1, keepdims=True), 1e-20)
    t = np.where(ln > 1e-12, t / np.maximum(ln, 1e-20), alt)
    sign = np.where((np.cross(nrm, t) * vb).sum(1) < 0, -1.0, 1.0)
    return t, sign


def submesh(mask, tris):
    """Select triangles whose 3 vertices are in mask; returns (vertex_index_array, new_tris)."""
    sel = mask[tris].all(1)
    t = tris[sel]
    used = np.unique(t)
    remap = -np.ones(len(mask), int); remap[used] = np.arange(len(used))
    return used, remap[t]
