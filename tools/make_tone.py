#!/usr/bin/env python3
"""
make_tone.py - Generate a beskar ARMOR tone variant using ONLY proven-safe edits.

Proven safe (mid_rough loaded in-game): float3 color constants + the float2
"Paint Roughness BC". NOT touched: any weathering/roughness *scalar* (one of those
crashed in v2), and any (none)/unserialized constant (editing would change length).

Levers we actually control:
  * L1 Color Overlay (float3)  - base-metal brightness/tint. Vanilla ~0.12 (dark).
  * L2 Color        (float3)   - second-layer steel color. Vanilla ~0.20.
  * Paint Roughness BC (float2)- paint-layer gloss [base, contrast]. Only bites if
                                 the paint layer is enabled (Paint>0); harmless else.
Optionally (experimental, --paint): turn the paint layer ON to expose a controllable
gloss layer. Paint + Paint Color R/G/B are serialized floats/float3 -> same-length safe.

Usage:
  python3 tools/make_tone.py <variant_name> OVL=r,g,b L2=r,g,b [PR=b,c] [--paint AMT]
Example:
  python3 tools/make_tone.py cool_bright OVL=0.46,0.50,0.58 L2=0.44,0.49,0.60 PR=0.12,0.45
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(__file__))
import bv2, matconst

METAL = ["helmet_metal", "vest_metal", "bracers_metal", "kneepads_metal",
         "backpack_metal", "backpack_missiletop_metal", "belt_metal", "pants_metal"]


def parse_args(argv):
    name = argv[1]
    p = {"paint": None}
    for a in argv[2:]:
        if a == "--paint":
            p["paint"] = 1.0
        elif a.startswith("--paint="):
            p["paint"] = float(a.split("=", 1)[1])
        elif "=" in a:
            k, v = a.split("=", 1)
            p[k] = [float(x) for x in v.split(",")]
    return name, p


def target_for(c, p):
    n = c.name
    if n == "L1 Color Overlay" and "OVL" in p:
        return p["OVL"]
    if n == "L2 Color" and "L2" in p:
        return p["L2"]
    if n == "Paint Roughness BC" and c.type == "float2" and "PR" in p:
        return p["PR"]
    if p["paint"] is not None:
        if n == "Paint" and c.type == "float":
            return (p["paint"],)
        # when enabling paint, also silver-ise the paint color so it isn't Boba green/red
        if n in ("Paint Color R", "Paint Color G", "Paint Color B") and c.type == "float3" and "L2" in p:
            return p["L2"]
    return None


def convert(path, outdir, p):
    m, cs = matconst.load_constants(path)
    changed = []
    for c in cs:
        if not c.values:
            continue
        tgt = target_for(c, p)
        if tgt is None:
            continue
        if c.type == "float3":
            newv = list(tgt[:3])
        elif c.type == "float2":
            newv = list(tgt[:2])
        elif c.type == "float":
            newv = [tgt[0]]
        else:
            continue
        if len(c.offsets) != len(newv):      # partial/unserialized -> skip (length safety)
            continue
        old = [round(v, 3) for v in c.values]
        matconst.set_const(m, c, newv)
        changed.append((c.name, old, [round(v, 3) for v in newv]))
    blob = m.build()
    assert bv2.BV2.parse(blob).build() == blob, "rebuild not stable"
    base = os.path.basename(path)
    open(os.path.join(outdir, base), "wb").write(blob)
    return base, changed, len(blob)


def main():
    name, p = parse_args(sys.argv)
    src = os.path.join(os.path.dirname(__file__), "..", "extracted", "raw_materials")
    outdir = os.path.join(os.path.dirname(__file__), "..", "deliver", f"beskar_armor_{name}")
    os.makedirs(outdir, exist_ok=True)
    print(f"variant '{name}' -> {outdir}\nparams: {p}\n")
    for tag in METAL:
        matches = glob.glob(os.path.join(src, f"*canon_boba_fett_{tag}.mmaterial"))
        if not matches:
            print(f"[miss] {tag}"); continue
        base, changed, sz = convert(matches[0], outdir, p)
        print(f"{base} ({sz} B)")
        for nm, old, new in changed:
            print(f"    {nm:20} {old} -> {new}")


if __name__ == "__main__":
    main()
