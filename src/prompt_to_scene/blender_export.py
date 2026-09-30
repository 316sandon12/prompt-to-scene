"""Executed by Blender, not the server's Python. Only static opaque PBR is supported."""

import hashlib
import json
import math
import runpy
import sys
from pathlib import Path

import bpy


def export_material(material, folder):
    if material is None or not material.use_nodes:
        raise ValueError("Every material must use a Principled BSDF node")
    tree = material.node_tree
    outputs = [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
    if len(outputs) != 1 or not outputs[0].inputs["Surface"].is_linked:
        raise ValueError(f"{material.name}: connect Principled BSDF directly to Material Output")
    if any(outputs[0].inputs[name].is_linked for name in ("Volume", "Displacement")):
        raise ValueError(f"{material.name}: volume and shader displacement are unsupported")
    principled = outputs[0].inputs["Surface"].links[0].from_node
    if principled.type != "BSDF_PRINCIPLED":
        raise ValueError(f"{material.name}: bake complex shaders to standard PBR before publishing")
    for socket in principled.inputs:
        if socket.is_linked and socket.name not in {"Base Color", "Normal"}:
            raise ValueError(f"{material.name}: {socket.name} cannot be linked in v0.1")
    for name in (
        "Alpha",
        "Transmission Weight",
        "Coat Weight",
        "Subsurface Weight",
        "Sheen Weight",
        "Anisotropic IOR Level",
    ):
        socket = principled.inputs.get(name)
        expected = 1 if name == "Alpha" else 0
        if socket and (socket.is_linked or abs(socket.default_value - expected) > 0.0001):
            raise ValueError(f"{material.name}: {name} is unsupported in v0.1 (opaque PBR only)")
    for name, expected in (("IOR", 1.5), ("Specular IOR Level", 0.5)):
        if abs(principled.inputs[name].default_value - expected) > 0.0001:
            raise ValueError(f"{material.name}: keep {name} at its default ({expected})")
    if any(abs(v - 1) > 0.0001 for v in principled.inputs["Specular Tint"].default_value[:3]):
        raise ValueError(f"{material.name}: colored specular tint is unsupported")
    emission = principled.inputs.get("Emission Color")
    strength = principled.inputs.get("Emission Strength")
    if (
        emission
        and strength
        and strength.default_value > 0
        and any(v > 0.0001 for v in emission.default_value[:3])
    ):
        raise ValueError(f"{material.name}: emission is not supported in v0.1")
    info = {
        "name": material.name,
        "color": list(principled.inputs["Base Color"].default_value),
        "metallic": float(principled.inputs["Metallic"].default_value),
        "roughness": float(principled.inputs["Roughness"].default_value),
        "base_color_texture": "",
        "normal_texture": "",
        "normal_strength": 1.0,
    }
    for input_name, field in (("Base Color", "base_color_texture"), ("Normal", "normal_texture")):
        socket = principled.inputs[input_name]
        if not socket.is_linked:
            continue
        link = socket.links[0]
        node = link.from_node
        if input_name == "Normal":
            if node.type != "NORMAL_MAP" or node.space != "TANGENT" or node.uv_map:
                raise ValueError(f"{material.name}: use a tangent-space Normal Map node")
            if node.inputs["Strength"].is_linked:
                raise ValueError("Normal strength must be a constant")
            info["normal_strength"] = float(node.inputs["Strength"].default_value)
            if not node.inputs["Color"].is_linked:
                raise ValueError("Normal Map requires an Image Texture")
            link = node.inputs["Color"].links[0]
            node = link.from_node
        if node.type != "TEX_IMAGE" or not node.image or link.from_socket.name != "Color":
            raise ValueError(
                f"{material.name}: {input_name} requires a direct Image Texture; bake first"
            )
        if (
            node.inputs["Vector"].is_linked
            or node.projection != "FLAT"
            or node.extension != "REPEAT"
            or node.interpolation != "Linear"
        ):
            raise ValueError(
                "v0.1 textures require default UVs, flat projection, repeat and linear filtering"
            )
        image = node.image
        if image.source not in {"FILE", "GENERATED"} or image.size[0] == 0:
            raise ValueError(f"Unsupported or missing image: {image.name}")
        expected_space = "sRGB" if input_name == "Base Color" else "Non-Color"
        if image.colorspace_settings.name != expected_space:
            raise ValueError(f"{image.name}: set color space to {expected_space}")
        filename = (
            "tex_" + hashlib.sha256((material.name + field).encode()).hexdigest()[:16] + ".png"
        )
        old_path, old_format = image.filepath_raw, image.file_format
        image.filepath_raw, image.file_format = str(folder / filename), "PNG"
        image.save()
        image.pack()
        image.filepath_raw, image.file_format = old_path, old_format
        info[field] = filename
        if input_name == "Base Color":
            info["color"] = [1, 1, 1, 1]
    return info


def main():
    folder = Path(sys.argv[sys.argv.index("--") + 1])
    script = folder / "model.py"
    if script.read_text().strip():
        runpy.run_path(str(script), run_name="__main__")
    collection = bpy.data.collections.get("Export")
    if collection is None:
        raise ValueError("Create a collection named Export and put your asset's meshes in it")
    meshes = [obj for obj in collection.all_objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Export collection has no meshes")
    materials = {}
    triangles = 0
    for obj in meshes:
        if any(not math.isfinite(v) or v <= 0 for v in obj.scale):
            raise ValueError(f"{obj.name}: apply/fix zero or negative scales before publishing")
        if obj.modifiers or obj.data.shape_keys or obj.animation_data:
            raise ValueError(
                f"{obj.name}: apply modifiers; animated/deforming meshes are unsupported"
            )
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
        if not obj.material_slots:
            raise ValueError(f"{obj.name}: assign a Principled BSDF material")
        for slot in obj.material_slots:
            info = export_material(slot.material, folder)
            if (info["base_color_texture"] or info["normal_texture"]) and len(
                obj.data.uv_layers
            ) != 1:
                raise ValueError(f"{obj.name}: textured meshes require exactly one UV map")
            materials[info["name"]] = info
    if triangles == 0 or triangles > 200000:
        raise ValueError("v0.1 accepts between 1 and 200,000 triangles per asset")
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "source.blend"))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.export_scene.fbx(
        filepath=str(folder / "model.fbx"),
        use_selection=True,
        object_types={"MESH"},
        axis_forward="-Z",
        axis_up="Y",
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS",
        bake_anim=False,
        add_leaf_bones=False,
        use_mesh_modifiers=False,
        path_mode="STRIP",
        mesh_smooth_type="FACE",
    )
    (folder / "export.json").write_text(
        json.dumps(
            {
                "materials": list(materials.values()),
                "triangles": triangles,
            }
        )
    )


if __name__ == "__main__":
    main()
