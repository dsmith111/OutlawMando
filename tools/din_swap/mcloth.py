#!/usr/bin/env python3
"""mcloth.py — reader for Snowdrop `.mcloth` (cloth simulation setup), reverse-engineered here.

Container: a flat stream of chunks   [id u8][type u8][0xD7 0xEC][size u32 (includes this 8-byte header)][payload]
preceded by small u32 headers. Objects are not length-nested in a way we need: named sections start
with a type-0x02 string chunk ("<sim mesh>_Cloth0_LOD0", ... one per sim LOD), and the chunks that
follow belong to that section until the next name.

What is decoded (type-0x11 chunks of a "<sim mesh>_Cloth0_LODn" section; N = particle count padded to 16):
  id 2    u32   particle count (= vertex count of the .mmb's CLOTH_SIM submesh, SAME ORDER, same positions)
  id 11   N x float4  particle rest position xyz + w, w = -2 for pinned particles (sim-mesh red == 0), else 0
  id 46   float3 gravity (0, -10, 0)
  id 178  u32 (N / 16, 9)      batches, number of per-particle channel slots
  id 180  9 x (u32 batches, float step, float min, float max)   one slot per channel; unused slots all zero
  id 179  N x u8 per used slot  quantised channel: value = min + byte * step
          slot 2 = MAX DISTANCE in metres: how far the particle may stray from its animated (skinned)
          position. Canto police cape: exactly sim-mesh red / 255 * 0.4 -> 0 .. 3.9 cm (red capped at 25);
          Lando's seated cape: 1 .. 3 cm from a separate map. Padding entries are 255.
The same tables are repeated, identical, in every sim LOD section.

Simulation settings ("states"; the solver is Ubisoft's SMotion — step names in the exe: InjectAnim,
ApplyDampingAndInertia, ApplyMaxLengthConstraints, ApplyBlendConstraints, Springs, ApplyLimitConstraints,
ApplyCollisionConstraints, BlendInAnimation). A section holds one default settings block plus one per
state (id 82 = state count: Canto 1, Lando seated 3 — picked by the gear graph's ClothPreset/presetId).
A block = id 5 (149 B packed struct) followed by the same values as separate chunks (46 gravity,
7 flags, 8 five floats, 45, 47-49, 44, 26, 43, 78):
  id 5 +0   u8 limit mode: 2 where the slot-2 limit is in force (Canto; Lando's seated state), 0 in Lando's free states
       +2   float3 gravity
       +14  float  (authored: Canto 0.1, Lando 0 / 0.03 — damping?)
       +26  float  LIMIT RADIUS = max of the slot-2 table (Canto 0.0392157, Lando seated 0.03).
                   Patching the table alone (rev 8) changed nothing in game; this header value must
                   be raised with it (rev 9).
       +35  float  1.05 Canto / 1.19-2.0 Lando (max-length stretch?)   +95 float time step (1/30, 1/60)
Hero-cape states (Lando) additionally carry a per-state table id 84/86/89 = red/255*0.4 (0..0.40 m).
"""
import struct, sys
import numpy as np

MAGIC = b"\xd7\xec"


def chunks(buf, start=0, end=None):
    """Yield (offset, id, type, size, payload_offset) for every well-formed chunk in [start, end)."""
    end = len(buf) if end is None else end
    i = start
    while i + 8 <= end:
        if buf[i + 2:i + 4] == MAGIC:
            size = struct.unpack_from("<I", buf, i + 4)[0]
            if 8 <= size <= end - i:
                yield i, buf[i], buf[i + 1], size, i + 8
                i += size
                continue
        i += 1


def sections(buf):
    """[(name, first chunk offset, [(off, id, type, size, payload_off), ...])] split at name chunks."""
    out = []; cur = None
    for c in chunks(buf):
        off, cid, typ, size, po = c
        if typ == 0x02:
            s = buf[po:po + size - 8].split(b"\0")[0]
            if len(s) >= 4 and all(32 <= b < 127 for b in s):
                cur = (s.decode(), off, []); out.append(cur); continue
        if cur is not None:
            cur[2].append(c)
    return out


def typed(buf, cs, typ=0x11):
    """{id: [(payload offset, payload bytes), ...]} for the chunks of one section with the given type."""
    d = {}
    for o, cid, t, size, po in cs:
        if t == typ: d.setdefault(cid, []).append((po, size - 8))
    return d


MAXDIST_SLOT = 2


def max_distance(buf, cs):
    """Per-particle max-distance table of one sim section.
    -> dict(n, pos (N,3), dist (N,) metres, byte_off, slot_off, batches, step, lo, hi)"""
    d = typed(buf, cs)
    n = struct.unpack_from("<I", buf, d[2][0][0])[0]
    batches, nslots = struct.unpack_from("<2I", buf, d[178][0][0])
    bo, nb = d[179][0]; so, ns = d[180][0]
    assert ns == nslots * 16 and nb == batches * 16, "expected exactly one stored channel (max distance)"
    used = [i for i in range(nslots) if any(buf[so + i * 16:so + i * 16 + 16])]
    assert used == [MAXDIST_SLOT], used
    cnt, step, lo, hi = struct.unpack_from("<I3f", buf, so + MAXDIST_SLOT * 16)
    assert cnt == batches
    po, npb = [x for x in d[11] if x[1] == nb * 16][0]
    pos = np.frombuffer(buf, "<f4", nb * 4, po).reshape(-1, 4)
    b = np.frombuffer(buf, np.uint8, nb, bo)
    return dict(n=n, pos=pos[:, :3].astype(np.float64), pinned=pos[:, 3] < 0, dist=lo + b.astype(np.float64) * step,
                byte_off=bo, slot_off=so + MAXDIST_SLOT * 16, pos_off=po, batches=batches, step=step, lo=lo, hi=hi)


def settings_blocks(buf, cs):
    """Payload offsets of the packed settings structs (id 5, 149 bytes) of one section."""
    return [po for po, n in typed(buf, cs).get(5, []) if n == 149]


LIMIT_OFF = 26      # float in the packed settings struct: limit radius (= max of the max-distance table)


def set_max_distance(buf, t, dist):
    """Write a new per-particle max distance (metres, first t['n'] particles) into a bytearray, in place.
    Requantised to 0..hi over 255 steps; pinned particles (0) stay exactly 0; padding entries stay 255."""
    n = t["n"]; dist = np.asarray(dist, np.float64)[:n]
    assert (dist >= 0).all()
    hi = float(dist.max()); step = hi / 255.0
    q = np.clip(np.rint(dist / step), 0, 255).astype(np.uint8)
    buf[t["byte_off"]:t["byte_off"] + n] = q.tobytes()
    struct.pack_into("<I3f", buf, t["slot_off"], t["batches"], step, 0.0, hi)
    return q


if __name__ == "__main__":
    buf = open(sys.argv[1], "rb").read()
    print("size", len(buf), "header u32s:", struct.unpack_from("<6I", buf, 0))
    for name, off, cs in sections(buf):
        tot = sum(c[3] for c in cs)
        print(f"\n== {name} @ {off}: {len(cs)} chunks, {tot} bytes")
        for (o, cid, typ, size, po) in cs[:60]:
            n = size - 8
            hint = ""
            if n >= 4 and n % 4 == 0 and n <= 64:
                f = struct.unpack_from(f"<{n // 4}f", buf, po); u = struct.unpack_from(f"<{n // 4}I", buf, po)
                hint = " f=" + ",".join(f"{x:.4g}" for x in f[:8]) + " u=" + ",".join(str(x) for x in u[:8])
            elif n <= 16:
                hint = " hex=" + buf[po:po + n].hex()
            else:
                hint = " head=" + buf[po:po + 16].hex()
            print(f"   @{o:6d} id={cid:3d} type={typ:#04x} payload={n:6d}{hint}")
        if len(cs) > 60: print(f"   ... {len(cs) - 60} more")
