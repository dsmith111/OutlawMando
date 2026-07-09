#!/usr/bin/env python3
"""
scale_helmet.py - Uniformly scale a Star Wars Outlaws skeletal-mesh (.mmb) around
its own centroid, in place (same file length). Built for shrinking the Boba helmet
toward Mandalorian proportions.

Format facts (from AlexP0/SWOutlawsMeshTool, tools/ref/swoutlaws_meshtool.py):
  - Each Mesh has N LODs; LOD vertex data lives at lod.data_offset in the file.
  - position_type 0 vertex = 8 bytes: int16 xn, int16 yn, int16 zn, int16 w.
      world pos = (xn/32767 * w, yn/32767 * w, zn/32767 * w)
    followed by weight/index bytes (rest of vertex_stride). We touch ONLY xn,yn,zn
    (6 bytes), keeping w and everything else, so the file length never changes.
  - position_type 1 vertex = 12 bytes: float32 x,y,z (we scale those directly).
Pivot = LOD0 axis-aligned bbox center, shared by all LODs so they stay coincident.

Because the helmet is a rigid single-bone binding (weight_count==1), scaling all
vertices about the shared centroid = a clean shrink-in-place after skinning.
Bounding volumes in the .mmb/graph object are left as-is (slightly generous cull
bounds are harmless).

Usage: python3 tools/scale_helmet.py <in.mmb> <out.mmb> [scale=0.85]
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(__file__))
import mmb_core as M


def read_lod_positions(buf, off, count, stride, ptype):
    ps = []
    for v in range(count):
        b = off + v * stride
        if ptype == 0:
            xn, yn, zn, w = struct.unpack_from('<hhhh', buf, b)
            ps.append((xn / 32767.0 * w, yn / 32767.0 * w, zn / 32767.0 * w, w))
        else:
            x, y, z = struct.unpack_from('<fff', buf, b)
            ps.append((x, y, z, None))
    return ps


def bbox_center(ps):
    xs = [p[0] for p in ps]; ys = [p[1] for p in ps]; zs = [p[2] for p in ps]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)


def clamp_i16(i):
    return max(-32767, min(32767, i))


def scale_mmb(inpath, outpath, scale=0.85):
    buf = bytearray(open(inpath, 'rb').read())
    path = inpath
    sys.modules["bpy"].context.scene.SWOMT.AssetPath = path
    asset = M.SkeletalMeshAsset()
    asset.parse(open(inpath, 'rb'))
    total_v = 0
    for mesh in asset.meshes:
        stride = mesh.vertex_stride
        ptype = mesh.position_type
        # shared pivot from the highest-detail LOD (LOD0)
        lod0 = mesh.lods[0]
        p0 = read_lod_positions(buf, lod0.data_offset, lod0.vertex_count, stride, ptype)
        cx, cy, cz = bbox_center(p0)
        print(f"mesh {mesh.name!r}: pivot=({cx:.4f},{cy:.4f},{cz:.4f}) stride={stride} ptype={ptype}")
        for li, lod in enumerate(mesh.lods):
            if lod.vertex_count <= 0 or lod.data_offset <= 0:
                continue
            for v in range(lod.vertex_count):
                b = lod.data_offset + v * stride
                if ptype == 0:
                    xn, yn, zn, w = struct.unpack_from('<hhhh', buf, b)
                    px = xn / 32767.0 * w; py = yn / 32767.0 * w; pz = zn / 32767.0 * w
                    px = cx + scale * (px - cx)
                    py = cy + scale * (py - cy)
                    pz = cz + scale * (pz - cz)
                    if w != 0:
                        nxn = clamp_i16(round(px / w * 32767))
                        nyn = clamp_i16(round(py / w * 32767))
                        nzn = clamp_i16(round(pz / w * 32767))
                        struct.pack_into('<hhh', buf, b, nxn, nyn, nzn)  # keep w at b+6
                else:
                    x, y, z = struct.unpack_from('<fff', buf, b)
                    x = cx + scale * (x - cx); y = cy + scale * (y - cy); z = cz + scale * (z - cz)
                    struct.pack_into('<fff', buf, b, x, y, z)
                total_v += 1
    assert len(buf) == os.path.getsize(inpath), "length changed!"
    open(outpath, 'wb').write(buf)
    print(f"scaled {total_v} vertices by {scale}; wrote {outpath} ({len(buf)} bytes, same length)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 0.85
    scale_mmb(sys.argv[1], sys.argv[2], scale)
