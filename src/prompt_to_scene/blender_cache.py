"""Content-addressed baked maps, validated before reuse. Runs inside Blender."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import bpy

FIELDS = ("base", "roughness", "metallic", "normal")
# Only cache graphs whose dependencies are represented below. Other graphs still bake.
CACHEABLE_NODES = {
    "NodeFrame",
    "NodeReroute",
    "NodeGroupInput",
    "NodeGroupOutput",
    "ShaderNodeGroup",
    "ShaderNodeBsdfPrincipled",
    "ShaderNodeOutputMaterial",
    "ShaderNodeRGB",
    "ShaderNodeValue",
    "ShaderNodeTexCoord",
    "ShaderNodeUVMap",
    "ShaderNodeTexImage",
    "ShaderNodeTexNoise",
    "ShaderNodeTexWave",
    "ShaderNodeTexGradient",
    "ShaderNodeTexVoronoi",
    "ShaderNodeTexMagic",
    "ShaderNodeTexChecker",
    "ShaderNodeTexBrick",
    "ShaderNodeTexWhiteNoise",
    "ShaderNodeMapping",
    "ShaderNodeValToRGB",
    "ShaderNodeMapRange",
    "ShaderNodeBump",
    "ShaderNodeNormalMap",
    "ShaderNodeNormal",
    "ShaderNodeMath",
    "ShaderNodeVectorMath",
    "ShaderNodeMix",
    "ShaderNodeMixRGB",
    "ShaderNodeSeparateColor",
    "ShaderNodeCombineColor",
    "ShaderNodeSeparateRGB",
    "ShaderNodeCombineRGB",
    "ShaderNodeSeparateXYZ",
    "ShaderNodeCombineXYZ",
    "ShaderNodeRGBToBW",
    "ShaderNodeHueSaturation",
    "ShaderNodeBrightContrast",
    "ShaderNodeInvert",
    "ShaderNodeGamma",
    "ShaderNodeClamp",
}


class UncacheableGraph(ValueError):
    pass


def scalars(value):
    result = {}
    for prop in value.bl_rna.properties:
        if prop.identifier in {"location", "width", "height", "select", "name", "label"}:
            continue
        if prop.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"} and not prop.is_readonly:
            item = getattr(value, prop.identifier)
            result[prop.identifier] = (
                (sorted(item) if isinstance(item, set) else list(item))
                if getattr(prop, "is_array", False) or isinstance(item, set)
                else item
            )
    return result


def ramp(value):
    return {**scalars(value), "elements": [(e.position, list(e.color)) for e in value.elements]}


def geometry(obj):
    mesh = obj.data
    return {
        "vertices": [list(v.co) for v in mesh.vertices],
        "faces": [list(p.vertices) for p in mesh.polygons],
        "material_indices": [p.material_index for p in mesh.polygons],
        "uv": [[list(v.uv) for v in uv.data] for uv in mesh.uv_layers],
        "uv_names": [(uv.name, uv.active_render) for uv in mesh.uv_layers],
        "matrix": [list(row) for row in obj.matrix_world],
        "smooth": [p.use_smooth for p in mesh.polygons],
        "normals": [list(n.vector) for n in mesh.corner_normals],
    }


def graph(tree, seen=None):
    seen = set(seen or ())
    if tree.name in seen:
        raise ValueError("Recursive material graph")
    seen.add(tree.name)
    nodes = []
    for node in tree.nodes:
        if (
            node.bl_idname not in CACHEABLE_NODES
            or getattr(node, "object", None)
            or getattr(node, "from_instancer", False)
        ):
            raise UncacheableGraph(node.bl_idname)
        if node.type == "TEX_COORD" and any(
            node.outputs[name].is_linked for name in ("Camera", "Window", "Reflection")
        ):
            raise UncacheableGraph("View-dependent coordinates")
        data = {"name": node.name, "type": node.bl_idname, **scalars(node)}
        for direction in ("inputs", "outputs"):
            data[direction] = {}
            for index, socket in enumerate(getattr(node, direction)):
                if hasattr(socket, "default_value"):
                    value = socket.default_value
                    if isinstance(value, (int, float, str, bool)):
                        data[direction][str(index)] = value
                    elif hasattr(value, "__len__"):
                        data[direction][str(index)] = list(value)
        if hasattr(node, "color_ramp"):
            data["ramp"] = ramp(node.color_ramp)
        for name in ("texture_mapping", "color_mapping"):
            if hasattr(node, name):
                mapping = getattr(node, name)
                data[name] = scalars(mapping)
                if hasattr(mapping, "color_ramp"):
                    data[name]["ramp"] = ramp(mapping.color_ramp)
        if getattr(node, "image", None):
            import array

            image = node.image
            if image.source not in {"FILE", "GENERATED"} or image.use_multiview:
                raise UncacheableGraph("Animated, tiled or multiview image")
            # Pixels may have been edited since packing; packed_file can then be stale.
            values = array.array("f", [0]) * len(image.pixels)
            image.pixels.foreach_get(values)
            data["image"] = [
                hashlib.sha256(values.tobytes()).hexdigest(),
                image.colorspace_settings.name,
                image.alpha_mode,
                list(image.size),
            ]
        if getattr(node, "node_tree", None):
            data["group"] = graph(node.node_tree, seen)
        nodes.append(data)
    return {
        "nodes": nodes,
        "links": [
            (
                link.from_node.name,
                link.from_socket.identifier,
                link.to_node.name,
                link.to_socket.identifier,
            )
            for link in tree.links
        ],
    }


def location(folder, material, objects, size, normal_sources):
    path = folder / "cache-config.json"
    if not path.exists():
        return None
    if any(len(o.material_slots) != 1 for o in objects):
        # Projection across several materials can depend on another material's normal graph.
        return None
    try:
        shader = graph(material.node_tree)
    except UncacheableGraph:
        return None
    data = {
        "version": 2,
        "blender": list(bpy.app.version),
        "size": size,
        "graph": shader,
        "geometry": [geometry(o) for o in objects],
        "sources": [geometry(normal_sources[o.name]) for o in objects] if normal_sources else [],
    }
    key = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return Path(json.loads(path.read_text())["path"]) / key


def read(path):
    if path is None:
        return None
    try:
        manifest = json.loads((path / "manifest.json").read_text())
        if set(manifest) != set(FIELDS):
            return None
        for field in FIELDS:
            if (
                hashlib.sha256((path / (field + ".png")).read_bytes()).hexdigest()
                != manifest[field]
            ):
                return None
        result = {}
        for field in FIELDS:
            image = bpy.data.images.load(str(path / (field + ".png")), check_existing=False)
            image.colorspace_settings.name = "sRGB" if field == "base" else "Non-Color"
            image.pack()
            result[field] = image
        return result
    except (OSError, ValueError, RuntimeError):
        return None


def write(path, images):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".bake-", dir=path.parent))
    try:
        manifest = {}
        for field, image in images.items():
            content = Path(image.filepath_raw).read_bytes()
            (temporary / (field + ".png")).write_bytes(content)
            manifest[field] = hashlib.sha256(content).hexdigest()
        (temporary / "manifest.json").write_text(json.dumps(manifest))
        try:
            os.rename(temporary, path)
        except OSError:
            if not path.is_dir():
                raise
            # Another build populated this key; all writes were isolated until publication.
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
