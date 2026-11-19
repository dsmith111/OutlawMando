#!/usr/bin/env python3
"""Preview helper: write game-space meshes as OBJ (converted to Blender RH Z-up) and render
orthographic views with headless Blender (Windows exe driven from WSL)."""
import json, os, subprocess
import numpy as np

BLENDER = "/mnt/c/Program Files/Blender Foundation/Blender 5.1/blender.exe"
HERE = os.path.dirname(os.path.abspath(__file__))


def wpath(p):
    return subprocess.check_output(["wslpath", "-w", os.path.abspath(p)]).decode().strip()


def g2b(p):
    """game (LH, Y up, +Z front) -> Blender (RH, Z up, front = -Y)."""
    p = np.asarray(p, np.float64)
    return np.stack([-p[:, 0], -p[:, 2], p[:, 1]], 1)


def write_obj(path, pos, tris, uv=None, nrm=None):
    """pos/nrm in game space; uv in file convention (v down). Winding flipped for the RH conversion."""
    P = g2b(pos)
    with open(path, "w") as f:
        for v in P: f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        if uv is not None:
            for t in uv: f.write(f"vt {t[0]:.6f} {1.0 - t[1]:.6f}\n")
        if nrm is not None:
            for n in g2b(nrm): f.write(f"vn {n[0]:.5f} {n[1]:.5f} {n[2]:.5f}\n")
        for a, b, c in np.asarray(tris) + 1:
            a, b, c = a, c, b
            if uv is not None and nrm is not None: f.write(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n")
            elif uv is not None: f.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")
            elif nrm is not None: f.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")
            else: f.write(f"f {a} {b} {c}\n")


def joints_obj(path, positions, size=0.012):
    """Write small octahedra at joint positions (game space)."""
    V = []; F = []
    o = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float) * size
    faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    for k, p in enumerate(np.asarray(positions)):
        V.append(o + p); F += [(a + 6 * k, b + 6 * k, c + 6 * k) for a, b, c in faces]
    write_obj(path, np.concatenate(V), np.array(F))


def render(outdir, name, items, views=("front", "side", "back"), res=(800, 1100), crop=None, timeout=600):
    """items: list of dict(obj=path, color=[r,g,b], texture=path|None, alpha=1.0, metallic, roughness, normal).
    crop: optional [[xmin,ymin,zmin],[xmax,ymax,zmax]] in game space to frame."""
    os.makedirs(outdir, exist_ok=True)
    spec = dict(out=wpath(outdir) + "\\" + name, views=list(views), res=list(res), items=[])
    for it in items:
        d = dict(it); d["obj"] = wpath(it["obj"])
        for k in ("texture", "normal", "orm"):
            if d.get(k): d[k] = wpath(d[k])
        spec["items"].append(d)
    if crop is not None:
        c = g2b(np.array(crop, float)); spec["crop"] = [c.min(0).tolist(), c.max(0).tolist()]
    sp = os.path.join(outdir, name + "_spec.json")
    json.dump(spec, open(sp, "w"), indent=1)
    r = subprocess.run([BLENDER, "--background", "--factory-startup", "--python", wpath(os.path.join(HERE, "bl_render_spec.py")), "--", wpath(sp)],
                       capture_output=True, text=True, timeout=timeout)
    tail = [l for l in r.stdout.splitlines() if l.startswith(("RENDERED", "ERR", "Traceback", "  File")) or "Error" in l]
    if not any(l.startswith("RENDERED") for l in tail):
        print("\n".join(r.stdout.splitlines()[-25:])); print(r.stderr[-2000:])
    return [os.path.join(outdir, f"{name}_{v}.png") for v in views]
