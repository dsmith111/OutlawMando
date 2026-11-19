#!/usr/bin/env python3
"""
bc.py — vectorised BC1 (DXT1) / BC3 (DXT5) encoders + SINGLE-LEVEL DDS writers.

Why single-level: Star Wars Outlaws streams the upper mip levels of a texture separately from the
texture asset itself, and loose-file loaders do not serve custom streamed mips. A loose DDS that
carries a mip chain is therefore displayed from its small tail only (a 1024² / 11-mip carrier
rendered as one flat average colour in game). The game's own non-streamed texture assets are
single-level DDS files (e.g. the vanilla helmet `_d`: 256², DXT1, mipMapCount 1, flags 0xa1007),
and that container is the one that has been seen to display real per-texel detail. So every
carrier is written the same way: one level, vanilla-style header.

Colour endpoints are fitted along the block's principal axis (not the bounding-box diagonal), which
matters for packed maps where channels are anti-correlated (metal up / roughness down).
"""
import os
import struct

import numpy as np


def _blocks(img):
    h, w, c = img.shape
    assert h % 4 == 0 and w % 4 == 0
    return img.reshape(h // 4, 4, w // 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(-1, 16, c).astype(np.float64)


def _unblocks(blk, h, w):
    c = blk.shape[2]
    return blk.reshape(h // 4, w // 4, 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(h, w, c)


def _to565(c):
    c = np.clip(np.rint(c), 0, 255).astype(np.uint32)
    return ((c[:, 0] * 31 + 127) // 255) << 11 | ((c[:, 1] * 63 + 127) // 255) << 5 | ((c[:, 2] * 31 + 127) // 255)


def _from565(v):
    r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31
    return np.stack([(r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)], 1).astype(np.float64)


def _color_blocks(rgb_blk, opaque_bc1):
    """rgb_blk (N,16,3) -> (N,8) uint8 BC1 colour blocks (always 4-colour mode)."""
    n = len(rgb_blk)
    mean = rgb_blk.mean(1, keepdims=True)
    d = rgb_blk - mean
    cov = np.einsum("nij,nik->njk", d, d)
    v = np.ones((n, 3)) / np.sqrt(3.0) + cov.sum(2) * 1e-6
    for _ in range(10):                                   # power iteration -> principal axis
        v = np.einsum("njk,nk->nj", cov, v)
        ln = np.linalg.norm(v, axis=1, keepdims=True)
        v = np.where(ln > 1e-9, v / np.maximum(ln, 1e-9), 1.0 / np.sqrt(3.0))
    proj = np.einsum("nij,nj->ni", d, v)
    e0 = mean[:, 0, :] + proj.max(1)[:, None] * v
    e1 = mean[:, 0, :] + proj.min(1)[:, None] * v
    c0 = _to565(e0); c1 = _to565(e1)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    p0 = _from565(c0); p1 = _from565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3.0, (p0 + 2 * p1) / 3.0], 1)
    idx = ((rgb_blk[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3).argmin(2).astype(np.uint32)
    if opaque_bc1:
        idx[c0 == c1] = 0            # equal endpoints select BC1's 3-colour mode; index 3 would be transparent
    bits = (idx << (2 * np.arange(16, dtype=np.uint32))[None, :]).sum(1).astype(np.uint32)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0:2] = c0.astype("<u2").view(np.uint8).reshape(n, 2)
    out[:, 2:4] = c1.astype("<u2").view(np.uint8).reshape(n, 2)
    out[:, 4:8] = bits.astype("<u4").view(np.uint8).reshape(n, 4)
    return out


def _alpha_blocks(a_blk):
    """a_blk (N,16) -> (N,8) uint8 BC3 alpha blocks (8-value interpolated mode)."""
    n = len(a_blk)
    a0 = np.clip(np.rint(a_blk.max(1)), 0, 255); a1 = np.clip(np.rint(a_blk.min(1)), 0, 255)
    w = np.array([[7, 0], [0, 7], [6, 1], [5, 2], [4, 3], [3, 4], [2, 5], [1, 6]], np.float64) / 7.0
    pal = a0[:, None] * w[None, :, 0] + a1[:, None] * w[None, :, 1]
    idx = np.abs(a_blk[:, :, None] - pal[:, None, :]).argmin(2).astype(np.uint64)
    idx[a0 == a1] = 0
    bits = (idx << (3 * np.arange(16, dtype=np.uint64))[None, :]).sum(1).astype(np.uint64)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0] = a0.astype(np.uint8); out[:, 1] = a1.astype(np.uint8)
    out[:, 2:8] = bits.astype("<u8").view(np.uint8).reshape(n, 8)[:, :6]
    return out


def encode_bc1(rgba):
    return _color_blocks(_blocks(rgba[..., :3]), True).tobytes()


def encode_bc3(rgba):
    col = _color_blocks(_blocks(rgba[..., :3]), False)
    alp = _alpha_blocks(_blocks(rgba[..., 3:4])[:, :, 0])
    return np.concatenate([alp, col], 1).tobytes()


def decode_bc1(data, w, h, n_off=0, stride=8):
    raw = np.frombuffer(data, np.uint8).reshape(-1, stride)[:, n_off:n_off + 8]
    n = len(raw)
    c0 = raw[:, 0:2].copy().view("<u2")[:, 0].astype(np.uint32); c1 = raw[:, 2:4].copy().view("<u2")[:, 0].astype(np.uint32)
    bits = raw[:, 4:8].copy().view("<u4")[:, 0]
    p0 = _from565(c0); p1 = _from565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) / 3.0, (p0 + 2 * p1) / 3.0], 1)
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))[None, :]) & 3
    return _unblocks(pal[np.arange(n)[:, None], idx], h, w)


def decode_bc3(data, w, h):
    raw = np.frombuffer(data, np.uint8).reshape(-1, 16)
    n = len(raw)
    rgb = decode_bc1(data, w, h, 8, 16)
    a0 = raw[:, 0].astype(np.float64); a1 = raw[:, 1].astype(np.float64)
    bits = np.zeros((n, 8), np.uint8); bits[:, :6] = raw[:, 2:8]
    bits = bits.view("<u8")[:, 0]
    wts = np.array([[7, 0], [0, 7], [6, 1], [5, 2], [4, 3], [3, 4], [2, 5], [1, 6]], np.float64) / 7.0
    pal = a0[:, None] * wts[None, :, 0] + a1[:, None] * wts[None, :, 1]
    idx = ((bits[:, None] >> (3 * np.arange(16, dtype=np.uint64))[None, :]) & 7).astype(int)
    a = _unblocks(pal[np.arange(n)[:, None], idx][:, :, None], h, w)
    return np.concatenate([rgb, a], 2)


def _header(w, h, fourcc, linear_size):
    """Vanilla-style header of the game's own non-streamed texture assets (flags 0xa1007, caps 0x1000)."""
    hdr = struct.pack("<4sIIIIIII", b"DDS ", 124, 0x000A1007, h, w, linear_size, 0, 1) + bytes(44)
    pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc, 0, 0, 0, 0, 0)
    caps = struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    out = hdr + pf + caps
    assert len(out) == 128
    return out


def write_dds(path, rgba, fmt):
    """Write ONE level. fmt: 'DXT1' (no alpha), 'DXT5', or 'BGRA8' (uncompressed)."""
    rgba = np.ascontiguousarray(rgba.astype(np.uint8))
    h, w, _ = rgba.shape
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if fmt == "DXT1":
        data = _header(w, h, b"DXT1", w * h // 2) + encode_bc1(rgba)
    elif fmt == "DXT5":
        data = _header(w, h, b"DXT5", w * h) + encode_bc3(rgba)
    elif fmt == "BGRA8":
        hdr = struct.pack("<4sIIIIIII", b"DDS ", 124, 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000, h, w, w * 4, 0, 1) + bytes(44)
        pf = struct.pack("<IIIIIIII", 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
        caps = struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
        data = hdr + pf + caps + rgba[..., [2, 1, 0, 3]].tobytes()
    else:
        raise ValueError(fmt)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def read_dds(path):
    """Decode a single-level DDS written by write_dds (or an uncompressed BGRA8 DDS) -> RGBA float."""
    b = open(path, "rb").read()
    h, w = struct.unpack_from("<II", b, 12)
    fourcc = b[84:88]
    if fourcc == b"DXT1":
        rgb = decode_bc1(b[128:128 + w * h // 2], w, h)
        return np.concatenate([rgb, np.full((h, w, 1), 255.0)], 2)
    if fourcc == b"DXT5":
        return decode_bc3(b[128:128 + w * h], w, h)
    return np.frombuffer(b, np.uint8, w * h * 4, 128).reshape(h, w, 4)[..., [2, 1, 0, 3]].astype(np.float64)


if __name__ == "__main__":
    # self-test: vanilla header reproduced byte-for-byte; encode/decode error on a synthetic image
    import sys
    van = sys.argv[1] if len(sys.argv) > 1 else None
    if van:
        ref = open(van, "rb").read(128)
        print("DXT1 256 header identical to vanilla:", _header(256, 256, b"DXT1", 256 * 256 // 2) == ref)
    rng = np.random.default_rng(0)
    y, x = np.mgrid[0:64, 0:64]
    img = np.stack([(x * 4) % 256, 255 - (x * 4) % 256, (y * 3) % 256, (x + y) * 2 % 256], 2).astype(np.float64)
    img += rng.normal(0, 3, img.shape); img = np.clip(img, 0, 255)
    e1 = np.abs(decode_bc1(encode_bc1(img), 64, 64) - img[..., :3]).mean()
    e3 = np.abs(decode_bc3(encode_bc3(img), 64, 64) - img).mean(axis=(0, 1))
    print("BC1 mean abs error (anti-correlated R/G test image):", round(float(e1), 2))
    print("BC3 mean abs error per channel RGBA:", np.round(e3, 2))
