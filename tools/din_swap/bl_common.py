"""Shared helpers for headless Blender scripts (rendering previews etc.)."""
import bpy, math, os
from mathutils import Vector, Matrix


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def scene_bounds(objs):
    mn = Vector((1e9, 1e9, 1e9)); mx = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != 'MESH':
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    return mn, mx


def setup_render(res=(900, 1200), engine=None, samples=24):
    sc = bpy.context.scene
    engines = [engine] if engine else ['BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'CYCLES']
    for e in engines:
        try:
            sc.render.engine = e
            break
        except Exception:
            continue
    if sc.render.engine == 'CYCLES':
        sc.cycles.samples = samples
        sc.cycles.use_denoising = False
        sc.cycles.device = 'CPU'
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'Standard'
    if sc.world is None:
        sc.world = bpy.data.worlds.new("W")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.35, 0.37, 0.40, 1)
        bg.inputs[1].default_value = 1.0
    return sc


def add_sun(rot=(50, 0, 30), energy=3.0, name="Sun"):
    d = bpy.data.lights.new(name, 'SUN'); d.energy = energy
    o = bpy.data.objects.new(name, d); bpy.context.scene.collection.objects.link(o)
    o.rotation_euler = [math.radians(a) for a in rot]
    return o


def ortho_cam(center, size, direction, name="Cam", up_axis='Z'):
    """direction: unit vector FROM camera TO target."""
    cd = bpy.data.cameras.new(name); cd.type = 'ORTHO'; cd.ortho_scale = size
    cd.clip_start = 0.01; cd.clip_end = 1000
    o = bpy.data.objects.new(name, cd); bpy.context.scene.collection.objects.link(o)
    d = Vector(direction).normalized()
    o.location = Vector(center) - d * 50
    up = 'Y'
    o.rotation_euler = d.to_track_quat('-Z', up).to_euler()
    return o


def render_views(out_prefix, objs, views=("front", "side", "back"), res=(900, 1200), pad=1.08, up='Z', front=(0, 1, 0)):
    """Render orthographic views of objs. `front` = direction camera looks for the front view."""
    sc = bpy.context.scene
    mn, mx = scene_bounds(objs)
    center = (mn + mx) / 2
    ext = mx - mn
    f = Vector(front).normalized()
    upv = Vector((0, 0, 1)) if up == 'Z' else Vector((0, 1, 0))
    right = f.cross(upv).normalized()
    dirs = {
        "front": f, "back": -f, "side": -right, "side2": right,
        "q": (f + right * 0.8 - upv * 0.25).normalized(),
        "qb": (-f - right * 0.8 - upv * 0.25).normalized(),
        "top": -upv,
    }
    height = abs(ext.dot(upv)); width = max(abs(ext.dot(right)), abs(ext.dot(f)))
    size = max(height, width * res[1] / res[0]) * pad
    outs = []
    for v in views:
        cam = ortho_cam(center, size, dirs[v], name="Cam_" + v)
        if v == "top":
            cam.rotation_euler = dirs[v].to_track_quat('-Z', 'Y').to_euler()
        sc.camera = cam
        sc.render.filepath = f"{out_prefix}_{v}.png"
        bpy.ops.render.render(write_still=True)
        outs.append(sc.render.filepath)
    return outs
