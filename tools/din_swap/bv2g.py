#!/usr/bin/env python3
"""
bv2g.py - reader for Snowdrop BV2 graph objects (.mgraphobject), enough to list nodes and wiring.

Layout: magic ff 42 56 32, header (string-length table), string table, body, trailing kind table.
The body is a sequence of ENTRIES numbered from 3 (#0 = null, #1 = true, #2 = false are implicit);
the trailing table holds one kind byte per entry:
    0x30  connection: 4 plain ints  [src node][src pin][dst node][dst pin]
    0x38 / 0x40  3 numbers (float3)     0x50  2 numbers (float2)     0x58  4 tokens (guid)
    0x00  generic table: [n_array][n_keys][array elements][keys][values]   (a record is n_array = 0)
Plain ints (counts, connections, number arrays): 1 byte n<<2, 2 bytes (n<<2)|1 (signed 14 bit),
4 bytes (n<<2)|2. Typed tokens (table elements, keys, values): low 2 bits = size (0:1, 1:2, 2:4,
3:5 bytes = 03 + float32/uint32), next 2 bits = type (0 int, 2 string [payload>>1 = index, low bit =
"is a path"], 3 reference to entry #payload), payload = the remaining bits.
"""
import struct, sys

SIZES = {0: 1, 1: 2, 2: 4, 3: 5}
FIXED = {0x30: 4, 0x38: 3, 0x40: 3, 0x50: 2, 0x58: 4}


def number(x):
    """A scalar number stored as a typed 5-byte token is NOT an IEEE float: it is
    [sign 1][exponent 6, bias 31][mantissa 25]  ->  (-1)^s * 2^(e - 31) * (1 + m / 2^25).
    (Checked against 25 mesh bounding radii; capsule radii, cylinder radii etc. come out as round
    numbers.) tok() returns the raw 32 bits read as float32 or as int; this converts either."""
    if isinstance(x, float): u = struct.unpack("<I", struct.pack("<f", x))[0]
    elif isinstance(x, int) and x > 1 << 20: u = x
    else: return x
    return (-1.0 if u >> 31 else 1.0) * 2.0 ** (((u >> 25) & 63) - 31) * (1 + (u & 0x1ffffff) / 2 ** 25)


class Ref(int):
    def __repr__(self): return f"#{int(self)}"


class Graph:
    def __init__(self, path):
        self.path = path; b = self.b = open(path, "rb").read()
        assert b[:4] == b"\xffBV2"
        start = b.find(b"connectionsById\x00")
        assert start > 0, "not a graph object"
        S = []; j = start
        while True:
            k = b.find(b"\x00", j); c = b[j:k]
            if k < 0 or not all(32 <= x < 127 for x in c) or (not c and b[k + 1:k + 2] and not (32 <= b[k + 1] < 127)): break
            S.append(c.decode()); j = k + 1
        self.strings = S; self.str_off = start; self.body = j
        self._find_table()
        root = self.entries[-1][2]
        assert isinstance(root, dict) and "nodesById" in root, root
        self.root = root
        self.nodes = {}                       # id -> (entry index, record dict)
        nb = self.entry(root["nodesById"])
        for i, v in enumerate(nb["#array"]):
            if isinstance(v, Ref) and int(v) >= 3: self.nodes[i] = (int(v), self.entry(v))
        for k, v in nb.items():
            if isinstance(k, int): self.nodes[k] = (int(v), self.entry(v))
        self.connections = []                 # (entry index, offset, src, srcpin, dst, dstpin) of the top-level graph
        for r in self.entry(root["connectionsById"])["#array"]:
            off, kind, val = self.entries[int(r) - 3]
            self.connections.append((int(r), off) + tuple(val))

    # ---- tokens
    def pint(self, i):
        b = self.b; c = b[i]; k = c & 3
        if k == 0: return c >> 2, 1
        if k == 1:
            v = (b[i] | (b[i + 1] << 8)) >> 2
            return (v - 16384 if v >= 8192 else v), 2
        if k == 2: return struct.unpack_from("<I", b, i)[0] >> 2, 4
        raise ValueError
    def num(self, i):
        if self.b[i] & 3 == 3:
            return struct.unpack_from("<f", self.b, i + 1)[0], 5
        return self.pint(i)
    def raw(self, i):
        """any token, undecoded (guids and other opaque fixed arrays)"""
        n = SIZES[self.b[i] & 3]
        if n == 5: return struct.unpack_from("<I", self.b, i + 1)[0], 5
        return int.from_bytes(self.b[i:i + n], "little") >> 2, n
    def tok(self, i):
        b = self.b; c = b[i]; k = c & 3
        if k == 3:
            if c != 3: raise ValueError
            u = struct.unpack_from("<I", b, i + 1)[0]; f = struct.unpack_from("<f", b, i + 1)[0]
            return (f if (f == 0 or 1e-9 < abs(f) < 1e7) else u), 5
        n = SIZES[k]; v = int.from_bytes(b[i:i + n], "little"); ty = (v >> 2) & 3; p = v >> 4
        if ty == 0:
            bits = n * 8 - 4
            return (p - (1 << bits) if (n == 2 and p >= 1 << (bits - 1)) else p), n
        if ty == 2:
            if (p >> 1) >= len(self.strings): raise ValueError
            return self.strings[p >> 1], n
        if ty == 3: return (None if p == 0 else True if p == 1 else False if p == 2 else Ref(p)), n
        return ("?t1", p), n

    # ---- entries
    def _parse(self, table, stop):
        i = self.body; out = []
        for kind in table:
            off = i
            if kind in FIXED:
                vals = []
                for _ in range(FIXED[kind]):
                    v, l = (self.pint(i) if kind == 0x30 else self.num(i) if kind in (0x38, 0x40, 0x50) else self.raw(i)); vals.append(v); i += l
                out.append((off, kind, vals))
            elif kind == 0:
                na, l = self.pint(i); i += l
                nk, l = self.pint(i); i += l
                if na > 5000 or nk > 5000 or na < 0 or nk < 0: raise ValueError
                arr = []
                for _ in range(na):
                    v, l = self.tok(i); arr.append(v); i += l
                keys = []
                for _ in range(nk):
                    v, l = self.tok(i); keys.append(v); i += l
                d = {}
                for k in keys:
                    v, l = self.tok(i); d[k] = v; i += l
                if na or not nk: d["#array"] = arr
                out.append((off, kind, d))
            else:
                raise ValueError(f"unknown kind {kind:#x}")
            if i > stop: raise ValueError
        if i != stop: raise ValueError
        return out
    def _find_table(self):
        """header = plain ints [?][n strings][n entries][...]; the kind table is the last n-entries bytes.
        Token counts of kinds not in FIXED are found by trial (the whole body must parse exactly)."""
        b = self.b; i = 4; hdr = []
        for _ in range(3):
            v, l = self.pint(i); hdr.append(v); i += l
        assert hdr[1] == len(self.strings), (hdr, len(self.strings))
        nent = hdr[2]; t = len(b) - nent; table = b[t:]; self.table_off = t
        unknown = sorted(set(table) - set(FIXED) - {0})
        def attempt(k, counts):
            if k == len(unknown):
                FIXED.update(counts)
                try: return self._parse(table, t)
                except (ValueError, IndexError, struct.error): return None
                finally:
                    for u in counts: FIXED.pop(u, None)
            for n in range(1, 21):
                r = attempt(k + 1, {**counts, unknown[k]: n})
                if r is not None:
                    self.kinds = {**FIXED, **counts, unknown[k]: n}; return r
            return None
        self.kinds = dict(FIXED)
        r = attempt(0, {})
        if r is None: raise ValueError(f"could not parse the body (unknown kinds {[hex(u) for u in unknown]})")
        self.entries = r

    def entry(self, ref):
        return self.entries[int(ref) - 3][2]

    # ---- views
    def node_type(self, nid):
        return self.nodes[nid][1].get("type", "?") if nid in self.nodes else "?"
    def inputs(self, nid):
        return sorted((dp, s, sp, e, off) for e, off, s, sp, d, dp in self.connections if d == nid)
    def outputs(self, nid):
        return sorted((sp, d, dp, e, off) for e, off, s, sp, d, dp in self.connections if s == nid)
    def show(self, v, depth=0):
        if isinstance(v, Ref) and depth < 2:
            e = self.entries[int(v) - 3]
            if e[1] in FIXED: return "(" + ", ".join(f"{x:.5g}" if isinstance(x, float) else str(x) for x in e[2]) + ")"
            if isinstance(e[2], dict) and set(e[2]) == {"#array"} and len(e[2]["#array"]) <= 6: return "[" + ", ".join(self.show(x, depth + 1) for x in e[2]["#array"]) + "]"
        if isinstance(v, float): return f"{v:.6g}"
        return repr(v)
    def describe(self, nid, brief=False):
        e, d = self.nodes[nid]
        props = "  ".join(f"{k}={self.show(v)}" for k, v in d.items() if k not in ("type", "#array"))
        return f"{nid} {d.get('type', '?')}  {props}"[: (150 if brief else 400)]


if __name__ == "__main__":
    g = Graph(sys.argv[1]); want = sys.argv[2:]
    print(f"{len(g.b)} B, {len(g.strings)} strings, {len(g.entries)} entries, {len(g.nodes)} nodes, {len(g.connections)} connections; root {g.root}")
    for nid in sorted(g.nodes):
        ty = g.node_type(nid)
        if want and not any(w in ty for w in want): continue
        print(g.describe(nid))
        for dp, s, sp, e, off in g.inputs(nid):
            print(f"      pin {dp:<6} <- {s}.{sp}  ({g.describe(s, brief=True)[:110]})")
