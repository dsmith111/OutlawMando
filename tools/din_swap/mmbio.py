#!/usr/bin/env python3
"""
mmbio — numpy reader/writer for Snowdrop `.mmb` skeletal meshes (Star Wars Outlaws, version 19).

Header parsing is delegated to ../mmb_core.py (the headless port of AlexPo's SWOutlaws Mesh Tool
parser). The data-block reading and the LOD0 *rebuild* (new geometry, new vertex count, extra bone
bindings) are implemented here with numpy, as a port of the addon's ExportLOD path, so the whole
swap pipeline runs without Blender and can be verified byte-for-byte against vanilla files.

Coordinates are GAME SPACE exactly as stored in the file (the Blender addon mirrors X on import and
again on export; we never do).

LOD block layout (one contiguous block per LOD at lod.data_offset, size lod.data_size):
    [vertex records: vertex_count * vertex_stride][vertex_end_bytes]
    [normal records: vertex_count * normals_stride][normals_end_bytes]
    [uint16 indices: index_count][faces_end_bytes]
Vertex record:  ptype1: float32 xyz | 8x uint8 weight | 8x uint8 binding index | pad
                ptype0: int16 xn,yn,zn,w (pos = n/32767*w) | zero weight bytes (rigid, 1 binding)
Normal record (int8 type, stride 16): int8n nx,ny,nz, u8 | int8n tx,ty,tz, u8 | int16n u0,v0 | int16n u1,v1
"""
import contextlib
import copy
import io
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import mmb_core as M  # noqa: E402

M.io = io


def _quiet():
    return contextlib.redirect_stdout(io.StringIO())


def parse_header(path):
    """Parse a .mmb with mmb_core. Returns the SkeletalMeshAsset."""
    with _quiet():
        sys.modules["bpy"].context.scene.SWOMT.AssetPath = path
        a = M.SkeletalMeshAsset()
        with open(path, "rb") as f:
            a.parse(f)
    a.path = path
    return a


def _mat(m):
    """mmb_core Matrix (rows list) -> np 4x4 (column-vector convention, translation in last column)."""
    return np.array(m.rows, dtype=np.float64)


def bone_tables(a):
    """Returns names, parents (-1 for root), local (N,4,4), world (N,4,4)."""
    names = [b.name for b in a.bones]
    parents = [(-1 if b.parent_index == 65535 else b.parent_index) for b in a.bones]
    local = np.stack([_mat(b.matrix) for b in a.bones])
    world = np.zeros_like(local)
    for i, p in enumerate(parents):
        world[i] = local[i] if p < 0 else world[p] @ local[i]
    return names, parents, local, world


def vertex_layout(a, mesh):
    """Solve the physical vertex record layout from the stride (mmb_core's guess is wrong for the
    common stride-32 skinned layout, which is int16 pos + 8x uint16 weights + 8x uint8 indices).

    Returns dict(plen, ptype, S, wsize, isize). ptype 0 = int16n xyz + int16 scale, 1 = float3.
    """
    vs = mesh.vertex_stride
    if mesh.weight_count <= 1:
        if vs == 16 and mesh.binding_count == 1 and mesh.normal_type == "float":
            return dict(plen=12, ptype=1, S=0, wsize=0, isize=0)
        return dict(plen=8, ptype=0, S=0, wsize=0, isize=0)
    isize = 2 if a.bone_count > 0xFF else 1
    for S in range(mesh.weight_count, 13):
        for plen in (8, 12):
            for wsize in (2, 1):
                if plen + S * (wsize + isize) == vs:
                    return dict(plen=plen, ptype=0 if plen == 8 else 1, S=S, wsize=wsize, isize=isize)
    raise NotImplementedError(f"{mesh.name}: cannot solve vertex layout for stride {vs}, "
                              f"weight_count {mesh.weight_count}")


class LodData:
    """Decoded geometry of one LOD (game space)."""

    def __init__(self):
        self.pos = None      # (N,3) float64
        self.nrm = None      # (N,3) float64 decoded int8n
        self.nrm_w = None    # (N,) uint8 4th byte
        self.tan = None      # (N,3)
        self.tan_w = None    # (N,) uint8
        self.uv0 = None      # (N,2) raw file values (v as stored, i.e. 1 - blender_v)
        self.uv1 = None
        self.bw = None       # (N,S) float weights 0..1
        self.bi = None       # (N,S) SKELETON bone indices (already mapped through the binding table)
        self.bi_raw = None   # (N,S) binding indices as stored
        self.tris = None     # (T,3) int
        self.raw_vertex = None
        self.raw_normal = None


def _i8n(b):
    return b.astype(np.int8).astype(np.float64) / 127.0


def _i16n(h):
    return h.astype(np.float64) / 32767.0


def read_lod(a, mesh_index, lod_index=0, buf=None):
    mesh = a.meshes[mesh_index]
    lod = mesh.lods[lod_index]
    if buf is None:
        buf = open(a.path, "rb").read()
    n = lod.vertex_count
    vs, ns = mesh.vertex_stride, mesh.normals_stride
    base = lod.data_offset
    d = LodData()
    vraw = np.frombuffer(buf, dtype=np.uint8, count=n * vs, offset=base).reshape(n, vs)
    d.raw_vertex = vraw.copy()
    lay = vertex_layout(a, mesh)
    d.layout = lay
    plen = lay["plen"]
    if lay["ptype"] == 0:
        q = vraw[:, :8].copy().view("<i2").reshape(n, 4).astype(np.float64)
        d.pos = q[:, :3] / 32767.0 * q[:, 3:4]
        d.pos_w = q[:, 3].astype(int)
    else:
        d.pos = vraw[:, :12].copy().view("<f4").reshape(n, 3).astype(np.float64)
    binds = list(mesh.mesh_bones.keys())
    if lay["S"] == 0:
        d.bw = np.ones((n, 1)); d.bi_raw = np.zeros((n, 1), int)
        d.bi = np.full((n, 1), binds[0], int)
        d.bw_raw = None
    else:
        S = lay["S"]
        if lay["wsize"] == 2:
            wr = vraw[:, plen:plen + 2 * S].copy().view("<u2").reshape(n, S).astype(np.int64)
            o = plen + 2 * S
        else:
            wr = vraw[:, plen:plen + S].astype(np.int64)
            o = plen + S
        if lay["isize"] == 2:
            ii = vraw[:, o:o + 2 * S].copy().view("<u2").reshape(n, S).astype(int)
        else:
            ii = vraw[:, o:o + S].astype(int)
        d.bw_raw = wr
        d.bw = wr / np.maximum(wr.sum(1, keepdims=True), 1)
        d.bi_raw = ii
        lut = np.array(binds + [binds[0]] * 65536, int)
        d.bi = lut[ii]
    noff = base + (lod.vertex_data_offset_b - lod.vertex_data_offset_a)
    nraw = np.frombuffer(buf, dtype=np.uint8, count=n * ns, offset=noff).reshape(n, ns)
    d.raw_normal = nraw.copy()
    if mesh.normal_type == "int8_norm":
        d.nrm = _i8n(nraw[:, 0:3]); d.nrm_w = nraw[:, 3].copy()
        d.tan = _i8n(nraw[:, 4:7]); d.tan_w = nraw[:, 7].copy()
        o = 8 + 4 * mesh.color_count
        d.uv0 = _i16n(nraw[:, o:o + 4].copy().view("<i2").reshape(n, 2))
        if mesh.uv_count > 1 and ns - o >= 8:
            d.uv1 = _i16n(nraw[:, o + 4:o + 8].copy().view("<i2").reshape(n, 2))
    else:
        f = nraw[:, :28].copy().view("<f4").reshape(n, 7).astype(np.float64)
        d.nrm, d.tan, d.tan_w = f[:, 0:3], f[:, 3:6], f[:, 6]
        o = 28 + 4 * mesh.color_count
        d.uv0 = _i16n(nraw[:, o:o + 4].copy().view("<i2").reshape(n, 2))
    foff = base + (lod.face_block_offset - lod.vertex_data_offset_a)
    idx = np.frombuffer(buf, dtype="<u2", count=lod.index_count, offset=foff).astype(int)
    d.tris = idx[: (len(idx) // 3) * 3].reshape(-1, 3)
    return d


# ----------------------------------------------------------------------------------------------
# Writing
# ----------------------------------------------------------------------------------------------

class NewGeom:
    """Replacement LOD0 geometry for one submesh (game space).

    pos (N,3), nrm (N,3) unit, tan (N,3) unit, tan_sign (N,) +1/-1, uv0 (N,2) FILE convention
    (v already flipped the way vanilla stores it), uv1 optional, tris (T,3),
    weights: list of N lists [(skeleton_bone_index, weight), ...] (ignored for rigid meshes).
    """

    def __init__(self, pos, nrm, tan, tan_sign, uv0, tris, weights=None, uv1=None, col=None):
        self.col = None if col is None else np.asarray(col, np.uint8)   # (N, 4*color_count) vertex colour bytes; default 0
        self.pos = np.asarray(pos, np.float64)
        self.nrm = np.asarray(nrm, np.float64)
        self.tan = np.asarray(tan, np.float64)
        self.tan_sign = np.asarray(tan_sign, np.float64)
        self.uv0 = np.asarray(uv0, np.float64)
        self.uv1 = self.uv0 if uv1 is None else np.asarray(uv1, np.float64)
        self.tris = np.asarray(tris, int)
        self.weights = weights


def enc_i8n(v):
    return np.clip(np.rint(np.asarray(v) * 127.0), -127, 127).astype(np.int8).view(np.uint8)


def enc_i16n(v):
    return np.clip(np.rint(np.asarray(v) * 32767.0), -32767, 32767).astype("<i2")


def quantize_weights(pairs, slots, binding_of, total=32767):
    """pairs: [(skel_bone, w)] -> (int weights[slots], binding indices[slots]); sum == total,
    sorted by descending weight (vanilla convention), unused slots zero."""
    pairs = [(b, w) for b, w in pairs if w > 0]
    if not pairs:
        raise ValueError("vertex has no weights")
    pairs.sort(key=lambda t: -t[1])
    pairs = pairs[:slots]
    s = sum(w for _, w in pairs)
    q = [int(round(w / s * total)) for _, w in pairs]
    q[0] += total - sum(q)
    # drop zero-quantized influences
    keep = [(binding_of[b], qq) for (b, _), qq in zip(pairs, q) if qq > 0]
    ws = [k[1] for k in keep] + [0] * (slots - len(keep))
    ix = [k[0] for k in keep] + [0] * (slots - len(keep))
    return ws, ix


def _build_lod0_block(a, mesh, lod, g, binding_of, pos_scale=None):
    """Returns (bytes, rel_normals_offset, rel_faces_offset)."""
    n = len(g.pos)
    if n > 65535:
        raise ValueError(f"{mesh.name}: {n} verts exceeds uint16 index range")
    vs, ns = mesh.vertex_stride, mesh.normals_stride
    v = np.zeros((n, vs), np.uint8)
    lay = vertex_layout(a, mesh)
    plen = lay["plen"]
    if lay["ptype"] == 0:
        w = max(int(pos_scale or 0), int(np.ceil(np.abs(g.pos).max())), 1)
        q = np.zeros((n, 4), "<i2")
        q[:, :3] = enc_i16n(g.pos / w)
        q[:, 3] = w
        v[:, :8] = q.view(np.uint8).reshape(n, 8)
    else:
        v[:, :12] = g.pos.astype("<f4").view(np.uint8).reshape(n, 12)
    if lay["S"]:
        S = lay["S"]
        if lay["isize"] != 1:
            raise NotImplementedError(f"{mesh.name}: uint16 bone indices not supported by writer")
        total = 32767 if lay["wsize"] == 2 else 255
        W = np.zeros((n, S), np.int64); I = np.zeros((n, S), np.uint8)
        for k in range(n):
            ws, ix = quantize_weights(g.weights[k], S, binding_of, total)
            W[k], I[k] = ws, ix
        if lay["wsize"] == 2:
            v[:, plen:plen + 2 * S] = W.astype("<u2").view(np.uint8).reshape(n, 2 * S)
            v[:, plen + 2 * S:plen + 3 * S] = I
        else:
            v[:, plen:plen + S] = W.astype(np.uint8)
            v[:, plen + S:plen + 2 * S] = I
    out = io.BytesIO()
    out.write(v.tobytes())
    if lod.vertex_end_bytes:
        out.write(lod.vertex_end_bytes)
    rel_n = out.tell()
    if mesh.normal_type != "int8_norm":
        raise NotImplementedError(f"{mesh.name}: float normal layout not supported by writer")
    r = np.zeros((n, ns), np.uint8)
    r[:, 0:3] = enc_i8n(g.nrm); r[:, 3] = 255
    r[:, 4:7] = enc_i8n(g.tan); r[:, 7] = np.where(g.tan_sign < 0, 129, 127).astype(np.uint8)
    o = 8 + 4 * mesh.color_count
    if mesh.color_count and g.col is not None:
        r[:, 8:o] = g.col[:, :4 * mesh.color_count]
    r[:, o:o + 4] = enc_i16n(g.uv0).view(np.uint8).reshape(n, 4)
    if mesh.uv_count > 1 and ns - o >= 8:
        r[:, o + 4:o + 8] = enc_i16n(g.uv1).view(np.uint8).reshape(n, 4)
    out.write(r.tobytes())
    if lod.normals_end_bytes:
        out.write(lod.normals_end_bytes)
    rel_f = out.tell()
    out.write(g.tris.astype("<u2").tobytes())
    if lod.faces_end_bytes:
        out.write(lod.faces_end_bytes)
    return out.getvalue(), rel_n, rel_f


def replace_lod0(src_path, dst_path, mesh_index, g, force_lod0=True, pos_scale=4, update_bounds=True):
    """Rebuild `mesh_index`'s LOD0 from NewGeom `g` and write a new .mmb (port of ExportLOD).

    Bones referenced by g.weights that are in the file skeleton but not yet bound by the mesh get
    an extra binding appended (inverse bind = the bone's existing mesh matrix from another submesh
    if any, else inverse of its world bind matrix).
    """
    a = parse_header(src_path)
    src = open(src_path, "rb").read()
    mesh = a.meshes[mesh_index]
    names, parents, local, world = bone_tables(a)

    # --- binding table (+ extra bones) ---
    binding_of = dict(mesh.real_bone_indices_to_mesh_bones)
    extra = []
    if vertex_layout(a, mesh)["S"]:
        used = sorted({b for pairs in g.weights for b, w in pairs if w > 0})
        for b in used:
            if b not in binding_of:
                binding_of[b] = len(binding_of)
                extra.append(b)
        if len(binding_of) > 255:
            raise ValueError("too many bindings for uint8 index")

    # --- per-mesh data files (LODs in reversed order, as the addon does) ---
    mods = []
    for m in a.meshes:
        mm = copy.copy(m)
        mm.lods = [copy.copy(l) for l in m.lods]
        mf = io.BytesIO()
        for lod in reversed(m.lods):
            ml = mm.lods[lod.index]
            ml.parent_mesh = mm
            new_a = mf.tell()
            if m.index == mesh_index and lod.index == 0:
                blk, rel_n, rel_f = _build_lod0_block(a, m, lod, g, binding_of, pos_scale)
                ml.vertex_count = len(g.pos)
                ml.index_count = int(g.tris.size)
                ml.vertex_data_offset_a = new_a
                ml.vertex_data_offset_b = new_a + rel_n
                ml.face_block_offset = new_a + rel_f
                mf.write(blk)
            else:
                diff = new_a - lod.vertex_data_offset_a
                ml.vertex_data_offset_a = new_a
                ml.vertex_data_offset_b = lod.vertex_data_offset_b + diff
                ml.face_block_offset = lod.face_block_offset + diff
                mf.write(src[lod.data_offset:lod.data_offset + lod.data_size])
            ml.data_size = mf.tell() - new_a
        mm.mesh_file = mf.getvalue()
        mods.append(mm)

    # --- header (insert extra bindings) ---
    out = io.BytesIO()
    with _quiet():
        data_start = a.get_mesh_data_start_offset()
    if extra:
        bco = mesh.binding_count_offset
        out.write(src[:bco])
        out.write(struct.pack("<H", mesh.binding_count + len(extra)))
        out.write(src[bco + 2: bco + 2 + 66 * mesh.binding_count])
        for b in extra:
            bone = a.bones[b]
            if bone.mesh_matrix is not None:
                mat = _mat(bone.mesh_matrix)
            else:
                mat = np.linalg.inv(world[b])
            out.write(mat.T.astype("<f4").tobytes())   # file stores columns consecutively
            out.write(struct.pack("<H", b))
        out.write(src[bco + 2 + 66 * mesh.binding_count: data_start])
        added = 66 * len(extra)
        for mm in mods:
            if mm.lod_count_offset > bco:
                mm.lod_count_offset += added
                for l in mm.lods:
                    l.start_offset += added
    else:
        out.write(src[:data_start])

    # --- data, in original file order ---
    order = sorted(((l.data_offset, mi, l.index) for mi, m in enumerate(a.meshes) for l in m.lods))
    new_header_size = -1
    for _, mi, li in order:
        ml = mods[mi].lods[li]
        if new_header_size == -1 and not a.meshes[mi].lods[li].is_header_lod:
            new_header_size = out.tell()
        ml.data_offset = out.tell()
        out.write(mods[mi].mesh_file[ml.vertex_data_offset_a: ml.vertex_data_offset_a + ml.data_size])

    # --- patch header fields ---
    buf = bytearray(out.getvalue())
    struct.pack_into("<I", buf, 4, new_header_size)
    for mm in mods:
        for l in mm.lods:
            thr = l.lod_screen_size
            if force_lod0 and mm.index == mesh_index and l.index > 0:
                thr = 1e6
            struct.pack_into("<IIIIIIIIf", buf, l.start_offset,
                             l.vertex_count, l.index_count, l.face_block_offset // 2,
                             l.vertex_data_offset_a, l.vertex_data_offset_b, l.face_block_offset,
                             l.data_offset, l.data_size, thr)
    if update_bounds:
        patch_bounds(buf, a, mesh_index, g.pos)
    with open(dst_path, "wb") as f:
        f.write(buf)
    return extra


def bounds_offset(buf, mesh):
    """File offset of the 48-byte per-mesh bounds block (right after the length-prefixed name)."""
    key = struct.pack("<H", len(mesh.name)) + mesh.name.encode("latin1")
    off = bytes(buf).rfind(key, 0, mesh.binding_count_offset)
    if off < 0:
        raise ValueError(f"cannot locate header of mesh {mesh.name}")
    return off + len(key)


def read_bounds(buf, mesh):
    f = struct.unpack_from("<12f", buf, bounds_offset(buf, mesh))
    return dict(aabb_min=np.array(f[0:3]), aabb_max=np.array(f[3:6]), top=f[6], center=np.array(f[7:10]),
                radius=f[10], cyl_radius=f[11])


def patch_bounds(buf, a, mesh_index, pos, margin=0.003):
    """Rewrite the per-mesh culling bounds so they cover the new geometry.

    Layout (12 float32, verified against vanilla helmet/vest/cape): AABB min xyz, AABB max xyz,
    top (max y + ~5 mm), bounding-sphere centre xyz, sphere radius, cylinder radius (max XZ distance
    from the centre axis). The new box is the UNION of the old box and the new geometry, so the
    bounds never shrink (conservative for culling)."""
    mesh = a.meshes[mesh_index]
    off = bounds_offset(buf, mesh)
    old = read_bounds(buf, mesh)
    mn = np.minimum(old["aabb_min"], pos.min(0) - margin)
    mx = np.maximum(old["aabb_max"], pos.max(0) + margin)
    c = 0.5 * (mn + mx)
    corners = np.array([[x, y, z] for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])])
    radius = float(np.linalg.norm(corners - c, axis=1).max())
    cyl = float(np.linalg.norm((corners - c)[:, [0, 2]], axis=1).max())
    vals = [*mn, *mx, max(old["top"], float(mx[1]) + 0.005), *c, max(old["radius"], radius), max(old["cyl_radius"], cyl)]
    struct.pack_into("<12f", buf, off, *[float(v) for v in vals])


def lod_from_vanilla(d, a, mesh_index):
    """Build a NewGeom that re-encodes a vanilla LodData unchanged (round-trip tests)."""
    mesh = a.meshes[mesh_index]
    weights = None
    if d.layout["S"]:
        weights = [[(int(d.bi[k, s]), float(d.bw[k, s])) for s in range(d.bw.shape[1]) if d.bw[k, s] > 0]
                   for k in range(len(d.pos))]
    sign = np.where(np.asarray(d.tan_w).astype(int) >= 128, -1.0, 1.0)
    col = d.raw_normal[:, 8:8 + 4 * mesh.color_count] if mesh.color_count else None
    return NewGeom(d.pos, d.nrm, d.tan, sign, d.uv0, d.tris, weights, d.uv1, col)
