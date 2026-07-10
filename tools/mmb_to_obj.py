#!/usr/bin/env python3
"""
Export a Snowdrop .mmb skeletal mesh (LOD0) to a Wavefront OBJ for editing in Blender,
plus a sidecar <out>.mmbmap.json that obj_to_mmb.py needs to write your edits back.

ONLY LOD0 is exported (the close-up mesh). Editing rule, non-negotiable:
    MOVE existing vertices only. Do NOT add, delete, merge ("Merge by Distance"),
    remesh, decimate, subdivide, or reorder vertices. Vertex count + order must stay identical.
Grab / proportional-edit / smooth / sculpt-Grab are all fine.

Blender OBJ import/export: use the SAME axis settings both ways (e.g. Forward=Y, Up=Z, no
scale) so positions round-trip. The re-injector sanity-checks this and warns if verts look
transformed.

Usage: python3 mmb_to_obj.py <in.mmb> <out.obj>
"""
import sys, os, io, json, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmb_core as M
M.io = io


def export(inpath, outobj):
    sys.modules["bpy"].context.scene.SWOMT.AssetPath = inpath
    buf = open(inpath, "rb").read()
    a = M.SkeletalMeshAsset(); a.parse(open(inpath, "rb"))
    v_lines, vt_lines, f_lines = [], [], []
    vbase = 0
    meshmap = []
    for mi, mesh in enumerate(a.meshes):
        l = mesh.lods[0]
        stride, ptype = mesh.vertex_stride, mesh.position_type
        pos = l.get_vertex_positions(mesh.extract_mesh_file(open(inpath, "rb")))
        tris = l.get_triangles(mesh.extract_mesh_file(open(inpath, "rb")))
        try:
            uvs = l.get_uvs(mesh.extract_mesh_file(open(inpath, "rb")), 0)
            if not uvs or len(uvs) != l.vertex_count:
                uvs = None
        except Exception:
            uvs = None
        ws = []
        for v in range(l.vertex_count):
            if ptype == 0:
                _, _, _, w = struct.unpack_from("<hhhh", buf, l.data_offset + v * stride)
                ws.append(w)
            else:
                ws.append(None)
        for v in range(l.vertex_count):
            x, y, z = pos[v][:3]
            v_lines.append(f"v {x:.8f} {y:.8f} {z:.8f}")   # 8 dp: float32 meshes round-trip ~exactly
        if uvs:
            for uv in uvs:
                vt_lines.append(f"vt {uv[0]:.6f} {uv[1]:.6f}")
        f_lines.append(f"g {mesh.name}")
        f_lines.append(f"o {mesh.name}")
        for t in tris:
            i, j, k = (t[0] + 1 + vbase, t[1] + 1 + vbase, t[2] + 1 + vbase)
            if uvs:
                f_lines.append(f"f {i}/{i} {j}/{j} {k}/{k}")
            else:
                f_lines.append(f"f {i} {j} {k}")
        meshmap.append(dict(index=mi, name=mesh.name, vertex_count=l.vertex_count,
                            data_offset=l.data_offset, stride=stride, ptype=ptype,
                            obj_vbase=vbase, has_uv=bool(uvs), w=ws))
        vbase += l.vertex_count
        print(f"  mesh[{mi}] {mesh.name!r}: {l.vertex_count} verts, {len(tris)} tris, uv={'yes' if uvs else 'no'}")
    with open(outobj, "w") as f:
        f.write(f"# {os.path.basename(inpath)} LOD0 — MOVE verts only; keep count+order.\n")
        f.write("\n".join(v_lines) + "\n")
        if vt_lines:
            f.write("\n".join(vt_lines) + "\n")
        f.write("\n".join(f_lines) + "\n")
    json.dump(dict(src=os.path.abspath(inpath), total_verts=vbase, meshes=meshmap),
              open(outobj + ".mmbmap.json", "w"))
    print(f"exported {vbase} verts across {len(a.meshes)} mesh(es) -> {outobj}")
    print(f"map -> {outobj}.mmbmap.json")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: mmb_to_obj.py <in.mmb> <out.obj>")
    export(sys.argv[1], sys.argv[2])
