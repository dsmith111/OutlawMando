#!/usr/bin/env python3
"""Minimal glTF 2.0 loader (numpy only) for skinned meshes: per-primitive geometry + skin joints.
Converts to GAME SPACE (Snowdrop: left-handed, Y up, +Z front, metres): x -> -x, scale 0.01,
triangle winding flipped."""
import json, os, struct
import numpy as np

_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Part:
    pass


class Model:
    pass


def _accessor(g, bins, i):
    a = g["accessors"][i]; bv = g["bufferViews"][a["bufferView"]]
    dt = np.dtype(_CT[a["componentType"]]).newbyteorder("<"); nc = _NC[a["type"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    buf = bins[bv["buffer"]]
    if stride and stride != dt.itemsize * nc:
        raw = np.frombuffer(buf, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * nc, offset=off)
        idx = (np.arange(a["count"])[:, None] * stride + np.arange(dt.itemsize * nc)[None, :])
        arr = raw[idx].copy().view(dt).reshape(a["count"], nc)
    else:
        arr = np.frombuffer(buf, dt, count=a["count"] * nc, offset=off).reshape(a["count"], nc)
    if a.get("normalized"):
        info = np.iinfo(_CT[a["componentType"]]); arr = arr.astype(np.float64) / info.max
    return arr


def _node_local(n):
    if "matrix" in n:
        return np.array(n["matrix"], np.float64).reshape(4, 4).T
    T = np.eye(4); R = np.eye(4); S = np.eye(4)
    if "translation" in n: T[:3, 3] = n["translation"]
    if "rotation" in n:
        x, y, z, w = n["rotation"]
        R[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    if "scale" in n: S[0, 0], S[1, 1], S[2, 2] = n["scale"]
    return T @ R @ S


def load(path, scale=0.01):
    g = json.load(open(path))
    base = os.path.dirname(path)
    bins = [open(os.path.join(base, b["uri"]), "rb").read() for b in g["buffers"]]
    nodes = g["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    skin = g["skins"][0]
    joints = skin["joints"]
    ibm = _accessor(g, bins, skin["inverseBindMatrices"]).astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1)
    m = Model()
    m.joint_names = [nodes[j].get("name", f"joint{j}") for j in joints]
    jidx = {j: k for k, j in enumerate(joints)}
    m.joint_parent = [jidx.get(parent.get(j, -1), -1) for j in joints]
    S = np.diag([-scale, scale, scale, 1.0])          # mesh space (cm, RH) -> game space (m, LH)
    Sinv = np.linalg.inv(S)
    bind = np.linalg.inv(ibm)                           # joint bind (world) matrices in mesh space
    m.joint_bind = np.einsum("ij,njk,kl->nil", S, bind, Sinv)   # conjugated into game space
    m.joint_pos = m.joint_bind[:, :3, 3].copy()
    m.parts = []
    for mi, me in enumerate(g["meshes"]):
        for p in me["primitives"]:
            a = p["attributes"]
            pt = Part()
            pt.material = g["materials"][p["material"]]["name"]
            pos = _accessor(g, bins, a["POSITION"]).astype(np.float64)
            pt.pos = pos * np.array([-scale, scale, scale])
            pt.nrm = _accessor(g, bins, a["NORMAL"]).astype(np.float64) * np.array([-1, 1, 1])
            uv = _accessor(g, bins, a["TEXCOORD_0"]).astype(np.float64)
            # Sketchfab's glTF conversion flipped BOTH the textures and v. We use the ORIGINAL TGA
            # textures (un-flipped), so undo the v flip: v_file = 1 - v_gltf (origin top-left, v down,
            # same convention as the game's own UVs).
            pt.uv = np.stack([uv[:, 0], 1.0 - uv[:, 1]], 1)
            tris = _accessor(g, bins, p["indices"]).astype(np.int64).reshape(-1, 3)
            pt.tris = tris[:, [0, 2, 1]].copy()
            pt.joints = _accessor(g, bins, a["JOINTS_0"]).astype(np.int64)
            pt.weights = _accessor(g, bins, a["WEIGHTS_0"]).astype(np.float64)
            pt.weights /= np.maximum(pt.weights.sum(1, keepdims=True), 1e-12)
            m.parts.append(pt)
    return m


if __name__ == "__main__":
    import sys
    np.set_printoptions(precision=4, suppress=True, linewidth=200)
    m = load(sys.argv[1])
    for pt in m.parts:
        fn = np.cross(pt.pos[pt.tris[:, 1]] - pt.pos[pt.tris[:, 0]], pt.pos[pt.tris[:, 2]] - pt.pos[pt.tris[:, 0]])
        vn = np.zeros_like(pt.pos)
        for k in range(3): np.add.at(vn, pt.tris[:, k], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        print(pt.material, "verts", len(pt.pos), "tris", len(pt.tris), "bbox", pt.pos.min(0), pt.pos.max(0),
              "uv", pt.uv.min(0), pt.uv.max(0), "normal.geo", round(float((vn * pt.nrm).sum(1).mean()), 3),
              "infl/vert max", int((pt.weights > 0).sum(1).max()))
    for k, n in enumerate(m.joint_names):
        if any(s in n for s in ("pelvis", "spine", "neck", "head_0", "clavicle", "upperarm_l", "upperarm_r", "lowerarm_l_", "hand_l", "thigh_l", "calf_l_", "foot_l", "ball_l_0")) and "twist" not in n and "end" not in n:
            print(f"{n:28s} pos {m.joint_pos[k]} parent {m.joint_names[m.joint_parent[k]] if m.joint_parent[k]>=0 else None}")
