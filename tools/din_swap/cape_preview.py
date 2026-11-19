#!/usr/bin/env python3
"""Preview a donor cape (.mmb, bind pose, LOD0 of its CLOTH_RENDER submesh) on the staged Din body.
   cape_preview.py [cape.mmb] [neck]     neck = close-up of the shoulders/neck (back, both back quarters, top)"""
import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mmbio, preview
from preview_build import staged_items, W, ROOT
args = [a for a in sys.argv[1:] if a != "neck"]; neck = "neck" in sys.argv[1:]
cape = args[0] if args else os.path.join(ROOT, "local/din_swap/containers/cape/chr_acc_2_silver_canto_police_cape.mmb")
tag = args[1] if len(args) > 1 else "p3_cape"
a = mmbio.parse_header(cape)
items = staged_items()
for mi, m in enumerate(a.meshes):
    if "RENDER" not in m.name: continue
    d = mmbio.read_lod(a, mi, 0)
    o = os.path.join(W, tag + "_donor.obj"); preview.write_obj(o, d.pos, d.tris, None, d.nrm)
    items.append(dict(obj=o, color=[0.10, 0.085, 0.075], roughness=0.85))
if neck:
    print(preview.render(W, tag + "_neck", items, views=("back", "qb", "side", "top"), res=(1000, 760), crop=[[-0.42, 1.12, -0.32], [0.42, 1.66, 0.16]]))
else:
    print(preview.render(W, tag, items, views=("front", "side", "back", "qb"), res=(820, 1080), crop=[[-0.72, -0.02, -0.40], [0.72, 1.80, 0.35]]))
