"""Blender-only read of retained meshes; never save over the source file."""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main():
    config = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
    collection = bpy.data.collections.get("Export")
    if not collection:
        raise ValueError("Missing Export meshes")
    objects = [o for o in collection.all_objects if o.type == "MESH"]
    if not objects:
        raise ValueError("No meshes to preview")
    points = [o.matrix_world @ Vector(p) for o in objects for p in o.bound_box]
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    center, size = (low + high) / 2, max((high - low).length, 0.1)
    if config["mode"] == "view":
        rows = []
        budget = 60000
        count = sum(sum(max(1, len(p.vertices) - 2) for p in o.data.polygons) for o in objects)
        for original in objects:
            obj = original.copy()
            obj.data = original.data.copy()
            bpy.context.scene.collection.objects.link(obj)
            if count > budget:
                modifier = obj.modifiers.new("Preview simplification", "DECIMATE")
                modifier.ratio = budget / count * 0.7
            evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            mesh.calc_loop_triangles()
            position, normal, color = [], [], []
            normals = obj.matrix_world.to_3x3().inverted().transposed()
            for triangle in mesh.loop_triangles:
                mat = mesh.materials[triangle.material_index] if mesh.materials else None
                rgba = mat.diffuse_color if mat else (0.45, 0.5, 0.45, 1)
                if mat and mat.use_nodes:
                    shader = next(
                        (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None
                    )
                    if shader:
                        rgba = shader.inputs["Base Color"].default_value
                n = (normals @ triangle.normal).normalized()
                for index in triangle.vertices:
                    p = obj.matrix_world @ mesh.vertices[index].co
                    position.extend(round(v, 5) for v in p)
                    normal.extend(round(v, 5) for v in n)
                    color.extend(round(max(0, min(1, v)), 4) for v in rgba[:3])
            rows.append(
                dict(
                    name=original.get("pts_part", original.name),
                    object=original.name,
                    position=position,
                    normal=normal,
                    color=color,
                )
            )
            evaluated.to_mesh_clear()
            bpy.data.objects.remove(obj, do_unlink=True)
        result = {
            "asset_id": config["asset_id"],
            "revision": config["revision"],
            "bounds": [list(low), list(high)],
            "parts": rows,
            "simplified": count > budget,
            "note": "Actual source geometry with approximate solid materials; "
            "use native preview for final shading.",
        }
        Path(config["output"]).write_text(json.dumps(result, separators=(",", ":")))
        return
    scene = bpy.context.scene
    for obj in scene.objects:
        obj.hide_render = obj not in objects
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "AgX"
    if not scene.world:
        scene.world = bpy.data.worlds.new("Icon world")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    for offset, power in (((-2, -3, 4), 550), ((3, -1, 2), 250), ((0, 3, 3), 400)):
        light = bpy.data.lights.new("Icon softbox", "AREA")
        light.energy, light.size = power * size * size, size * 3
        obj = bpy.data.objects.new("Icon softbox", light)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(offset) * size
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    camera = bpy.data.objects.new("Icon camera", bpy.data.cameras.new("Icon camera"))
    scene.collection.objects.link(camera)
    camera.data.type, camera.data.ortho_scale = "ORTHO", size * 1.15
    camera.location = center + Vector((1.4, -2, 1.25)) * size
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera, scene.render.filepath = camera, config["output"]
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
