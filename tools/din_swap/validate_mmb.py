#!/usr/bin/env python3
"""Structural validation of a rebuilt .mmb against its vanilla container (no game needed).
Usage: validate_mmb.py <rebuilt.mmb> <vanilla_container.mmb>"""
import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mmbio


def validate(path, ref):
    a = mmbio.parse_header(path); r = mmbio.parse_header(ref)
    buf = open(path, "rb").read(); n = len(buf)
    errs = []; notes = []

    def chk(cond, msg):
        if not cond: errs.append(msg)
    chk(buf[:3] == b"MMB" and buf[3] == 19, "magic/version")
    chk(a.bone_count == r.bone_count, "bone count changed")
    chk([b.name for b in a.bones] == [b.name for b in r.bones], "bone table changed")
    chk(len(a.meshes) == len(r.meshes), "mesh count changed")
    blocks = []
    for m, rm in zip(a.meshes, r.meshes):
        chk(m.name == rm.name, f"mesh name {m.name}")
        chk(m.lod_count == rm.lod_count, f"{m.name}: lod count")
        chk(m.vertex_stride == rm.vertex_stride and m.normals_stride == rm.normals_stride, f"{m.name}: strides")
        chk(m.binding_count >= rm.binding_count, f"{m.name}: binding count shrank")
        if m.binding_count != rm.binding_count: notes.append(f"{m.name}: bindings {rm.binding_count} -> {m.binding_count}")
        for l in m.lods:
            vs, ns = m.vertex_stride, m.normals_stride
            chk(l.data_offset + l.data_size <= n, f"{m.name} LOD{l.index}: block beyond EOF")
            relb = l.vertex_data_offset_b - l.vertex_data_offset_a; relf = l.face_block_offset - l.vertex_data_offset_a
            chk(relb >= l.vertex_count * vs, f"{m.name} LOD{l.index}: vertex block too small")
            chk(relf - relb >= l.vertex_count * ns, f"{m.name} LOD{l.index}: normal block too small")
            chk(l.data_size - relf >= l.index_count * 2, f"{m.name} LOD{l.index}: index block too small")
            chk(l.size_a * 2 == l.face_block_offset, f"{m.name} LOD{l.index}: size_a != face_block_offset/2")
            chk(l.index_count % 3 == 0, f"{m.name} LOD{l.index}: index count not multiple of 3")
            blocks.append((l.data_offset, l.data_size, m.name, l.index, l.is_header_lod))
            d = mmbio.read_lod(a, m.index, l.index, buf)
            chk(np.isfinite(d.pos).all(), f"{m.name} LOD{l.index}: non-finite positions")
            chk(d.tris.size == 0 or d.tris.max() < l.vertex_count, f"{m.name} LOD{l.index}: index out of range")
            if d.layout["S"]:
                chk((d.bw_raw.sum(1) == 32767).all(), f"{m.name} LOD{l.index}: weights do not sum to 32767")
                chk(d.bi_raw.max() < m.binding_count, f"{m.name} LOD{l.index}: binding index out of range")
            if l.index == 0:
                ln = np.linalg.norm(d.nrm, axis=1)
                chk(abs(ln.mean() - 1) < 0.02 and ln.min() > 0.9, f"{m.name}: normals not unit")
                chk(d.uv0.min() >= -1e-6 and d.uv0.max() <= 1 + 1e-6, f"{m.name}: uv0 outside [0,1]")
                b = mmbio.read_bounds(buf, m)
                chk(np.all(d.pos >= b["aabb_min"] - 1e-4) and np.all(d.pos <= b["aabb_max"] + 1e-4), f"{m.name}: geometry outside header AABB")
                area = np.linalg.norm(np.cross(d.pos[d.tris[:, 1]] - d.pos[d.tris[:, 0]], d.pos[d.tris[:, 2]] - d.pos[d.tris[:, 0]]), axis=1)
                fn = np.cross(d.pos[d.tris[:, 1]] - d.pos[d.tris[:, 0]], d.pos[d.tris[:, 2]] - d.pos[d.tris[:, 0]])
                vn = np.zeros_like(d.pos)
                for k in range(3): np.add.at(vn, d.tris[:, k], fn)
                vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)
                facing = float((vn * d.nrm).sum(1).mean())
                chk(facing > 0.5, f"{m.name}: winding/normals disagree ({facing:.2f})")
                thr = [round(float(x.lod_screen_size), 4) for x in m.lods]
                notes.append(f"{m.name}: LOD0 {l.vertex_count} v / {l.index_count // 3} t, degenerate tris {int((area < 1e-12).sum())}, "
                             f"normal/winding agreement {facing:.3f}, LOD thresholds {thr}, influences/vert max "
                             f"{int((d.bw > 0).sum(1).max())}")
    blocks.sort()
    end = None
    for off, sz, nm, li, hl in blocks:
        if end is not None: chk(off == end, f"gap/overlap before {nm} LOD{li} ({off} vs {end})")
        end = off + sz
    chk(end == n, f"trailing bytes after last LOD block ({n - end})")
    first_non_header = min(off for off, sz, nm, li, hl in blocks if not hl)
    chk(a.size == first_non_header, f"header size field {a.size} != first streamed LOD offset {first_non_header}")
    return errs, notes


if __name__ == "__main__":
    errs, notes = validate(sys.argv[1], sys.argv[2])
    for x in notes: print("  ", x)
    print("RESULT:", "OK" if not errs else "FAILED"); [print("  ERROR:", e) for e in errs]
    sys.exit(1 if errs else 0)
