#!/usr/bin/env python3
"""
matconst.py - Read/write named material constants in Snowdrop BV2 .mmaterial files.

Builds on bv2.py. A material body is a stream of constant DEFINITION records
(maps: {editable,name,originalPinId,pinId,type,value}) plus, for constants whose
value is non-default, a run of 0x03+float32 emitted immediately BEFORE the
definition record that owns it. The run length matches the type
(float=1, float2=2, float3=3, float4=4).

parse_constants() returns a list of Const(name, type, values, offsets) where
offsets are ABSOLUTE body offsets of each float32 (i.e. the byte after each 0x03),
suitable for bv2.set_float_at(offset).

Validated: boots material -> Color Overlay float3 == (0.4969, 0.4969, 0.4969).
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import List, Optional
import bv2

TYPE_LEN = {"float": 1, "float2": 2, "float3": 3, "float4": 4}
STRUCT_KEYS = {"editable", "name", "originalPinId", "pinId", "type", "value"}


@dataclass
class Const:
    name: str
    type: str
    values: List[float]
    offsets: List[int]  # absolute body offsets of each float32


def _events(m: "bv2.BV2"):
    """Yield ('float', off, val) and ('def', name, type) in stream order."""
    b = m.body
    S = m.strings
    i = 0
    n = len(b)
    pending_floats = []  # (off, val)
    while i < n:
        c = b[i]
        if c == 0x03 and i + 5 <= n:
            v = struct.unpack_from("<f", b, i + 1)[0]
            pending_floats.append((i + 1, v))
            i += 5
            continue
        # map definition record: tag 0x18 (6 keys) or 0x14 (5 keys)
        if c in (0x18, 0x14):
            nkeys = c >> 2
            # read keys
            keys = []
            j = i + 1
            for _ in range(nkeys):
                if j + 1 >= n:
                    break
                tok = b[j] | (b[j + 1] << 8)
                keys.append(S[tok >> 5] if (tok >> 5) < len(S) else None)
                j += 2
            # expect values-delimiter 0x1c
            if j < n and b[j] == 0x1c and set(k for k in keys if k) <= STRUCT_KEYS:
                j += 1
                # first value token = constant name
                name = None
                cty = None
                # scan a bounded window of value tokens for name (first string not struct)
                # and the type string (floatN/texture)
                vj = j
                toks = []
                while vj + 1 < n and len(toks) < 12:
                    # stop if we hit another record/terminator
                    if b[vj] in (0x18, 0x14, 0x00) or (b[vj] == 0x03):
                        break
                    tok = b[vj] | (b[vj + 1] << 8)
                    idx = tok >> 5
                    s = S[idx] if 0 <= idx < len(S) else None
                    toks.append(s)
                    vj += 2
                # name = first string that isn't a struct key / type keyword
                for s in toks:
                    if s and s not in STRUCT_KEYS and s not in TYPE_LEN and s != "texture":
                        name = s
                        break
                for s in toks:
                    if s in TYPE_LEN or s == "texture":
                        cty = s
                        break
                yield ("def", name, cty, pending_floats)
                pending_floats = []
                i = j
                continue
        i += 1


def parse_constants(m: "bv2.BV2") -> List[Const]:
    consts = []
    for ev in _events(m):
        _tag, name, cty, floats = ev
        if cty in TYPE_LEN and name:
            need = TYPE_LEN[cty]
            use = floats[-need:] if len(floats) >= need else floats
            consts.append(Const(name, cty,
                                 [v for _o, v in use],
                                 [o for o, _v in use]))
    return consts


def load_constants(path: str):
    m = bv2.BV2.load(path)
    return m, parse_constants(m)


def set_const(m: "bv2.BV2", const: Const, new_values):
    """Overwrite a constant's float values in the body."""
    assert len(new_values) == len(const.offsets), (const.name, len(const.offsets))
    b = bytearray(m.body)
    for off, val in zip(const.offsets, new_values):
        struct.pack_into("<f", b, off, float(val))
    m.body = bytes(b)


if __name__ == "__main__":
    import sys, os
    p = sys.argv[1] if len(sys.argv) > 1 else \
        "helix/materials/mat_chr_botm_5_canon_boba_fett_boots_metal.mmaterial.orig"
    m, cs = load_constants(p)
    print(f"{os.path.basename(p)}: {len(cs)} valued constants")
    for c in cs:
        print(f"  {c.name:32} {c.type:7} = {[round(v,4) for v in c.values]}  @{[hex(o) for o in c.offsets]}")
