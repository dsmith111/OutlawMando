#!/usr/bin/env python3
"""
find_assets.py - Locate asset strings across all Star Wars Outlaws BERG archives.

For each sdf-A-*.sdfdata it searches, without needing Oodle:
  1. the RAW bytes (catches uncompressed BV2 objects / text)
  2. every zlib block's decompressed bytes (catches zlib-packed graphs/materials)
Oodle-only blocks are skipped (can't decode), but most material/text metadata is
raw or zlib, which is what we need for names/paths.

Writes a report to stdout: which archives contain each keyword, with context.
"""
import sys, os, glob, zlib, struct

GAME = "/mnt/g/SteamLibrary/steamapps/common/Star Wars Outlaws"
SENT = b"\xe3\x02\xbc\xda"  # 0xDABC02E3 zlib-block sentinel
BLOCK_HDR = struct.Struct("<5I")


def zlib_text(data: bytes) -> bytes:
    """Concatenate all inflated zlib blocks (sentinel-anchored, resync-safe)."""
    out = []
    i = data.find(SENT)
    while i != -1:
        try:
            _m, _a, _b, usize, csize = BLOCK_HDR.unpack_from(data, i)
            p = i + 20
            if 0 < csize <= len(data) - p and data[p:p+1] == b"\x78":
                out.append(zlib.decompress(data[p:p+csize]))
                i = data.find(SENT, p + csize)
                continue
        except Exception:
            pass
        i = data.find(SENT, i + 1)
    return b"\x00".join(out)


def contexts(blob: bytes, kw: bytes, maxn=2):
    res = []
    start = 0
    for _ in range(maxn):
        idx = blob.find(kw, start)
        if idx < 0:
            break
        seg = bytes(b if 32 <= b < 127 else 46 for b in blob[max(0, idx-30):idx+70])
        res.append(seg.decode("latin1"))
        start = idx + 1
    return res


def main(keywords):
    archives = sorted(glob.glob(os.path.join(GAME, "helix/sdf/pc/data/sdf-A-*.sdfdata")))
    kws = [k.encode() if isinstance(k, str) else k for k in keywords]
    hits = {k: [] for k in keywords}
    for n, path in enumerate(archives):
        try:
            data = open(path, "rb").read()
        except Exception as e:
            sys.stderr.write(f"[err] {path}: {e}\n")
            continue
        base = os.path.basename(path)
        ztext = zlib_text(data) if SENT in data else b""
        for kw, kwb in zip(keywords, kws):
            in_raw = kwb in data
            in_zlib = kwb in ztext
            if in_raw or in_zlib:
                src = ("raw" if in_raw else "") + ("+zlib" if in_zlib else "")
                ctx = contexts(data if in_raw else ztext, kwb)
                hits[kw].append((base, src, data.count(kwb), ctx))
        if n % 100 == 0:
            sys.stderr.write(f"  {n}/{len(archives)} scanned...\n")
            sys.stderr.flush()
    print(f"\n===== SCAN COMPLETE: {len(archives)} archives =====")
    for kw in keywords:
        print(f"\n### keyword {kw!r}: {len(hits[kw])} archives")
        for base, src, cnt, ctx in hits[kw][:30]:
            print(f"  {base} [{src}] rawcount={cnt}")
            for c in ctx:
                print(f"      {c}")


if __name__ == "__main__":
    kws = sys.argv[1:] or [
        "canon_boba", "gn_metal", "boba_fett", "beskar", ".mmaterial",
        "gn_metal_light", "gn_metal_clean", "gn_metal_polish", "gn_metal_bright",
        "gn_metal_chrome", "generic_textures", "mat_chr_botm_5",
    ]
    main(kws)
