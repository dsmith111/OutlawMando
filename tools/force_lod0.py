#!/usr/bin/env python3
"""
Force a Snowdrop .mmb to render LOD0 at every distance (kills LOD-swap flicker/pop).

Mechanism: each LOD header carries a float `lod_screen_size` (at start_offset+32) — a
distance/LOD metric that INCREASES with distance. LOD0 is always 0.0; the engine picks the
coarsest LOD whose threshold the metric has crossed. Setting LOD1..N thresholds to a value
the metric can never reach (1e6; real values top out ~0.04) makes LOD0 the only selectable
LOD -> full-res mesh at all distances. Same-length edit (float32 in place) -> no load crash.
Served loose by Raindrop like any other .mmb override.

Use when a mesh's higher LODs differ from LOD0 in ways you can't/ won't reconcile (added
geometry only on LOD0, cloth-sim binding only on LOD0, etc). Cost: full-res always for that
mesh — negligible for a single hero/player asset.

Usage: python3 force_lod0.py <in.mmb> <out.mmb> [submesh_name_substr]
  submesh filter optional; default = all submeshes. LOD0 & the sim mesh (1-LOD) are safe.
"""
import sys, os, io, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mmb_core as M
M.io = io

FAR = 1.0e6


def force(inpath, outpath, name_substr=None):
    buf = bytearray(open(inpath, "rb").read())
    a = M.SkeletalMeshAsset(); a.parse(open(inpath, "rb"))
    touched = []
    for mesh in a.meshes:
        if name_substr and name_substr not in mesh.name:
            continue
        if len(mesh.lods) <= 1:
            continue  # nothing to force (e.g. a 1-LOD cloth-sim cage)
        for l in mesh.lods:
            if l.index == 0:
                continue
            off = l.start_offset + 32
            old = struct.unpack_from("<f", buf, off)[0]
            struct.pack_into("<f", buf, off, FAR)
            touched.append((mesh.name, l.index, off, old))
    assert len(buf) == os.path.getsize(inpath), "length changed"
    open(outpath, "wb").write(buf)
    # verify
    b = M.SkeletalMeshAsset(); b.parse(open(outpath, "rb"))
    print(f"forced LOD0-only on {outpath}")
    for mesh in b.meshes:
        if name_substr and name_substr not in mesh.name:
            continue
        ss = [round(l.lod_screen_size, 4) for l in mesh.lods]
        print(f"  {mesh.name}: thresholds={ss}")
    for nm, idx, off, old in touched:
        print(f"   {nm} LOD{idx} @{off}: {old:.6f} -> {FAR:.0f}")
    assert all(mesh.lods[0].lod_screen_size == 0.0 for mesh in b.meshes
               if not name_substr or name_substr in mesh.name), "LOD0 changed!"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    force(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
