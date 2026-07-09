#!/usr/bin/env python3
"""
berg.py - Reader for Star Wars Outlaws (Snowdrop) BERG archive payload files
(helix/sdf/pc/data/sdf-A-*.sdfdata).

An archive is a sequence of blocks. Each block is either stored raw, or
compressed with one of:
  - zlib  (headers 78 01 / 78 5e / 78 9c / 78 da)   <-- Python can inflate
  - Oodle (Kraken/Leviathan)                        <-- proprietary, NOT handled here

This module recovers everything reachable WITHOUT Oodle:
  * the leading uncompressed region
  * every inflatable zlib stream

That is enough to recover text metadata: material graphs, shader source,
asset path references, string tables. It is NOT enough to recover Oodle-packed
bulk (most raw texture mip data). For our purpose (finding material definitions
and texture *names* to repoint at) that is exactly what we need.

Usage:
  python3 tools/berg.py scan   <keyword> [<keyword> ...]   # grep decompressed content of ALL archives
  python3 tools/berg.py inflate <archive> <outdir>         # dump all zlib blocks of one archive
"""
from __future__ import annotations
import sys, os, zlib, re, glob

ZLIB_HEADS = (b"\x78\x01", b"\x78\x5e", b"\x78\x9c", b"\x78\xda")

import struct

# Each BERG block is preceded by a 20-byte header:
#   u32 sentinel (per-archive constant, e.g. 0xDABC02E3)
#   u32 typeA, u32 typeB   (content/schema descriptor, constant within an archive)
#   u32 usize              (uncompressed size)
#   u32 csize              (compressed payload size)
# followed by `csize` payload bytes. Blocks chain: next_hdr = payload_off + csize.
# Payload is zlib (78 xx), Oodle (Kraken/Leviathan), or stored raw (usize==csize).
BLOCK_HDR = struct.Struct("<5I")


def iter_blocks(data: bytes):
    """Deterministically walk the block table. Yields dicts with offset, sizes,
    codec ('zlib'|'raw'|'oodle'|'bad'), and (for zlib/raw) decompressed bytes.
    Stops if the chain desyncs (sentinel mismatch)."""
    if data[:4] != b"BERG":
        return
    n = len(data)
    sentinel = None
    off = 8  # after 'BERG' + u32
    while off + 20 <= n:
        magic, tA, tB, usize, csize = BLOCK_HDR.unpack_from(data, off)
        if sentinel is None:
            sentinel = magic
        if magic != sentinel or csize == 0 or csize > n or off + 20 + csize > n:
            # chain desync — bail rather than emit garbage
            return
        p = off + 20
        payload = data[p:p + csize]
        rec = {"hdr": off, "payload": p, "usize": usize, "csize": csize,
               "typeA": tA, "typeB": tB}
        if payload[:1] == b"\x78" and ((payload[0] << 8) | payload[1]) % 31 == 0:
            try:
                out = zlib.decompress(payload)
                rec["codec"] = "zlib"
                rec["data"] = out
            except Exception:
                rec["codec"] = "bad"
                rec["data"] = b""
        elif usize == csize:
            rec["codec"] = "raw"
            rec["data"] = payload
        else:
            rec["codec"] = "oodle"   # or other non-zlib codec; not decoded here
            rec["data"] = b""
        yield rec
        off = p + csize


def iter_zlib_blocks(data: bytes, min_out: int = 32):
    """Yield (offset, decompressed_bytes) for every inflatable zlib stream.

    Fast path: only positions whose two-byte zlib header passes the CMF/FLG
    check (0x78 && (u16be %% 31 == 0)) are tried, and slicing uses a memoryview
    so no multi-MB tail copy happens per candidate. Oodle bytes that coincidentally
    start with 0x78 almost never pass %%31, and the rare ones fail decompress fast."""
    mv = memoryview(data)
    n = len(data)
    seen_end = 0
    i = data.find(b"\x78", 0)
    while i != -1 and i + 1 < n:
        if i >= seen_end and ((data[i] << 8) | data[i + 1]) % 31 == 0:
            dob = zlib.decompressobj()
            try:
                out = dob.decompress(mv[i:], 64_000_000)
                out += dob.flush()
                if len(out) >= min_out and dob.eof:
                    consumed = n - i - len(dob.unused_data)
                    seen_end = i + consumed
                    yield i, out
                    i = data.find(b"\x78", seen_end)
                    continue
            except Exception:
                pass
        i = data.find(b"\x78", i + 1)


def leading_raw(data: bytes) -> bytes:
    """The bytes from just after the 8-byte BERG header up to the first zlib
    stream — often uncompressed schema/shader text in data archives."""
    first = len(data)
    for h in ZLIB_HEADS:
        j = data.find(h, 8)
        if 0 <= j < first:
            first = j
    return data[8:first]


def archive_text(path: str) -> bytes:
    """All Oodle-free bytes of an archive, concatenated (raw lead + zlib blocks)."""
    data = open(path, "rb").read()
    if data[:4] != b"BERG":
        return b""
    parts = [leading_raw(data)]
    for _off, out in iter_zlib_blocks(data):
        parts.append(out)
    return b"\x00".join(parts)


def cmd_scan(keywords):
    game = "/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws"
    archives = sorted(glob.glob(os.path.join(game, "helix/sdf/pc/data/sdf-A-*.sdfdata")))
    kws = [k.encode() for k in keywords]
    hits = {k: [] for k in keywords}
    for n, path in enumerate(archives):
        try:
            blob = archive_text(path)
        except Exception as e:
            sys.stderr.write(f"[err] {path}: {e}\n")
            continue
        base = os.path.basename(path)
        for kw, kwb in zip(keywords, kws):
            if kwb in blob:
                # capture a little context around each hit (first 3)
                ctxs = []
                start = 0
                for _ in range(3):
                    idx = blob.find(kwb, start)
                    if idx < 0:
                        break
                    seg = blob[max(0, idx-40):idx+80]
                    seg = re.sub(rb"[^\x20-\x7e]", b".", seg)
                    ctxs.append(seg.decode("latin1"))
                    start = idx + 1
                hits[kw].append((base, blob.count(kwb), ctxs))
        if n % 100 == 0:
            sys.stderr.write(f"  scanned {n}/{len(archives)} ...\n")
    for kw in keywords:
        print(f"\n===== keyword {kw!r}: {len(hits[kw])} archives =====")
        for base, cnt, ctxs in hits[kw][:40]:
            print(f"  {base}  x{cnt}")
            for c in ctxs:
                print(f"      {c}")


def cmd_inflate(archive, outdir):
    os.makedirs(outdir, exist_ok=True)
    data = open(archive, "rb").read()
    raw = leading_raw(data)
    if raw:
        open(os.path.join(outdir, "0000_rawlead.bin"), "wb").write(raw)
    for i, (off, out) in enumerate(iter_zlib_blocks(data)):
        open(os.path.join(outdir, f"{i:04d}_zlib_0x{off:x}.bin"), "wb").write(out)
    print(f"wrote blocks to {outdir}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "scan":
        cmd_scan(sys.argv[2:])
    elif len(sys.argv) == 4 and sys.argv[1] == "inflate":
        cmd_inflate(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
