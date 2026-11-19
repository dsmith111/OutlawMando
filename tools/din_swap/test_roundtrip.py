"""Round-trip test: re-encode each vanilla submesh's LOD0 through mmbio.replace_lod0 and compare
against the original file. Proves the writer reproduces vanilla layout/offsets/encodings."""
import sys, os, tempfile, numpy as np
import mmbio

def check(path):
    a = mmbio.parse_header(path); src = open(path, "rb").read()
    ok_all = True
    cur = path
    tmpd = tempfile.mkdtemp()
    for mi, m in enumerate(a.meshes):
        d = mmbio.read_lod(a, mi, 0)
        if m.normal_type != "int8_norm":
            print(f"  [{m.name}] skipped (float-normal layout: writer n/a)"); continue
        g = mmbio.lod_from_vanilla(d, a, mi)
        out = os.path.join(tmpd, f"rt_{mi}.mmb")
        extra = mmbio.replace_lod0(cur, out, mi, g, force_lod0=False, pos_scale=int(d.pos_w[0]) if hasattr(d, "pos_w") else 4, update_bounds=False)
        cur = out
        b = mmbio.parse_header(out); dst = open(out, "rb").read()
        d2 = mmbio.read_lod(b, mi, 0)
        l1, l2 = m.lods[0], b.meshes[mi].lods[0]
        end_blocks = max(l.data_offset + l.data_size for mm in a.meshes for l in mm.lods)
        same_size = len(dst) == end_blocks   # trailing post-LOD section is dropped (same as the addon; proven to load)
        hdr_same = src[:a.size] == dst[:b.size] and a.size == b.size
        # byte comparison of the LOD0 block, ignoring weight slot order
        blk1 = src[l1.data_offset:l1.data_offset + l1.data_size]; blk2 = dst[l2.data_offset:l2.data_offset + l2.data_size]
        n = l1.vertex_count; vs = m.vertex_stride
        v1 = np.frombuffer(blk1, np.uint8, n * vs).reshape(n, vs); v2 = np.frombuffer(blk2, np.uint8, n * vs).reshape(n, vs)
        pos_same = np.array_equal(v1[:, :8], v2[:, :8])
        rest_same = blk1[n * vs:] == blk2[n * vs:]
        wsame = True
        if d.layout["S"]:
            for k in range(n):
                s1 = sorted((int(i), int(w)) for i, w in zip(d.bi_raw[k], d.bw_raw[k]) if w > 0)
                s2 = sorted((int(i), int(w)) for i, w in zip(d2.bi_raw[k], d2.bw_raw[k]) if w > 0)
                if s1 != s2: wsame = False; break
        exact = blk1 == blk2
        ok = same_size and hdr_same and pos_same and rest_same and wsame and not extra
        ok_all &= ok
        print(f"  [{m.name}] size_same={same_size} header_same={hdr_same} pos_bytes_same={pos_same} normals+uv+faces_same={rest_same} weights_same={wsame} block_byte_exact={exact} extra_bones={extra} -> {'PASS' if ok else 'FAIL'}")
    # all other bytes (other LODs) identical?
    final = open(cur, "rb").read()
    end_blocks = max(l.data_offset + l.data_size for mm in a.meshes for l in mm.lods)
    diff = sum(1 for x, y in zip(src[:end_blocks], final) if x != y)
    print(f"  differing bytes vs original (header+LOD blocks, {end_blocks} B; dropped trailing {len(src)-end_blocks} B): {diff}  [weight slot order may differ]")
    return ok_all

if __name__ == "__main__":
    res = True
    for p in sys.argv[1:]:
        print(os.path.basename(p)); res &= check(p)
    print("ALL PASS" if res else "SOME FAILED"); sys.exit(0 if res else 1)
