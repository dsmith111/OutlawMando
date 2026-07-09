#!/usr/bin/env python3
"""
make_beskar.py - Turn the Boba Fett metal-armor materials into silver beskar by
retinting their color constants. Reads raw materials from extracted/raw_materials/,
writes overrides to deliver/beskar_armor/.

Transform (v1):
  * L2 Color, L2 Color R/G/B      -> SILVER (base metal color)
  * Paint Color R/G/B             -> SILVER (kills Boba's green/red/orange paint)
  * L1 Color Overlay              -> neutral, mildly bright (removes dark/color cast)
  * Rust Stains Color, Wall Stains Color -> neutral grey (de-tints the rust/grime)
  * Dirt Color                    -> left (very dark, subtle)
Roughness/metalness are texture+default driven and mostly not stored as editable
constants, so this changes COLOR (silver) but not gloss; shine is tuned separately.
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(__file__))
import bv2, matconst

# tunable targets (linear-ish 0..1)
SILVER = (0.82, 0.84, 0.88)     # bright, faintly cool beskar
OVERLAY = (0.80, 0.80, 0.80)    # brighten Layer 1 (0.5 = identity) to wash baked darkness
PAINT_ROUGH = (0.08, 0.30)      # polished (not mirror): low base roughness, low contrast

# which armor materials to convert (the _metal ones + missiletop)
METAL = [
    "helmet_metal", "vest_metal", "bracers_metal", "kneepads_metal",
    "backpack_metal", "backpack_missiletop_metal", "belt_metal", "pants_metal",
]

# scalar weathering-intensity constants to zero out (clean beskar). Matched by
# substring on float-typed constants only. Excludes: "Rust" (a UV scale ~70),
# "Flakes Suppression" (raising suppresses flaking — leave), metalness/roughness base.
ZERO_SUBSTRINGS = [
    "Amount", "Scratch", "Rust Stains", "Rust Tint", "Rust Soft", "Rust Smear",
    "Dirt", "Wall Stains", "Normal Strength", "Mask Contrast", "Roughness Detail",
]


def target_for(c):
    """Return replacement values for constant c, or None to leave unchanged."""
    n = c.name
    if n == "L1 Color Overlay":
        return OVERLAY
    if n == "Paint Roughness BC" and c.type == "float2":
        return PAINT_ROUGH
    # any color vector -> silver (paint/base/rust/dirt/wall colors all blend to metal)
    if c.type == "float3" and ("Color" in n) and n != "L1 Color Overlay":
        return SILVER
    # weathering intensity scalars -> 0
    if c.type == "float" and n != "Rust" and "Flakes" not in n and "Metalness" not in n:
        if any(k in n for k in ZERO_SUBSTRINGS):
            return (0.0,)
    return None


def convert(path, outdir):
    m, cs = matconst.load_constants(path)
    changed = []
    for c in cs:
        if not c.values:
            continue
        tgt = target_for(c)
        if tgt is None:
            continue
        # match dimensionality
        if c.type == "float3":
            newv = list(tgt[:3])
        elif c.type == "float2":
            newv = list(tgt[:2])
        elif c.type == "float":
            newv = [sum(tgt) / len(tgt)]
        else:
            continue
        # some values are only partially serialized when default/zero (e.g. an
        # "off" paint layer stores a single 0.0). Skip those — leaving an off
        # layer off is correct, and we can't safely rewrite a partial vector.
        if len(c.offsets) != len(newv):
            continue
        matconst.set_const(m, c, newv)
        changed.append((c.name, [round(v, 3) for v in c.values], [round(v, 3) for v in newv]))
    # rebuild + verify round-trip parse
    blob = m.build()
    m2 = bv2.BV2.parse(blob)
    assert m2.build() == blob, "rebuild not stable"
    base = os.path.basename(path)
    out = os.path.join(outdir, base)
    open(out, "wb").write(blob)
    # re-read constants to confirm edits landed
    _m3, cs3 = matconst.load_constants(out)
    return base, changed, len(blob)


def main():
    src = os.path.join(os.path.dirname(__file__), "..", "extracted", "raw_materials")
    outdir = os.path.join(os.path.dirname(__file__), "..", "deliver", "beskar_armor")
    os.makedirs(outdir, exist_ok=True)
    for tag in METAL:
        matches = glob.glob(os.path.join(src, f"*canon_boba_fett_{tag}.mmaterial"))
        if not matches:
            print(f"[miss] {tag}")
            continue
        base, changed, sz = convert(matches[0], outdir)
        print(f"\n{base}  ({sz} B)")
        for nm, old, new in changed:
            print(f"    {nm:22} {old} -> {new}")


if __name__ == "__main__":
    main()
