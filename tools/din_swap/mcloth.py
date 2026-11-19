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
          slot 2 = the particle's COLLISION RADIUS in metres (cloth thickness against the collision
          capsules). Canto police cape 0 .. 3.9 cm (sim-mesh red / 255 * 0.4), Boba poncho 0 .. 5 cm,
          Vader 2 .. 7.4 cm, Lando 1 .. 5 cm - all free-flowing capes, so this is NOT a leash (it was
          first read as "max distance"; max_distance() below still carries that name). Raising it
          to 40 cm made the lower cape keep 40 cm away from the body. Padding entries are 255.
  ids 12 / 13 / 14   constraint tables: id 12 = six batch counts, id 14 = six (step, lo, hi), id 13 = bytes
          range 0-2 per-edge spring rest lengths
          range 3   BACKSTOP: how far (negative metres) a particle may go inside its animated pose
                    (Canto 0 .. -17 cm, Lando 0 .. -23 cm, Vader 0 .. -36 cm; the poncho has none)
          range 4   max distance from the animated pose (only Lando: 0 .. 26 cm)
          range 5   tether length
The same tables are repeated, identical, in every sim LOD section.

Simulation settings ("states"; the solver is Ubisoft's SMotion — step names in the exe: InjectAnim,
ApplyDampingAndInertia, ApplyMaxLengthConstraints, ApplyBlendConstraints, Springs, ApplyLimitConstraints,
ApplyCollisionConstraints, BlendInAnimation). A section holds one default settings block plus one per
state (id 82 = state count: Canto 1, Lando seated 3 — picked by the gear graph's ClothPreset/presetId).
A block = id 5 (149 B packed struct) followed by the same values as separate chunks (46 gravity,
7 flags, 8 five floats, 45, 47-49, 44, 26, 43, 78):
  id 5 +0   u8 mode: 2 Canto / Lando, 1 Boba poncho / Vader, 0 in the two special states of Lando's seated cape
       +2   float3 gravity
       +14  float  (authored: Canto 0.1, Lando 0 / 0.03 — damping?)
       +26  float  maximum of the slot-2 table = largest collision radius (Canto 0.0392, poncho / Lando
                   0.05, Vader 0.074). A table value above it has no effect.
       +125 float  0.7 and +133 float 0.1 on the Canto cape only, 0 in every other cape (friction?)
       +1, +94, +99 = 1, chunk 43 byte 0 = 1, chunk 45 byte 0 = 1 in every normal cape (body collision
                   and body-relative frame); all 0 in the special states of Lando's seated cape, where
                   the cloth ignores the body (seen in game)
       +35  float  1.05 Canto / 1.19-2.0 Lando (max-length stretch?)   +95 float time step (1/30, 1/60)
The states of Lando's seated cape additionally carry a per-state table id 84/86/89 (0..0.40 m).
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
    """Per-particle slot-2 table of one sim section (the COLLISION RADIUS - historically misnamed, see above).
    -> dict(n, pos (N,3), dist (N,) metres, byte_off, slot_off, batches, step, lo, hi)"""
    d = typed(buf, cs)
    n = struct.unpack_from("<I", buf, d[2][0][0])[0]
    batches, nslots = struct.unpack_from("<2I", buf, d[178][0][0])
    bo, nb = d[179][0]; so, ns = d[180][0]
    assert ns == nslots * 16 and nb == batches * 16, "expected exactly one stored channel (collision radius)"
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


LIMIT_OFF = 26      # float in the packed settings struct: the largest collision radius (max of the slot-2 table)


BACKSTOP_RANGE = 3  # index of the per-particle inward-limit channel in the constraint tables (ids 12/13/14)


def particle_channel(buf, cs, r=BACKSTOP_RANGE):
    """One quantised channel of a sim section's constraint tables.

    id 12 = six batch counts (x16 entries each), id 14 = six (step, lo, hi) float triples, id 13 = the
    bytes of all six ranges back to back; value = lo + byte * step. Ranges 0-2 are per-edge spring rest
    lengths, range 3 is per particle (-17 cm ... +0.6 cm on the Canto cape, about 0 at the pinned top and
    most negative at the hem: the inward limit / backstop offset along the skinned normal), range 5 is
    the per-particle tether length.
    -> dict(off = absolute offset of the channel's bytes, count = entries incl. padding, step, lo, hi)"""
    d = typed(buf, cs)
    counts = struct.unpack_from("<6I", buf, d[12][0][0])
    assert d[14][0][1] == 72, d[14][0][1]
    step, lo, hi = struct.unpack_from("<3f", buf, d[14][0][0] + r * 12)
    po, size = d[13][0]
    off = po + 16 * sum(counts[:r]); n = 16 * counts[r]
    assert off + n <= po + size
    return dict(off=off, count=n, step=step, lo=lo, hi=hi)


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
