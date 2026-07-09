#!/usr/bin/env python3
"""
analyze_log.py - Parse dstorage_proxy.log and locate the Boba helmet mesh read.

Log grammar (from the Phase-0 proxy):
  O file=<ptr> path=<archive path>
  R <seq> F file=<ptr> off=<u64> sz=<u32> comp=<0|1|128> dst=<0..4> ucs=<u32> name=<str>
  R <seq> M mem=<ptr> sz=<u32> comp=.. dst=.. ucs=.. name=..

The helmet .mmb is 260404 bytes uncompressed, so we rank file-sourced requests by:
  (a) request Name containing helmet/boba/headw   (strongest, if the game names requests)
  (b) UncompressedSize or Size near 260404        (mesh-sized reads)
For each candidate we print the archive path + offset + size + compression so Phase 1
can match on (archive-basename, offset, size).

Usage: python3 analyze_log.py <path-to-dstorage_proxy.log> [target_uncompressed_size=260404]
"""
import sys, re, os
from collections import defaultdict

TARGET = 260404  # loose helmet .mmb size
NAME_HINTS = ("helmet", "boba", "headw", "chr_headw")

def main():
    path = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else TARGET
    ptr2path = {}
    reqs = []          # (seq, srckind, ptr, off, sz, comp, dst, ucs, name)
    o_count = 0
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("O "):
                m = re.match(r"O file=(\S+) path=(.*)", line)
                if m:
                    ptr2path[m.group(1)] = m.group(2); o_count += 1
            elif line.startswith("R "):
                m = re.match(r"R (\d+) F file=(\S+) off=(\d+) sz=(\d+) comp=(\d+) dst=(\d+) ucs=(\d+) name=(.*)", line)
                if m:
                    reqs.append(("F", int(m.group(1)), m.group(2), int(m.group(3)),
                                 int(m.group(4)), int(m.group(5)), int(m.group(6)),
                                 int(m.group(7)), m.group(8)))
                    continue
                m = re.match(r"R (\d+) M mem=(\S+) sz=(\d+) comp=(\d+) dst=(\d+) ucs=(\d+) name=(.*)", line)
                if m:
                    reqs.append(("M", int(m.group(1)), m.group(2), 0,
                                 int(m.group(3)), int(m.group(4)), int(m.group(5)),
                                 int(m.group(6)), m.group(7)))

    print(f"parsed: {len(reqs)} requests, {o_count} file-opens, {len(ptr2path)} unique archives\n")

    # archives touched
    print("=== archives opened ===")
    for p in sorted(set(ptr2path.values())):
        print("  ", os.path.basename(p))
    print()

    def score(r):
        kind, seq, ptr, off, sz, comp, dst, ucs, name = r
        s = 0
        nml = name.lower()
        if any(h in nml for h in NAME_HINTS): s += 1000
        for v in (ucs, sz):
            if v == target: s += 500
            elif abs(v - target) <= 4096: s += 200
            elif abs(v - target) <= 65536: s += 40
        return s

    ranked = sorted(reqs, key=score, reverse=True)
    print(f"=== top candidates for helmet mesh (target ucs≈{target}) ===")
    print(f"{'score':>5} {'seq':>7} {'k':1} {'off':>12} {'size':>9} {'ucs':>9} {'c':>1} {'d':>1}  archive / name")
    shown = 0
    for r in ranked:
        sc = score(r)
        if sc == 0 or shown >= 25: break
        kind, seq, ptr, off, sz, comp, dst, ucs, name = r
        arch = os.path.basename(ptr2path.get(ptr, "?")) if kind == "F" else "(memory)"
        print(f"{sc:>5} {seq:>7} {kind} {off:>12} {sz:>9} {ucs:>9} {comp:>1} {dst:>1}  {arch}  {name[:60]}")
        shown += 1
    if shown == 0:
        print("  (no size/name matches — dumping largest reads instead)")
        for r in sorted(reqs, key=lambda x: max(x[4], x[7]), reverse=True)[:20]:
            kind, seq, ptr, off, sz, comp, dst, ucs, name = r
            arch = os.path.basename(ptr2path.get(ptr, "?")) if kind == "F" else "(memory)"
            print(f"      {seq:>7} {kind} off={off} sz={sz} ucs={ucs} comp={comp} dst={dst} {arch} {name[:50]}")

if __name__ == "__main__":
    main()
