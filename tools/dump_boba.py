#!/usr/bin/env python3
"""
dump_boba.py - Extract the canon_boba_fett materials, their texture/shader refs,
and the material PATHS referenced by the Boba mesh/graph objects.

Targeted (does NOT scan all 763 archives): reads only the archives known to hold
Boba assets:
  0010 = materials archive (raw \xffBV2 material objects)
  0081, 0085, 0086 = Boba mesh objects (reference materials by path)
  0011 = more Boba mesh/graph objects

Outputs to  extracted/boba/ :
  * <name>.mmaterial       raw material objects carved from 0010 (best-effort bounds)
  * refs.txt               every distinct plaintext string mentioning canon_boba / mat_chr / .mmaterial / .dds / .mshader
"""
import os, re, sys

GAME = "/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws/helix/sdf/pc/data"
OUT = os.path.join(os.path.dirname(__file__), "..", "extracted", "boba")
MAGIC = b"\xffBV2"

# archives to inspect and why
ARCHIVES = {
    "sdf-A-0010.sdfdata": "materials",
    "sdf-A-0011.sdfdata": "meshes/graphobjects",
    "sdf-A-0081.sdfdata": "meshes",
    "sdf-A-0085.sdfdata": "meshes",
    "sdf-A-0086.sdfdata": "meshes",
}

STR = re.compile(rb"[\x20-\x7e]{4,}")
INTEREST = re.compile(rb"(canon_boba|mat_chr|\.mmaterial|\.mshader|gn_metal|beskar|sd_gn_)", re.I)


def clean_strings(seg: bytes):
    """NUL-delimited printable strings (the material string table splits cleanly here)."""
    out = []
    for p in seg.split(b"\x00"):
        if len(p) >= 4 and all(32 <= b < 127 for b in p):
            out.append(p.decode("latin1"))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    all_refs = set()
    boba_paths = set()
    dds_paths = set()
    for fn, why in ARCHIVES.items():
        path = os.path.join(GAME, fn)
        try:
            d = open(path, "rb").read()
        except Exception as e:
            print(f"[skip] {fn}: {e}"); continue
        # object boundaries by magic
        offs = []
        i = d.find(MAGIC)
        while i != -1:
            offs.append(i); i = d.find(MAGIC, i + 4)
        offs.append(len(d))
        nboba = 0
        for k in range(len(offs) - 1):
            a, b = offs[k], offs[k + 1]
            seg = d[a:b]
            if b"canon_boba" not in seg and b"boba_fett" not in seg:
                continue
            nboba += 1
            ss = clean_strings(seg)
            for s in ss:
                if INTEREST.search(s.encode()):
                    all_refs.add(s)
                if ".mmaterial" in s:
                    boba_paths.add(s)
                if ".dds" in s:
                    dds_paths.add(s)
            # save material objects (from the materials archive) for editing
            if why == "materials" and b"\xffBV2" == seg[:4]:
                # best-effort: carve [a, b) — trailing bytes belong to framing, trim later
                name = f"{fn.replace('.sdfdata','')}_obj_{k:05d}_0x{a:x}.bv2"
                open(os.path.join(OUT, name), "wb").write(seg)
        print(f"{fn} ({why}): {nboba} boba-related objects")
    with open(os.path.join(OUT, "refs.txt"), "w") as f:
        f.write("=== .mmaterial paths mentioned near boba objects ===\n")
        for s in sorted(boba_paths):
            f.write("  " + s + "\n")
        f.write("\n=== .dds texture refs ===\n")
        for s in sorted(dds_paths):
            f.write("  " + s + "\n")
        f.write("\n=== all interesting strings ===\n")
        for s in sorted(all_refs):
            f.write("  " + s + "\n")
    print(f"\nwrote {len(boba_paths)} .mmaterial paths, {len(dds_paths)} dds refs, {len(all_refs)} interesting strings to {OUT}/refs.txt")


if __name__ == "__main__":
    main()
