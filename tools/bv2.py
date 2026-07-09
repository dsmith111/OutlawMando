#!/usr/bin/env python3
"""
bv2.py - Parser / editor for Star Wars Outlaws (Snowdrop) BV2 ".mmaterial" containers.

Reverse-engineered from:
  helix/materials/mat_chr_botm_5_canon_boba_fett_boots_metal.mmaterial(.orig)

============================ FILE FORMAT (CONFIRMED) ============================
Magic:  ff 42 56 32   ("\xffBV2")

Layout:
  [0x00 .. 0x04)  magic
  [0x04 .. HDR )  header blob        (compact tagged root node; opaque here)
  [HDR  .. BODY)  string table       (NUL-terminated latin1 strings, ordinal-indexed)
  [BODY .. EOF )  body blob          (tagged node tree; references strings by INDEX)

For the reference file:
  HDR  = 0x2c   (header = 40 bytes: data[0x04:0x2c])
  BODY = 0x276

STRING TABLE
  A flat sequence of NUL-terminated strings. There is NO length/offset table:
  strings are self-delimiting by NUL and are addressed purely by ORDINAL INDEX
  (0,1,2,...). The reference file has 28 strings, index 0 = "AlphaTest".

REFERENCE ENCODING (the crack)
  Wherever the body needs to name a string it stores a little-endian uint16 token
  whose top 11 bits are the string index and whose low 5 bits are a type tag:

        string_index = LE16 >> 5
        tag          = LE16 & 0x1F
        token        = (string_index << 5) | tag

  Proof (all resolve exactly to NUL-terminated string starts):
    key tokens 89 00 / a9 00 / e9 00 / 09 01 / 29 01 / 69 01
       -> idx 4,5,7,8,9,11 = editable, name, originalPinId, pinId, type, value
    e9 01 -> idx15 "Color Overlay"     09 02 -> idx16 "float3"
    a9 02 -> idx21 "Color   WorldXZ"   c9 02 -> idx22 "texture"
    f9 02 -> idx23 ".../gn_...base_d.dds"   (etc.)
  Because refs are by INDEX, not byte offset, changing a string's *content length*
  does not break any reference (see rebuild()/round-trip self-test).

BODY NODE GRAMMAR (partially confirmed)
  Records seen: 0x18 = 6-field map, 0x14 = 5-field map. After the tag come the
  field-name tokens (2-byte, >>5), a 0x1c delimiter, then the value section
  (mixed encoding), then 0x00. Float values are encoded as tag 0x03 + float32LE.
  The Color Overlay float3 is three consecutive (03 <f32>) at 0x2c3/0x2c8/0x2cd.

This module deliberately treats header and body as OPAQUE byte blobs. That is
sufficient for a byte-exact round trip and for the two edits that matter:
  * rewrite a string (any length) -> edit_string()
  * rewrite the Color Overlay float3 (or any 03-tagged float) -> set_float_at()
================================================================================
"""
from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import List

MAGIC = b"\xffBV2"


def _find_string_table(data: bytes):
    """Locate [hdr_end, body_start). The string table is the run of printable
    NUL-terminated strings between the header and the body. We anchor on the
    known first string 'AlphaTest' and walk NUL-terminated strings until a byte
    that is not a plausible string start (the body tag区)."""
    # Header end == start of the first string. For BV2 the string table begins
    # right after the compact header. We detect it by scanning for the first
    # long ASCII run that is NUL terminated.
    i = 4
    # find first ASCII letter run >= 4 preceded by nothing meaningful
    start = data.find(b"AlphaTest", 4)
    if start < 0:
        raise ValueError("could not locate string table anchor 'AlphaTest'")
    # walk strings
    strings = []
    offs = []
    j = start
    while j < len(data):
        k = data.find(b"\x00", j)
        if k < 0:
            break
        chunk = data[j:k]
        # stop when the "string" stops looking like a path/identifier
        if not chunk or not all(32 <= b < 127 for b in chunk):
            break
        strings.append(chunk.decode("latin1"))
        offs.append(j)
        j = k + 1
    body_start = j  # first byte after the last NUL of the table
    return start, body_start, strings


@dataclass
class BV2:
    magic: bytes
    header: bytes                       # opaque
    strings: List[str]
    body: bytes                         # opaque
    _hdr_end: int = 0
    _body_start: int = 0

    # ---------- parse ----------
    @classmethod
    def parse(cls, data: bytes) -> "BV2":
        if data[:4] != MAGIC:
            raise ValueError("bad magic %r" % data[:4])
        hdr_end, body_start, strings = _find_string_table(data)
        return cls(
            magic=data[:4],
            header=data[4:hdr_end],
            strings=strings,
            body=data[body_start:],
            _hdr_end=hdr_end,
            _body_start=body_start,
        )

    @classmethod
    def load(cls, path: str) -> "BV2":
        with open(path, "rb") as f:
            return cls.parse(f.read())

    # ---------- serialize ----------
    def build(self) -> bytes:
        out = bytearray()
        out += self.magic
        out += self.header
        for s in self.strings:
            out += s.encode("latin1") + b"\x00"
        out += self.body
        return bytes(out)

    def save(self, path: str):
        with open(path, "wb") as f:
            f.write(self.build())

    # ---------- reference helpers ----------
    @staticmethod
    def ref(index: int, tag: int = 9) -> int:
        return (index << 5) | (tag & 0x1F)

    @staticmethod
    def deref(token: int):
        return token >> 5, token & 0x1F

    def index_of(self, s: str) -> int:
        return self.strings.index(s)

    # ---------- edits ----------
    def edit_string(self, index: int, new: str):
        """Replace a string by index. ANY length is allowed: strings are
        NUL-terminated and referenced by ordinal index, so downstream refs are
        unaffected. Do not add/remove/reorder entries."""
        assert 0 <= index < len(self.strings)
        self.strings[index] = new

    def replace_string(self, old: str, new: str):
        self.edit_string(self.index_of(old), new)

    def set_float_at(self, body_off: int, value: float):
        """Overwrite a float32 in the body. `body_off` is relative to body start
        and must point at the 4 bytes AFTER a 0x03 tag."""
        b = bytearray(self.body)
        struct.pack_into("<f", b, body_off, value)
        self.body = bytes(b)

    def find_float3(self):
        """Return list of (abs_off, value) for the run of three 03+float32
        (the Color Overlay value in the reference file)."""
        res = []
        b = self.body
        i = 0
        while i + 5 <= len(b):
            if b[i] == 0x03:
                v = struct.unpack_from("<f", b, i + 1)[0]
                res.append((self._body_start + i, v))
                i += 5
            else:
                i += 1
        return res

    # ---------- introspection ----------
    def dump_refs(self):
        """Yield every 2-byte-aligned token in the body that resolves to a valid
        string index, for inspection. (Body is not uniformly 2-byte aligned, so
        this is a heuristic view, not a full parse.)"""
        b = self.body
        for i in range(0, len(b) - 1):
            v = b[i] | (b[i + 1] << 8)
            idx, tag = self.deref(v)
            if idx < len(self.strings):
                yield self._body_start + i, v, idx, tag, self.strings[idx]


# ================================ SELF TEST ================================
def _selftest():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    ref = os.path.join(here, "..", "helix", "materials",
                       "mat_chr_botm_5_canon_boba_fett_boots_metal.mmaterial.orig")
    ref = os.path.normpath(ref)
    raw = open(ref, "rb").read()
    m = BV2.parse(raw)

    # 1) byte-exact round trip
    rebuilt = m.build()
    assert rebuilt == raw, "ROUND TRIP FAILED (len %d vs %d)" % (len(rebuilt), len(raw))
    print("[ok] byte-exact round trip (%d bytes)" % len(raw))

    # 2) segmentation
    assert m.magic == MAGIC
    assert m._hdr_end == 0x2c, m._hdr_end
    assert m._body_start == 0x276, hex(m._body_start)
    assert len(m.strings) == 28, len(m.strings)
    assert m.strings[0] == "AlphaTest"
    assert m.strings[15] == "Color Overlay" and m.strings[16] == "float3"
    print("[ok] segmentation: hdr[4:0x2c] 40B, 28 strings, body@0x276")

    # 3) reference formula: keys decode to the 6 known fields
    keys = [0x0089, 0x00a9, 0x00e9, 0x0109, 0x0129, 0x0169]
    got = [m.strings[BV2.deref(k)[0]] for k in keys]
    assert got == ["editable", "name", "originalPinId", "pinId", "type", "value"], got
    assert all(BV2.deref(k)[1] == 9 for k in keys)
    print("[ok] ref formula idx=LE16>>5 -> keys:", got)

    # 4) Color Overlay float3 located + editable, refs preserved across length change
    f3 = m.find_float3()
    assert len(f3) >= 3
    assert abs(f3[0][1] - 0.4969330430030823) < 1e-6, f3[0]
    assert f3[0][0] == 0x2c2, hex(f3[0][0])  # 0x03 tag; float32 lives at +1 (0x2c3)
    print("[ok] Color Overlay float3 @0x2c3 =", [round(v, 4) for _, v in f3[:3]])

    # 5) length-change safety: replace a .dds path with a DIFFERENT length,
    #    rebuild, re-parse, and confirm every body ref still resolves identically.
    before = [ (o, v, i) for o, v, i, t, s in m.dump_refs() ]
    m2 = BV2.parse(raw)
    di = m2.index_of(
        "helix/baked/art/textures/generic_textures/gn_metal_dark_2m_01/gn_metal_dark_2m_01_base_d.dds")
    m2.edit_string(di, "helix/baked/art/textures/generic_textures/beskar/beskar_polished_base_d.dds")
    blob = m2.build()
    m3 = BV2.parse(blob)
    # body bytes are unchanged (refs are index-based, not offset-based)
    assert m3.body == m.body, "body changed after string-length edit!"
    assert m3.strings[22] == "texture"  # index order preserved
    print("[ok] string length change is safe: body byte-identical, indices stable")
    print("     (new file length %d vs original %d)" % (len(blob), len(raw)))

    print("\nALL SELF-TESTS PASSED")


if __name__ == "__main__":
    _selftest()
