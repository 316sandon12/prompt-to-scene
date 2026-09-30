"""Blender-only realization of semantic plans. Executed by a retained recipe script."""

import json
import math
import runpy
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector

QUALITY = {
    "draft": (0, 1, 12),
    "mobile": (256, 2, 16),
    "desktop": (512, 3, 24),
    "hero": (1024, 4, 32),
}


def lathe(name, rings, segments, cap=True):
    vertices = [
        (rx * math.cos(a * math.tau / segments), ry * math.sin(a * math.tau / segments), z)
        for rx, ry, z in rings
        for a in range(segments)
    ]
    faces = []
    for j in range(len(rings) - 1):
        for i in range(segments):
            k = (i + 1) % segments
            faces.append(
                (j * segments + i, j * segments + k, (j + 1) * segments + k, (j + 1) * segments + i)
            )
    if cap:
        faces += [
            tuple(reversed(range(segments))),
            tuple((len(rings) - 1) * segments + i for i in range(segments)),
        ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def build(payload):
    recipe, items = payload["recipe"], payload["objects"]
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    old = bpy.data.collections.get("Export")
    if old:
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(collection)
    resolution, segments, radial = QUALITY[recipe["style"]["quality"]]
    material_driver = runpy.run_path(str(Path(__file__).with_name("blender_surfaces.py")))
    materials = {}
    for item in items:
        _, segments, radial = QUALITY[item.get("quality", recipe["style"]["quality"])]
        name, size, shape = item["name"], item["size"], item["shape"]
        w, d, h = size
        if shape == "box":
            bpy.ops.mesh.primitive_cube_add(size=1)
            obj = bpy.context.object
            obj.dimensions = size
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        elif shape == "taper":
            taper = item["taper"]
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(
                [
                    (x * w / 2 * t, y * d / 2 * t, z * h / 2)
                    for z, t in ((-1, taper), (1, 1))
                    for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))
                ],
                [],
                [
                    (3, 2, 1, 0),
                    (4, 5, 6, 7),
                    (0, 1, 5, 4),
                    (1, 2, 6, 5),
                    (2, 3, 7, 6),
                    (3, 0, 4, 7),
                ],
            )
            obj = bpy.data.objects.new(name, mesh)
            collection.objects.link(obj)
        else:
            if shape == "barrel":
                rings = [
                    (
                        w
                        / 2
                        * (
                            (1 - item["bulge"] * 1.6)
                            + item["bulge"] * 1.6 * math.sin(math.pi * i / 8)
                        ),
                        d
                        / 2
                        * (
                            (1 - item["bulge"] * 1.6)
                            + item["bulge"] * 1.6 * math.sin(math.pi * i / 8)
                        ),
                        -h / 2 + h * i / 8,
                    )
                    for i in range(9)
                ]
            elif shape == "ring":
                thickness = min(item["thickness"], min(w, d) * 0.15)
                rings = [
                    (w / 2, d / 2, -h / 2),
                    (w / 2, d / 2, h / 2),
                    (w / 2 - thickness, d / 2 - thickness, h / 2),
                    (w / 2 - thickness, d / 2 - thickness, -h / 2),
                    (w / 2, d / 2, -h / 2),
                ]
            else:
                rings = [(w / 2, d / 2, -h / 2), (w / 2, d / 2, h / 2)]
            obj = bpy.data.objects.new(name, lathe(name, rings, radial, cap=shape != "ring"))
            collection.objects.link(obj)
        obj.name = name
        for owner in list(obj.users_collection):
            if owner != collection:
                owner.objects.unlink(obj)
        if collection not in obj.users_collection:
            collection.objects.link(obj)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bevel = obj.modifiers.new("Designed edge radius", "BEVEL")
        bevel.width = min(size) * (0.025 + item["roundness"] * 0.13)
        bevel.segments = segments
        bevel.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=bevel.name)
        if shape in {"cylinder", "barrel", "ring"}:
            for polygon in obj.data.polygons:
                polygon.use_smooth = abs(polygon.normal.z) < 0.8
        local = (
            Matrix.Translation(Vector(item["center"]))
            @ Euler(item.get("rotation", [0, 0, 0])).to_matrix().to_4x4()
        )
        pivot = Vector(item["part_pivot"])
        part = (
            Matrix.Translation(pivot + Vector(item["part_offset"]))
            @ Euler([math.radians(a) for a in item["part_rotation"]]).to_matrix().to_4x4()
            @ Matrix.Diagonal((*item["part_scale"], 1))
            @ Matrix.Translation(-pivot)
        )
        obj.data.transform(part @ local)
        obj["pts_part"] = item["part"]
        key = item["material_name"]
        if key not in materials:
            materials[key] = material_driver["surface"](key, item["surface"], bool(resolution))
        obj.data.materials.append(materials[key])
    bpy.context.scene["pts_recipe"] = json.dumps(recipe)
    bpy.context.scene["pts_texture_size"] = resolution
    bpy.context.scene["pts_bake_needed"] = bool(resolution)
    # The exporter owns UV/baking so custom sources and recipe sources share validation.
