#!/usr/bin/env python3
"""
build_graphs.py — gear-graph fixes for the Din outfit (staging tree only; same-length byte edits).

Two problems come from wearing Boba's NPC gear graphs on Kay's character graph with Kay's own gear
graphs blanked by the base mods:

1. FIRST PERSON. Kay's character graph (chr_body_2_gold_kay) sets gear input 151 to
   NOT(IsInFirstPersonMode); her own gear feeds that into each mesh node's visibility pin, so the
   gear disappears when the camera moves inside her (vents, lockpicking). Boba's gear meshes
   (HC_GearPrefabNode_MeshSkinned) have their two always-true inputs (pins 1002 and 1003, one of
   which is visibility) fed by constants, so they stay drawn around the camera.
   Fix: re-point both at GearInputs_Inside (node 2) pin 151. A connection is four plain ints
   [src node][src pin][dst node][dst pin]; "constant N, pin 0" is 2 + 1 bytes and "node 2, pin 151"
   is 1 + 2 bytes, so the file length does not change.

2. GRAPPLE ROPE. The joints the rope hangs from (rope_attachment_joint, Grappling_hook, Holster, ...)
   belong to Kay's accessories gear graph chr_acc_1_gold_kay_001, which "Hide Kay's Clothes" replaces
   with an empty file. Fix: ship that graph again with its three meshes (holster, wire pouch, coiled
   rope) switched off: each mesh's visibility pin is re-pointed from its logic node to a constant
   False node of the same graph (2-byte node id -> 2-byte node id).

3. CAPE "FOLLOW". The Canto police cape's cloth node has its follow input (pin 7) at 0.2; every
   free-flowing cape in the game (Lando, Vader, Boba's poncho) has 0 there. Fix: re-point pin 7 from
   its constant to a `Constant 0.0` node of the same graph. The 0.2 constant record itself is shared
   with a collision capsule's radius, so the record is left alone. This graph sits on the Canto
   cape's own path, so Canto Bight police get the same change (follow 0); it is deliberately NOT
   given the first-person edit, which could hide the cape on NPCs whose character graph leaves gear
   input 151 undriven.

Inputs: vanilla graphs exported with Hunter, in local/din_swap/containers/graphs/ (the cape's in
containers/cape/).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
import bv2g  # noqa: E402

SRC = os.path.join(ROOT, "local/din_swap/containers/graphs")
STAGE = os.environ.get("DIN_GRAPH_STAGE") or os.path.join(ROOT, "local/din_swap/staging")
REL = "helix/graph objects/gear"
WORN = ["chr_headw_5_canon_boba_fett_helmet", "chr_top_5_canon_boba_fett_shirt", "chr_top_5_canon_boba_fett_belt",
        "chr_botm_5_canon_boba_fett_pants", "chr_acc_5_canon_boba_fett_gloves", "chr_top_5_canon_boba_fett_vest",
        "chr_acc_5_canon_boba_fett_bracers", "chr_acc_5_canon_boba_fett_pouches", "chr_acc_5_canon_boba_fett_kneepads",
        "chr_botm_5_canon_boba_fett_boots"]
ACCESSORIES = "chr_acc_1_gold_kay_001"
CAPE = "chr_acc_2_silver_canto_police_cape"
CAPE_SRC = os.path.join(ROOT, "local/din_swap/containers/cape")
CLOTH_FOLLOW_PIN = 7
GEAR_INPUTS, VISIBLE_PIN = 2, 151
HC_BOOL_PINS = (1002, 1003)


def enc(n):
    """plain int: 1 byte n<<2 (0..63), else 2 bytes (n<<2)|1"""
    if 0 <= n < 64: return bytes([n << 2])
    assert -8192 <= n < 8192, n
    return ((n & 0x3fff) << 2 | 1).to_bytes(2, "little")


def is_const(g, n, value):
    d = g.nodes[n][1]
    return d.get("type") == "native:Constant" and d.get("valueType") == "bool" and d.get("value") is value


def repoint(buf, conn, new_src, new_pin):
    """rewrite the source half of one connection entry in place"""
    e, off, s, sp, d, dp = conn
    old = enc(s) + enc(sp); new = enc(new_src) + enc(new_pin)
    assert bytes(buf[off:off + len(old)]) == old, (bytes(buf[off:off + len(old)]).hex(), old.hex())
    assert len(new) == len(old), f"connection {s}.{sp} -> {d}.{dp}: {len(old)} bytes cannot hold node {new_src} pin {new_pin}"
    buf[off:off + len(old)] = new


def first_person(name):
    g = bv2g.Graph(os.path.join(SRC, name + ".mgraphobject")); buf = bytearray(g.b)
    assert g.node_type(GEAR_INPUTS) == "native:GearInputs_Inside", g.node_type(GEAR_INPUTS)
    meshes = [n for n in sorted(g.nodes) if g.node_type(n) == "HC_GearPrefabNode_MeshSkinned"]
    assert meshes, name
    for m in meshes:
        ins = {c[5]: c for c in g.connections if c[4] == m}
        for pin in HC_BOOL_PINS:
            c = ins[pin]
            assert c[3] == 0 and is_const(g, c[2], True), (name, m, pin, g.describe(c[2]))
            repoint(buf, c, GEAR_INPUTS, VISIBLE_PIN)
    return g, bytes(buf), meshes


def accessories(name=ACCESSORIES):
    g = bv2g.Graph(os.path.join(SRC, name + ".mgraphobject")); buf = bytearray(g.b)
    meshes = [n for n in sorted(g.nodes) if g.node_type(n) == "prefab:MeshSkinned"]
    assert [g.nodes[m][1]["MeshName"] for m in meshes] == ["holster_mesh", "wirepouch_mesh", "rope_mesh"], meshes
    false = next(n for n in sorted(g.nodes) if n >= 64 and is_const(g, n, False))
    for m in meshes:
        c = next(c for c in g.connections if c[4] == m and c[5] == 0)
        assert g.node_type(c[2]) == "native:And" and c[3] == 0, g.describe(c[2])
        repoint(buf, c, false, 0)
    return g, bytes(buf), meshes, false


def cape_follow(name=CAPE):
    g = bv2g.Graph(os.path.join(CAPE_SRC, name + ".mgraphobject")); buf = bytearray(g.b)
    cloth = [n for n in g.nodes if g.node_type(n) == "prefab:Cloth"]
    assert len(cloth) == 1, cloth
    c = next(c for c in g.connections if c[4] == cloth[0] and c[5] == CLOTH_FOLLOW_PIN)
    d = g.nodes[c[2]][1]
    assert d.get("type") == "native:Constant" and d.get("valueType") == "float" and c[3] == 0, g.describe(c[2])
    was = bv2g.number(d.get("value"))
    assert abs(was - 0.2) < 1e-6, was
    zero = next(n for n in sorted(g.nodes) if n >= 64 and g.nodes[n][1].get("type") == "native:Constant"
                and g.nodes[n][1].get("valueType") == "float" and g.nodes[n][1].get("value") == 0 and isinstance(g.nodes[n][1].get("value"), int))
    repoint(buf, c, zero, 0)
    return g, bytes(buf), cloth[0], zero, was


def write(name, data, size):
    assert len(data) == size, name
    out = os.path.join(STAGE, REL, name + ".mgraphobject"); os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(data)
    return out


def build():
    rep = []
    for name in WORN:
        g, data, meshes = first_person(name)
        out = write(name, data, len(g.b))
        h = bv2g.Graph(out)                                        # still parses; only the intended connections moved
        assert len(h.nodes) == len(g.nodes) and len(h.connections) == len(g.connections)
        moved = [(a, b) for a, b in zip(g.connections, h.connections) if a != b]
        assert len(moved) == 2 * len(meshes) and all(b[2:4] == (GEAR_INPUTS, VISIBLE_PIN) and a[4:] == b[4:] and b[5] in HC_BOOL_PINS for a, b in moved), moved
        rep.append(f"{name}: {len(meshes)} mesh node(s), {len(moved)} inputs now follow gear pin {VISIBLE_PIN}")
    g, data, meshes, false = accessories()
    out = write(ACCESSORIES, data, len(g.b)); h = bv2g.Graph(out)
    moved = [(a, b) for a, b in zip(g.connections, h.connections) if a != b]
    assert len(moved) == 3 and all(b[2:4] == (false, 0) and a[4:] == b[4:] and b[5] == 0 for a, b in moved), moved
    rep.append(f"{ACCESSORIES}: graph restored; holster, wire pouch and coiled rope meshes switched off (visibility <- constant False, node {false})")
    g, data, cloth, zero, was = cape_follow()
    out = write(CAPE, data, len(g.b)); h = bv2g.Graph(out)
    moved = [(a, b) for a, b in zip(g.connections, h.connections) if a != b]
    assert len(moved) == 1 and moved[0][1][2:4] == (zero, 0) and moved[0][1][4:] == (cloth, CLOTH_FOLLOW_PIN), moved
    rep.append(f"{CAPE}: cloth follow input {was:g} -> 0 (pin {CLOTH_FOLLOW_PIN} <- constant node {zero})")
    return rep


if __name__ == "__main__":
    for line in build(): print("   " + line)
