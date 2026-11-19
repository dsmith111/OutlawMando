import bpy, sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as C
from mathutils import Vector
spec = json.load(open(sys.argv[sys.argv.index("--") + 1]))
C.reset_scene()
objs = []
for it in spec["items"]:
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=it["obj"], forward_axis='Y', up_axis='Z')
    new = [o for o in bpy.data.objects if o not in before]
    mat = bpy.data.materials.new(os.path.basename(it["obj"]))
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    col = it.get("color", [0.8, 0.8, 0.8])
    bsdf.inputs["Base Color"].default_value = (col[0], col[1], col[2], 1)
    bsdf.inputs["Roughness"].default_value = it.get("roughness", 0.6)
    bsdf.inputs["Metallic"].default_value = it.get("metallic", 0.0)
    if it.get("texture"):
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(it["texture"])
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if it.get("normal"):
        nt = mat.node_tree.nodes.new("ShaderNodeTexImage"); nt.image = bpy.data.images.load(it["normal"]); nt.image.colorspace_settings.name = 'Non-Color'
        nm = mat.node_tree.nodes.new("ShaderNodeNormalMap")
        mat.node_tree.links.new(nt.outputs["Color"], nm.inputs["Color"]); mat.node_tree.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    a = it.get("alpha", 1.0)
    if a < 1.0:
        bsdf.inputs["Alpha"].default_value = a
        try: mat.surface_render_method = 'BLENDED'
        except Exception: pass
    for o in new:
        o.data.materials.clear(); o.data.materials.append(mat)
        if it.get("smooth", True):
            for p in o.data.polygons: p.use_smooth = True
        if it.get("wire"):
            m = o.modifiers.new("w", "WIREFRAME"); m.thickness = 0.0015
        objs.append(o)
C.setup_render(res=tuple(spec.get("res", (800, 1100))))
C.add_sun((55, 0, 25), 3.0); C.add_sun((60, 0, 200), 1.5, "Sun2"); C.add_sun((120, 0, 100), 0.8, "Sun3")
frame = objs
if spec.get("crop"):
    mn, mx = spec["crop"]
    me = bpy.data.meshes.new("crop"); me.from_pydata([mn, mx], [], []); o = bpy.data.objects.new("crop", me)
    bpy.context.scene.collection.objects.link(o); o.hide_render = True; frame = [o]
outs = C.render_views(spec["out"], frame, views=tuple(spec["views"]), res=tuple(spec.get("res", (800, 1100))))
print("RENDERED", outs)
