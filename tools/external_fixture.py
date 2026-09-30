"""Blender fixture: dense, textured static geometry in three external formats."""

import sys
from pathlib import Path

import bpy
import numpy as np

folder = Path(sys.argv[sys.argv.index("--") + 1])
folder.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=64, location=(0, 0, 0.7))
obj = bpy.context.object
obj.name = "CeramicBody"
obj.scale = (0.5, 0.5, 0.7)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for poly in obj.data.polygons:
    poly.use_smooth = True
mat = bpy.data.materials.new("GlazedCeramic")
mat.use_nodes = True
shader = mat.node_tree.nodes.get("Principled BSDF")
image = bpy.data.images.new("CheckerColor", width=64, height=64)
yy, xx = np.indices((64, 64))
mask = ((xx // 8 + yy // 8) % 2).astype(bool)
pixels = np.ones((64, 64, 4), dtype=np.float32)
pixels[mask, :3] = [0.06, 0.42, 0.38]
pixels[~mask, :3] = [0.7, 0.52, 0.26]
image.pixels.foreach_set(pixels.ravel())
image.filepath_raw = str(folder / "fixture_color.png")
image.file_format = "PNG"
image.save()
image.pack()
texture = mat.node_tree.nodes.new("ShaderNodeTexImage")
texture.image = image
mat.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
shader.inputs["Roughness"].default_value = 0.3
obj.data.materials.append(mat)
bpy.ops.mesh.primitive_torus_add(
    major_radius=0.35,
    minor_radius=0.045,
    major_segments=72,
    minor_segments=20,
    location=(0, 0, 1.2),
)
rim = bpy.context.object
rim.name = "MetalRim"
metal = bpy.data.materials.new("WarmBrass")
metal.use_nodes = True
shader = metal.node_tree.nodes.get("Principled BSDF")
shader.inputs["Base Color"].default_value = (0.5, 0.3, 0.06, 1)
shader.inputs["Metallic"].default_value = 0.8
shader.inputs["Roughness"].default_value = 0.25
rim.data.materials.append(metal)
bpy.ops.wm.save_as_mainfile(filepath=str(folder / "fixture.blend"))
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=str(folder / "fixture.glb"), export_format="GLB")
bpy.ops.export_scene.fbx(
    filepath=str(folder / "fixture.fbx"),
    use_selection=True,
    object_types={"MESH"},
    bake_anim=False,
    path_mode="COPY",
    embed_textures=True,
)
print("EXTERNAL_FIXTURE_READY", flush=True)
