#!/usr/bin/env python3
"""
Same-length string-table path alias for Snowdrop .mmaterial (BV2).
Replace one existing path string's bytes with a NEW path of EXACTLY the same byte
length -> creates a mod-private texture carrier. File length, string count, string
offsets, body, header, and all tokens are unchanged. NOT the rejected length-changing
path edit. The binding token still resolves through the same string INDEX, which now
holds the new path.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bv2

def alias(inpath, old_substr, new_path, outpath):
    m = bv2.BV2.load(inpath); raw = m.build()
    idxs = [i for i, s in enumerate(m.strings) if old_substr in s]
    if len(idxs) != 1:
        return (False, f"'{old_substr}': {len(idxs)} string matches (need exactly 1)")
    idx = idxs[0]; old = m.strings[idx]
    if len(new_path.encode("latin1")) != len(old.encode("latin1")):
        return (False, f"byte-length mismatch: new {len(new_path.encode('latin1'))} != old {len(old.encode('latin1'))}")
    off = len(m.magic) + len(m.header) + sum(len(s.encode("latin1")) + 1 for s in m.strings[:idx])
    before_tokens = list(_tag25(m))
    m.edit_string(idx, new_path); new = m.build()
    # ---- strict validation ----
    if len(new) != len(raw): return (False, "LENGTH CHANGED")
    if new[:len(m.magic)+len(m.header)] != raw[:len(m.magic)+len(m.header)]: return (False, "header changed")
    diffs = [i for i in range(len(raw)) if raw[i] != new[i]]
    span = range(off, off + len(old.encode("latin1")))
    if not diffs or any(d not in span for d in diffs):
        return (False, f"changed bytes outside target string payload: {[hex(d) for d in diffs][:8]}")
    m2 = bv2.BV2.parse(new)
    if len(m2.strings) != len(m.strings): return (False, "string count changed")
    if m2.strings[idx] != new_path: return (False, "target string did not update / did not reparse")
    if list(_tag25(m2)) != before_tokens: return (False, "a tag=25 binding token changed")
    if m2.body != m.body: return (False, "body changed")
    open(outpath, "wb").write(new)
    return (True, f"aliased idx{idx} @file+0x{off:x}: '{old.split('/')[-1]}' -> '{new_path.split('/')[-1]}'  "
                  f"({len(diffs)} payload bytes, len {len(raw)} same, {len(m.strings)} strings, tokens intact)")

def _tag25(m):
    return [(o, i) for o, tok, i, tag, s in m.dump_refs() if tag == 25]

if __name__ == "__main__":
    inp, old_sub, newp, out = sys.argv[1:5]
    ok, msg = alias(inp, old_sub, newp, out)
    print(("OK   " if ok else "FAIL ") + msg); sys.exit(0 if ok else 1)
