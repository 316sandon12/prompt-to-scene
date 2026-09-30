"""A reproducible Blender recipe. AI clients can author any script obeying the asset contract."""

import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
collection = bpy.data.collections.new("Export")
bpy.context.scene.collection.children.link(collection)


def material(name, color, metallic, roughness):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    bsdf = result.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return result


wood = material("Wood", (0.24, 0.085, 0.025), 0, 0.72)
iron = material("Iron", (0.08, 0.09, 0.11), 0.85, 0.3)


def box(name, center, size, surface):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    collection.objects.link(obj)
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(surface)
    bevel = obj.modifiers.new("Soft edges", "BEVEL")
    bevel.width = 0.008
    bevel.segments = 2
    bpy.ops.object.modifier_apply(modifier=bevel.name)


# Grounded origin, one-meter cube, visible planks and dark metal straps.
for i in range(5):
    box("Plank_" + str(i), (-0.4 + i * 0.2, 0, 0.5), (0.192, 0.96, 0.96), wood)
for x in (-0.36, 0.36):
    for y in (-0.49, 0.49):
        box("BandSide", (x, y, 0.5), (0.075, 0.025, 1.0), iron)
    for z in (0.0125, 0.9875):
        box("BandTop", (x, 0, z), (0.075, 0.98, 0.025), iron)
