#!/usr/bin/env python3
"""
Re-inject an edited OBJ's vertex positions back into a .mmb (LOD0), IN PLACE — same file
length, so it loads without the character-load crash. Positions only; normals, skin weights,
UVs, faces and every other block are left untouched (correct for slight tweaks).

Requires the <edited>.obj to have the SAME vertex count + order as the export (see mmb_to_obj.py).
The tool asserts the count matches and warns if the vertices look transformed (wrong Blender
axis settings), so a mistake fails loudly instead of shipping a broken mesh.

Usage: python3 obj_to_mmb.py <edited.obj> <mmbmap.json> <orig.mmb> <out.mmb>
"""
import sys, os, json, struct, math


def read_obj_grouped(path):
    """Return (all_verts_in_order, {group_name: [verts]}). Groups split on 'o '/'g ' markers."""
    ordered, groups, cur = [], {}, None
    for line in open(path):
        if line[:2] in ("o ", "g "):
            name = line[2:].strip()
            cur = groups.setdefault(name, [])
        elif line.startswith("v "):
            p = line.split()
            v = (float(p[1]), float(p[2]), float(p[3]))
            ordered.append(v)
            (cur if cur is not None else groups.setdefault("__default__", [])).append(v)
    return ordered, groups


def resolve_per_mesh(meshes, ordered, groups):
    """Map each mesh -> its edited verts. Prefer name match (robust to object reorder);
    fall back to global vertex order. Returns {mesh_index: [verts]} or None on mismatch."""
    # name match: every mesh finds a uniquely-named group of the right size
    named = {}
    ok = True
    for mesh in meshes:
        cand = [n for n, vs in groups.items()
                if (n == mesh["name"] or n.startswith(mesh["name"]) or mesh["name"].startswith(n))
                and len(vs) == mesh["vertex_count"]]
        if len(cand) == 1:
            named[mesh["index"]] = groups[cand[0]]
        else:
            ok = False; break
    if ok and len(named) == len(meshes):
        return named, "name"
    # fallback: global order
    if len(ordered) == sum(mm["vertex_count"] for mm in meshes):
        return {mm["index"]: ordered[mm["obj_vbase"]:mm["obj_vbase"] + mm["vertex_count"]] for mm in meshes}, "order"
    return None, None


def main():
    if len(sys.argv) < 5:
        sys.exit("usage: obj_to_mmb.py <edited.obj> <mmbmap.json> <orig.mmb> <out.mmb>")
    objpath, mappath, origpath, outpath = sys.argv[1:5]
    m = json.load(open(mappath))
    ordered, groups = read_obj_grouped(objpath)
    if len(ordered) != m["total_verts"]:
        sys.exit(f"ABORT: OBJ has {len(ordered)} verts but the mesh needs {m['total_verts']} "
                 f"(same count+order required — you added/removed/merged/reordered verts).")
    per_mesh, how = resolve_per_mesh(m["meshes"], ordered, groups)
    if per_mesh is None:
        sys.exit("ABORT: could not line up the OBJ verts with the mesh groups (counts don't match "
                 "per-object and total order is ambiguous). Re-export without joining/splitting objects.")
    print(f"vertex mapping: by {how}" + ("" if how == "name" else "  (global order — keep object order stable)"))
    buf = bytearray(open(origpath, "rb").read())
    orig_len = len(buf)
    moved = 0
    max_shift = 0.0
    warn_out_of_space = 0
    for mesh in m["meshes"]:
        do, stride, ptype = mesh["data_offset"], mesh["stride"], mesh["ptype"]
        mverts = per_mesh[mesh["index"]]
        for lv in range(mesh["vertex_count"]):
            x, y, z = mverts[lv]
            b = do + lv * stride
            if ptype == 0:
                oxn, oyn, ozn, w = struct.unpack_from("<hhhh", buf, b)
                need = max(abs(x), abs(y), abs(z))
                nw = w
                if need > w:                              # vertex moved outside its quant range -> grow w (same 2 bytes)
                    nw = min(32767, int(math.ceil(need)) + 1); warn_out_of_space += 1
                xn = max(-32767, min(32767, round(x / nw * 32767))) if nw else 0
                yn = max(-32767, min(32767, round(y / nw * 32767))) if nw else 0
                zn = max(-32767, min(32767, round(z / nw * 32767))) if nw else 0
                struct.pack_into("<hhhh", buf, b, xn, yn, zn, nw)   # keep trailing weight/index bytes intact
                # measure actual shift vs original decoded pos
                ox, oy, oz = oxn / 32767 * w, oyn / 32767 * w, ozn / 32767 * w
            else:
                ox, oy, oz = struct.unpack_from("<fff", buf, b)
                struct.pack_into("<fff", buf, b, x, y, z)
            d = math.dist((x, y, z), (ox, oy, oz))
            if d > 1e-5:
                moved += 1
            max_shift = max(max_shift, d)
    if len(buf) != orig_len:
        sys.exit(f"ABORT: length changed {orig_len}->{len(buf)} (bug — refusing to write).")
    # transform sanity: a max_shift on the order of the whole model = wrong axis settings
    if max_shift > 0.5:
        print(f"WARNING: max vertex shift = {max_shift:.3f} m — that's large. If you only made slight "
              f"tweaks, your Blender OBJ export axis/scale probably differs from import. Re-export with "
              f"matching settings. (Writing anyway.)")
    open(outpath, "wb").write(buf)
    print(f"re-injected: {moved}/{m['total_verts']} verts moved, max shift {max_shift*1000:.1f} mm, "
          f"length {orig_len} (unchanged). -> {outpath}")
    if warn_out_of_space:
        print(f"  ({warn_out_of_space} verts moved outside their quant range — auto-grew their scale, fine.)")


if __name__ == "__main__":
    main()
