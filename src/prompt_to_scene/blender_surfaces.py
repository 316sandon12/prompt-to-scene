"""Curated procedural PBR surfaces and lighting-independent texture baking in Blender."""

import hashlib
import json
import runpy
from pathlib import Path

import bpy


def surface(name, data, textured):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat["pts_reuse_path"] = data.get("reuse_path", "")
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*data["color"], 1)
    shader.inputs["Metallic"].default_value = 0.82 if data["role"] == "metal" else 0
    shader.inputs["Roughness"].default_value = data["roughness"]
    if not textured:
        return mat
    coord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    noise.inputs["W"].default_value = data["seed"] * 0.137
    noise.inputs["Scale"].default_value = 8 if data["role"] == "stone" else 35
    noise.inputs["Detail"].default_value = 3
    links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    pattern = noise.outputs["Fac"]
    if data["role"] == "wood" and data.get("grain"):
        attribute = nodes.new("ShaderNodeAttribute")
        attribute.attribute_name = "pts_grain"
        noise.inputs["Scale"].default_value = 1
        noise.inputs["Detail"].default_value = 2
        links.new(attribute.outputs["Vector"], noise.inputs["Vector"])
    elif data["role"] == "wood":
        wave = nodes.new("ShaderNodeTexWave")
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = 5
        wave.inputs["Distortion"].default_value = 2
        wave.inputs["Detail"].default_value = 3
        wave.inputs["Detail Scale"].default_value = 1.5
        links.new(coord.outputs["Generated"], wave.inputs["Vector"])
        pattern = wave.outputs["Color"]
    ramp = nodes.new("ShaderNodeValToRGB")
    amount = (0.06 + data["wear"] * 0.14) if data.get("grain") else (0.09 + data["wear"] * 0.3)
    if data.get("quiet"):
        amount *= 0.5
    color = data["color"]
    ramp.color_ramp.elements[0].position = 0.12
    ramp.color_ramp.elements[0].color = (*(max(0, c * (1 - amount)) for c in color), 1)
    ramp.color_ramp.elements[1].position = 0.86
    ramp.color_ramp.elements[1].color = (
        *(min(1, c * (1 + amount) + data["wear"] * 0.025) for c in color),
        1,
    )
    links.new(pattern, ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    rough = nodes.new("ShaderNodeMapRange")
    rough.inputs["To Min"].default_value = max(0.03, data["roughness"] - 0.08 - data["wear"] * 0.07)
    rough.inputs["To Max"].default_value = min(0.97, data["roughness"] + 0.09)
    links.new(noise.outputs["Fac"], rough.inputs["Value"])
    links.new(rough.outputs["Result"], shader.inputs["Roughness"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06 + data["wear"] * 0.16
    if data.get("grain"):
        bump.inputs["Strength"].default_value *= 0.35 if data.get("quiet") else 0.6
    bump.inputs["Distance"].default_value = 0.0018 if data["role"] == "wood" else 0.0015
    links.new(pattern, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    return mat


def bake(meshes, folder, size, unwrap=True, normal_sources=None):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 4
    scene.render.bake.margin = max(3, size // 128)
    scene.render.bake.use_clear = True
    # Multi-object unwrap packs a shared atlas. Each semantic object keeps its own mesh.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if unwrap:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.025)
        bpy.ops.object.mode_set(mode="OBJECT")
    else:
        for obj in meshes:
            if not obj.data.uv_layers:
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.025)
                bpy.ops.object.mode_set(mode="OBJECT")
            obj.data.uv_layers.active_index = 0
    cache = runpy.run_path(str(Path(__file__).with_name("blender_cache.py")))
    stats = {"reused_materials": [], "baked_materials": []}
    materials = {slot.material for obj in meshes for slot in obj.material_slots}
    for mat in materials:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        output = next(n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
        selected = [obj for obj in meshes if mat in list(obj.data.materials)]
        cache_path = cache["location"](folder, mat, selected, size, normal_sources)
        images = cache["read"](cache_path)
        fields = [
            ("base", "Base Color"),
            ("roughness", "Roughness"),
            ("metallic", "Metallic"),
            ("normal", "Normal"),
        ]
        fields += [
            (field, socket)
            for field, socket in (("opacity", "Alpha"), ("emission", "Emission Color"))
            if shader.inputs[socket].is_linked
        ]
        if images and set(images) != {field for field, _ in fields}:
            images = None
        if images:
            stats["reused_materials"].append(mat.name)
        else:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in selected:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = selected[0]
            images = {}
            emission = nodes.new("ShaderNodeEmission")
            target = nodes.new("ShaderNodeTexImage")
            for field, socket_name in fields:
                image = bpy.data.images.new(
                    mat.name + "_" + field, width=size, height=size, alpha=False
                )
                image.colorspace_settings.name = (
                    "sRGB" if field in {"base", "emission"} else "Non-Color"
                )
                target.image = image
                nodes.active = target
                if field == "normal":
                    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
                    if normal_sources:
                        # Transfer source shading to the reduced surface, including its normal map.
                        # Pair objects so rays cannot land on an adjacent part of the asset.
                        for index, obj in enumerate(selected):
                            source = normal_sources[obj.name]
                            bpy.ops.object.select_all(action="DESELECT")
                            source.hide_render = False
                            source.select_set(True)
                            obj.select_set(True)
                            bpy.context.view_layer.objects.active = obj
                            distance = max(source.dimensions.length * 0.04, 0.0001)
                            try:
                                bpy.ops.object.bake(
                                    type="NORMAL",
                                    normal_space="TANGENT",
                                    use_selected_to_active=True,
                                    use_clear=index == 0,
                                    cage_extrusion=distance,
                                    max_ray_distance=distance * 2,
                                )
                            finally:
                                source.hide_render = True
                        bpy.ops.object.select_all(action="DESELECT")
                        for obj in selected:
                            obj.select_set(True)
                        bpy.context.view_layer.objects.active = selected[0]
                    else:
                        bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
                else:
                    socket = shader.inputs[socket_name]
                    for link in list(emission.inputs["Color"].links):
                        links.remove(link)
                    if socket.is_linked:
                        links.new(socket.links[0].from_socket, emission.inputs["Color"])
                    else:
                        value = socket.default_value
                        emission.inputs["Color"].default_value = (
                            value if field in {"base", "emission"} else (value, value, value, 1)
                        )
                    links.new(emission.outputs["Emission"], output.inputs["Surface"])
                    bpy.ops.object.bake(type="EMIT")
                filename = (
                    "bake_"
                    + hashlib.sha256((mat.name + field + "_baked").encode()).hexdigest()[:16]
                    + ".png"
                )
                image.filepath_raw = str(folder / filename)
                image.file_format = "PNG"
                image.save()
                image.pack()
                images[field] = image
            links.new(shader.outputs["BSDF"], output.inputs["Surface"])
            nodes.remove(emission)
            nodes.remove(target)
            cache["write"](cache_path, images)
            stats["baked_materials"].append(mat.name)
        for field, socket_name in fields:
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = images[field]
            if field == "normal":
                normal = nodes.new("ShaderNodeNormalMap")
                links.new(texture.outputs["Color"], normal.inputs["Color"])
                links.new(normal.outputs["Normal"], shader.inputs["Normal"])
            else:
                links.new(texture.outputs["Color"], shader.inputs[socket_name])
    scene["pts_bake_cache"] = json.dumps(stats)
    scene["pts_bake_needed"] = False
    for obj in meshes:
        while len(obj.data.uv_layers) > 1:
            obj.data.uv_layers.remove(obj.data.uv_layers[-1])
