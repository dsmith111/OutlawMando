#!/usr/bin/env python3
"""Pose sanity test for the STAGED full-body build: forward-kinematics on the game's bind skeleton
(elbows / knees bent, spine twisted, head pitched), every staged submesh skinned with ITS OWN bone
table and weights exactly as written to the .mmb. Catches weight mistakes and seams between the
separate mesh files that bind-pose renders cannot show. The game drives the RFX helper bones at
runtime; here they simply follow the limb segment they sit on."""
import os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mmbio, preview
from preview_build import staged_meshes, staged_items, W


def rot(axis, deg, pivot):
    a = np.radians(deg); axis = np.asarray(axis, float) / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K
    M = np.eye(4); M[:3, :3] = R; M[:3, 3] = pivot - R @ pivot
    return M


def union_skeleton():
    world, parent = {}, {}
    seen = set()
    for rel, slot, tex, d, a in staged_meshes():
        if rel in seen: continue
        seen.add(rel)
        names, parents, local, w = mmbio.bone_tables(a)
        for i, n in enumerate(names):
            world.setdefault(n, w[i]); parent.setdefault(n, names[parents[i]] if parents[i] >= 0 else None)
    for n in list(parent):                       # the arm helper subtree hangs off the clavicle in the file;
        for S in ("Left", "Right"):              # at runtime it follows the upper arm
            if n == f"RFX_D_{S}_Shoulder": parent[n] = f"{S}Arm"
    return world, parent


POSES = {
    # standing stance with the spine curved the way a relaxed idle does (each spine joint a little
    # different) plus dropped shoulders: the case where chest accessories separate from the plates
    "stance": {"Spine": ([1, 0, 0], 4), "Spine1": ([1, 0, 0], -6), "Spine2": ([1, 0, 0], -8), "Spine3": ([1, 0, 0], 12),
               "LeftShoulder": ([0, 0, 1], 12), "RightShoulder": ([0, 0, 1], -12),
               "LeftArm": ([0, 0, 1], 30), "RightArm": ([0, 0, 1], -30),
               "LeftForeArm": ([1, 0, 0], -15), "RightForeArm": ([1, 0, 0], -15)},
    # roughly the game's idle stance: clavicles dropped, arms hanging, forearms slightly bent
    "idle": {"LeftShoulder": ([0, 0, 1], 12), "RightShoulder": ([0, 0, 1], -12),
             "LeftArm": ([0, 0, 1], 30), "RightArm": ([0, 0, 1], -30),
             "LeftForeArm": ([1, 0, 0], -15), "RightForeArm": ([1, 0, 0], -15), "Neck1": ([1, 0, 0], 6)},
    "action": {"Spine1": ([0, 1, 0], 14), "Neck1": ([1, 0, 0], 12), "Head": ([1, 0, 0], 12),
               "LeftArm": ([0, 0, 1], -35), "LeftForeArm": ([1, 0, 0], -75), "LeftHand": ([0, 0, 1], 20),
               "RightArm": ([1, 0, 0], -40), "RightForeArm": ([1, 0, 0], -55),
               "LeftUpLeg": ([1, 0, 0], -55), "LeftLeg": ([1, 0, 0], 75), "LeftFoot": ([1, 0, 0], -15),
               "RightUpLeg": ([1, 0, 0], 18), "RightLeg": ([1, 0, 0], 20),
               "LeftHandIndex1": ([0, 0, 1], 30), "LeftHandMiddle1": ([0, 0, 1], 30), "RightHandIndex1": ([0, 0, 1], -40)},
}


def pose_deltas(world, parent, pose):
    """World-space delta matrix per bone (identity = bind pose), local rotations given in WORLD axes at the joint."""
    D = {}

    def get(n):
        if n in D: return D[n]
        p = parent.get(n)
        Dp = get(p) if p else np.eye(4)
        if n in pose:
            axis, deg = pose[n]
            piv = world[n][:3, 3]
            D[n] = Dp @ rot(axis, deg, piv)
        else:
            D[n] = Dp
        return D[n]
    for n in world: get(n)
    return D


def run(name="action"):
    world, parent = union_skeleton()
    D = pose_deltas(world, parent, POSES[name])
    stats = []

    def posed(rel, slot, d, a):
        names = [b.name for b in a.bones]
        M = np.stack([D[n] for n in names])
        ph = np.concatenate([d.pos, np.ones((len(d.pos), 1))], 1)
        out = np.zeros_like(d.pos)
        for s in range(d.bw.shape[1]):
            out += d.bw[:, s:s + 1] * np.einsum("nij,nj->ni", M[d.bi[:, s]], ph)[:, :3]
        e0 = np.linalg.norm(d.pos[d.tris[:, 0]] - d.pos[d.tris[:, 1]], axis=1); e1 = np.linalg.norm(out[d.tris[:, 0]] - out[d.tris[:, 1]], axis=1)
        r = e1 / np.maximum(e0, 1e-9)
        stats.append((os.path.basename(rel)[:-4].replace("chr_", ""), slot, float(np.percentile(r, 1)), float(np.median(r)), float(np.percentile(r, 99)), float(r.max())))
        return out
    items = staged_items(tag="pose", posed=posed)
    for s in stats:
        print(f"  {s[0][-28:]:28s} {s[1]:14s} edge stretch p1 {s[2]:.2f}  median {s[3]:.2f}  p99 {s[4]:.2f}  max {s[5]:.2f}")
    if name in ("idle", "stance"):
        print(preview.render(W, f"p2_pose_{name}", items, views=("front", "q", "back"), res=(900, 900), crop=[[-0.45, 0.95, -0.35], [0.45, 1.80, 0.35]]))
    else:
        print(preview.render(W, f"p2_pose_{name}", items, views=("front", "side", "q", "back"), res=(820, 1080), crop=[[-0.8, -0.05, -0.6], [0.8, 1.85, 0.6]]))


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "action")
