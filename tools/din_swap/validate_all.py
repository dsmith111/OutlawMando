#!/usr/bin/env python3
"""Validate every staged .mmb against the vanilla container it was built from."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_din, validate_mmb
bad = 0
for name, (src, rel, slots) in build_din.CONTAINERS.items():
    errs, notes = validate_mmb.validate(os.path.join(build_din.STAGE, rel), src)
    lod0 = "; ".join(n.split(": ", 1)[0] + " " + n.split("LOD0 ")[1].split(",")[0] for n in notes if "LOD0" in n)
    print(f"   {name:9s} {'OK    ' if not errs else 'FAILED'} {lod0}")
    for e in errs: print("      ERROR:", e); bad += 1
print("   ALL CONTAINERS VALID" if not bad else f"   {bad} ERRORS")
sys.exit(1 if bad else 0)
