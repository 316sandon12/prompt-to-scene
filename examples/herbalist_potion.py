"""Blender source for a reusable stylized glazed potion; named parts remain editable."""

import math

import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
export = bpy.data.collections.new("Export")
bpy.context.scene.collection.children.link(export)


def material(name, color, roughness=0.35, metallic=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Metallic"].default_value = metallic
    return m


jade = material("Forest glaze", (0.035, 0.24, 0.12), 0.23)
gold = material("Warm brass", (0.55, 0.3, 0.07), 0.3, 0.65)
cork = material("Soft cork", (0.22, 0.10, 0.042), 0.78)
cream = material("Ivory seal", (0.74, 0.61, 0.33), 0.62)


def finish(obj, part, mat, bevel=0.008):
    obj.name = part
    obj["pts_part"] = part
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    export.objects.link(obj)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Rounded craft edges", "BEVEL")
        mod.width, mod.segments = bevel, 3
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


profile = [
    (0, 0.13),
    (0.025, 0.165),
    (0.075, 0.18),
    (0.27, 0.18),
    (0.35, 0.155),
    (0.405, 0.078),
    (0.46, 0.073),
    (0.48, 0.076),
]
vertices = [
    (r * math.cos(i * math.tau / 48), r * math.sin(i * math.tau / 48), z)
    for z, r in profile
    for i in range(48)
]
faces = [
    (j * 48 + i, j * 48 + (i + 1) % 48, (j + 1) * 48 + (i + 1) % 48, (j + 1) * 48 + i)
    for j in range(len(profile) - 1)
    for i in range(48)
]
faces += [tuple(reversed(range(48))), tuple((len(profile) - 1) * 48 + i for i in range(48))]
mesh = bpy.data.meshes.new("Lathed bottle")
mesh.from_pydata(vertices, [], faces)
mesh.update()
body = bpy.data.objects.new("body", mesh)
bpy.context.collection.objects.link(body)
finish(body, "body", jade)
for z, radius in ((0.035, 0.171), (0.29, 0.182), (0.455, 0.076)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=radius,
        minor_radius=0.009,
        major_segments=48,
        minor_segments=10,
        location=(0, 0, z),
    )
    finish(bpy.context.object, "brass_bands", gold, 0)
bpy.ops.mesh.primitive_cone_add(
    vertices=32, radius1=0.062, radius2=0.073, depth=0.083, location=(0, 0, 0.503)
)
finish(bpy.context.object, "cork", cork, 0.006)
bpy.ops.mesh.primitive_uv_sphere_add(
    segments=24, ring_count=12, radius=1, location=(0, -0.181, 0.19)
)
seal = bpy.context.object
seal.scale = (0.07, 0.012, 0.092)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
finish(seal, "seal", cream, 0.002)
bpy.ops.mesh.primitive_uv_sphere_add(
    segments=20, ring_count=10, radius=1, location=(0, -0.196, 0.192)
)
leaf = bpy.context.object
leaf.scale = (0.022, 0.006, 0.048)
leaf.rotation_euler[1] = 0.4
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
finish(leaf, "emblem", jade, 0)

# Publish static meshes: the retained source already contains the finished bevel geometry.
bpy.ops.object.select_all(action="DESELECT")
for obj in export.objects:
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.select_set(False)
