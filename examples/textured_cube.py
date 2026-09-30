"""Self-contained UV, base-color and normal-map fixture; no downloaded assets."""

import bpy

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
collection = bpy.data.collections.new("Export")
bpy.context.scene.collection.children.link(collection)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
cube = bpy.context.object
for old_collection in list(cube.users_collection):
    old_collection.objects.unlink(cube)
collection.objects.link(cube)

material = bpy.data.materials.new("Paint")
material.use_nodes = True
cube.data.materials.append(material)
nodes = material.node_tree.nodes
links = material.node_tree.links
shader = nodes.get("Principled BSDF")
shader.inputs["Metallic"].default_value = 0.2
shader.inputs["Roughness"].default_value = 0.65

albedo = bpy.data.images.new("Checker", width=8, height=8, alpha=False)
albedo.colorspace_settings.name = "sRGB"
pixels = []
for y in range(8):
    for x in range(8):
        pixels.extend((0.8, 0.12, 0.04, 1) if (x // 2 + y // 2) % 2 else (0.9, 0.9, 0.9, 1))
albedo.pixels[:] = pixels
base = nodes.new("ShaderNodeTexImage")
base.image = albedo
links.new(base.outputs["Color"], shader.inputs["Base Color"])

normal_image = bpy.data.images.new("Flat normal", width=8, height=8, alpha=False)
normal_image.colorspace_settings.name = "Non-Color"
normal_image.pixels[:] = [0.5, 0.5, 1, 1] * 64
normal_texture = nodes.new("ShaderNodeTexImage")
normal_texture.image = normal_image
normal = nodes.new("ShaderNodeNormalMap")
normal.inputs["Strength"].default_value = 0.75
links.new(normal_texture.outputs["Color"], normal.inputs["Color"])
links.new(normal.outputs["Normal"], shader.inputs["Normal"])
