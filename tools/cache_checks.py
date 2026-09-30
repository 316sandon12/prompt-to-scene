"""Run inside real Blender: dependency changes must invalidate baked maps."""

import json
import runpy
import tempfile
from pathlib import Path

import bpy

repo = Path(__file__).resolve().parents[1]
cache = runpy.run_path(str(repo / "src/prompt_to_scene/blender_cache.py"))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add()
obj = bpy.context.object
mat = bpy.data.materials.new("Cache check")
mat.use_nodes = True
obj.data.materials.append(mat)
nodes, links = mat.node_tree.nodes, mat.node_tree.links
shader = nodes.get("Principled BSDF")
rgb, value = nodes.new("ShaderNodeRGB"), nodes.new("ShaderNodeValue")
links.new(rgb.outputs[0], shader.inputs["Base Color"])
links.new(value.outputs[0], shader.inputs["Roughness"])

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    (folder / "cache-config.json").write_text(json.dumps({"path": str(folder / "maps")}))

    def key(sources=None):
        return cache["location"](folder, mat, [obj], 256, sources)

    original = key()
    assert original is not None and key() == original
    rgb.outputs[0].default_value = (0.2, 0.4, 0.7, 1)
    color = key()
    assert color != original and key() == color
    value.outputs[0].default_value = 0.73
    assert key() != color
    image = bpy.data.images.new("Pixel edits", 2, 2)
    image.pack()
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    original = key()
    image.pixels[0] = 0.7
    assert key() != original, "An edited packed image reused stale maps"
    attribute = nodes.new("ShaderNodeAttribute")
    links.new(attribute.outputs["Color"], shader.inputs["Base Color"])
    assert key() is None, "Attribute-dependent graphs must bake without caching"
    nodes.remove(attribute)
    coord = nodes.new("ShaderNodeTexCoord")
    other = bpy.data.objects.new("Coordinate dependency", None)
    coord.object = other
    assert key() is None
    coord.object = None
    links.new(coord.outputs["Camera"], texture.inputs["Vector"])
    assert key() is None
    nodes.remove(coord)
    source = obj.copy()
    source.data = obj.data.copy()
    bpy.context.scene.collection.objects.link(source)
    sources = {obj.name: source}
    original = key(sources)
    source.data.vertices[0].co.x += 0.1
    assert key(sources) != original, "Source geometry affects the transferred normal map"
    obj.data.materials.append(mat.copy())
    assert key() is None, "Cross-material projection bypasses cache"

print(
    "PASS: real Blender cache invalidation: RGB/value outputs, packed pixels, normal source; "
    "implicit dependencies bypass caching"
)
