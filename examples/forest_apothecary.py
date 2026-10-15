"""Original jade-and-brass apothecary set. Set PTS_ASSET_KIND before this source.

Every object has a semantic part; geometry, material and lighting-independent color
are authored in Blender. No downloaded models, model weights or external textures.
"""

import math
import random

import bpy
from mathutils import Vector

kind = globals().get("PTS_ASSET_KIND", "workbench")
rng = random.Random(714)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
export = bpy.data.collections.new("Export")
bpy.context.scene.collection.children.link(export)


def material(name, color, roughness=0.5, metal=0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = roughness
    p.inputs["Metallic"].default_value = metal
    return m


jade = material("Glazed jade", (0.035, 0.24, 0.12), 0.24)
brass = material("Satin brass", (0.55, 0.30, 0.07), 0.32, 0.65)
wood = material("Oiled walnut", (0.16, 0.07, 0.027), 0.57)
edge = material("Honey wood edge", (0.29, 0.145, 0.052), 0.5)
ivory = material("Warm porcelain", (0.73, 0.63, 0.40), 0.29)
leafmat = material("Sage leaf", (0.12, 0.32, 0.105), 0.66)
leaflight = material("Fresh leaf tips", (0.28, 0.46, 0.12), 0.64)
cord = material("Woven linen", (0.43, 0.30, 0.13), 0.85)
stone = material("Chalk plaster", (0.43, 0.38, 0.28), 0.86)


def finish(obj, part, mat, bevel=0.008, smooth=False):
    obj.name = part
    obj["pts_part"] = part
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    export.objects.link(obj)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("Crafted edge", "BEVEL")
        mod.width, mod.segments = bevel, 3
        mod.affect = "EDGES"
    for polygon in obj.data.polygons:
        polygon.use_smooth = smooth
    if not smooth:
        mod = obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
        mod.keep_sharp = True
    return obj


def box(part, location, size, mat, bevel=0.008):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.scale = size
    return finish(obj, part, mat, bevel)


def rod(part, a, b, radius, mat):
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=radius, depth=(b - a).length, location=(a + b) / 2
    )
    obj = bpy.context.object
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return finish(obj, part, mat, radius * 0.2, True)


def ring(part, location, radius, thickness, mat, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_segments=40,
        minor_segments=8,
        major_radius=radius,
        minor_radius=thickness,
        location=location,
        rotation=rotation,
    )
    return finish(bpy.context.object, part, mat, 0, True)


def lathe(part, profile, mat, location=(0, 0, 0), segments=40):
    verts = [
        (
            r * math.cos(i * math.tau / segments) + location[0],
            r * math.sin(i * math.tau / segments) + location[1],
            z + location[2],
        )
        for z, r in profile
        for i in range(segments)
    ]
    faces = [
        (
            j * segments + i,
            j * segments + (i + 1) % segments,
            (j + 1) * segments + (i + 1) % segments,
            (j + 1) * segments + i,
        )
        for j in range(len(profile) - 1)
        for i in range(segments)
    ]
    faces.extend(
        [
            tuple(reversed(range(segments))),
            tuple((len(profile) - 1) * segments + i for i in range(segments)),
        ]
    )
    mesh = bpy.data.meshes.new(part)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(part, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, part, mat, 0.004, True)


def leaf(part, center, length, width, angle, mat):
    # Curved midrib and a folded silhouette remain legible at game distance.
    verts = []
    for t, w in ((0, 0), (0.22, 0.72), (0.52, 1), (0.78, 0.6), (1, 0)):
        for side in (-1, 0, 1):
            x = side * width * w / 2
            y = t * length
            z = 0.015 * math.sin(t * math.pi) + (0.008 if side == 0 else 0)
            verts.append(
                (
                    center[0] + x * math.cos(angle) - y * math.sin(angle),
                    center[1] + x * math.sin(angle) + y * math.cos(angle),
                    center[2] + z,
                )
            )
    faces = [
        (j * 3 + k, j * 3 + k + 1, (j + 1) * 3 + k + 1, (j + 1) * 3 + k)
        for j in range(4)
        for k in range(2)
    ]
    mesh = bpy.data.meshes.new(part)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(part, mesh)
    bpy.context.collection.objects.link(obj)
    finish(obj, part, mat, 0, True)
    solid = obj.modifiers.new("Leaf thickness", "SOLIDIFY")
    solid.thickness = 0.002
    return obj


def bottle(location=(0, 0, 0), scale=1, filled=False):
    profile = [(0, 0.08), (0.025, 0.10), (0.17, 0.10), (0.23, 0.055), (0.29, 0.045), (0.31, 0.051)]
    lathe(
        "vessel", [(z * scale, r * scale) for z, r in profile], jade if filled else ivory, location
    )
    for z, r in ((0.025, 0.10), (0.285, 0.047)):
        ring(
            "brass_trim",
            (location[0], location[1], location[2] + z * scale),
            r * scale,
            0.005 * scale,
            brass,
        )
    lathe("stopper", [(0.30 * scale, 0.043 * scale), (0.34 * scale, 0.047 * scale)], cord, location)
    seal = box(
        "seal",
        (location[0], location[1] - 0.10 * scale, location[2] + 0.12 * scale),
        (0.08 * scale, 0.006 * scale, 0.09 * scale),
        ivory,
        0.008 * scale,
    )
    seal.rotation_euler[1] = -0.08


if kind == "herb":
    for i in range(7):
        angle = i * 2.4
        end = (math.cos(angle) * 0.075, math.sin(angle) * 0.075, 0.27 + rng.random() * 0.08)
        rod("stems", (0, 0, 0.015), end, 0.004, leafmat)
        for j in range(3):
            t = 0.44 + j * 0.22
            leaf(
                "leaves",
                (end[0] * t, end[1] * t, end[2] * t),
                0.105,
                0.052,
                angle + j * 1.8,
                leafmat if j % 2 else leaflight,
            )
    for z in (0.055, 0.066, 0.077):
        ring("linen_tie", (0, 0, z), 0.026, 0.003, cord)
elif kind == "bottle":
    bottle(scale=1.25)
elif kind == "workbench":
    for x in (-0.68, 0.68):
        for y in (-0.3, 0.3):
            box("turned_legs", (x, y, 0.43), (0.10, 0.10, 0.86), wood, 0.015)
            for z in (0.08, 0.65):
                box("leg_collars", (x, y, z), (0.125, 0.125, 0.045), edge, 0.008)
    for x in (-0.68, 0.68):
        box("side_rails", (x, 0, 0.28), (0.065, 0.69, 0.095), edge)
    box("lower_stretcher", (0, 0.25, 0.29), (1.4, 0.065, 0.085), wood)
    box("cabinet", (0, 0, 0.68), (1.30, 0.59, 0.24), wood, 0.012)
    for x in (-0.33, 0.33):
        box("drawer_frame", (x, -0.31, 0.69), (0.61, 0.05, 0.18), edge, 0.009)
        box("drawer_inlay", (x, -0.341, 0.69), (0.50, 0.012, 0.115), jade, 0.006)
        ring("drawer_pull", (x, -0.365, 0.69), 0.034, 0.006, brass, (math.pi / 2, 0, 0))
    for i in range(5):
        box(
            "worktop_planks",
            (0, -0.34 + i * 0.17, 0.86),
            (1.62, 0.164, 0.075),
            edge if i % 2 else wood,
            0.012,
        )
    box("worktop_rim", (0, 0.40, 0.90), (1.68, 0.055, 0.09), brass, 0.008)
    for x in (-0.77, 0.77):
        box("corner_cap", (x, 0, 0.90), (0.045, 0.84, 0.018), brass, 0.005)
    bottle((0.48, 0.15, 0.90), 0.8, True)
    lathe(
        "mortar",
        [(0, 0.10), (0.02, 0.12), (0.12, 0.15), (0.15, 0.15), (0.15, 0.125), (0.06, 0.09)],
        ivory,
        (-0.40, -0.10, 0.90),
    )
    rod("pestle", (-0.44, -0.1, 0.95), (-0.27, -0.1, 1.14), 0.025, wood)
    box("recipe_book", (0.05, 0.02, 0.945), (0.28, 0.23, 0.06), jade, 0.007)
    box("book_pages", (0.05, -0.01, 0.945), (0.25, 0.20, 0.041), ivory, 0.004)
elif kind == "shelf":
    for x in (-0.62, 0.62):
        box("uprights", (x, 0, 0.95), (0.09, 0.35, 1.9), wood, 0.012)
    box("back_panel", (0, 0.16, 1.0), (1.2, 0.035, 1.62), jade, 0.008)
    for z in (0.18, 0.72, 1.25, 1.80):
        box("shelves", (0, -0.03, z), (1.4, 0.49, 0.065), edge, 0.012)
        box("shelf_brass_lip", (0, -0.28, z + 0.02), (1.36, 0.018, 0.035), brass, 0.004)
    for z in (0.22, 0.76, 1.29):
        for i in range(4):
            bottle((-0.44 + i * 0.29, -0.06, z), 0.7 + (i % 2) * 0.15, i % 2 == 0)
    box("crest", (0, 0.05, 1.95), (0.62, 0.12, 0.16), edge, 0.04)
    ring("crest_medallion", (0, -0.02, 1.95), 0.06, 0.009, brass, (math.pi / 2, 0, 0))
elif kind == "lantern":
    lathe("base", [(0, 0.14), (0.03, 0.15), (0.06, 0.13), (0.08, 0.1)], jade)
    lathe("candle", [(0.08, 0.052), (0.32, 0.052)], ivory)
    for angle in range(4):
        x, y = math.cos(angle * math.pi / 2) * 0.11, math.sin(angle * math.pi / 2) * 0.11
        rod("brass_cage", (x, y, 0.07), (x, y, 0.38), 0.008, brass)
    lathe("roof", [(0.38, 0.15), (0.40, 0.15), (0.50, 0.025)], jade)
    ring("handle", (0, 0, 0.55), 0.065, 0.009, brass, (math.pi / 2, 0, 0))
    flame = material("Warm flame", (0.95, 0.36, 0.04), 0.6)
    p = flame.node_tree.nodes.get("Principled BSDF")
    p.inputs["Emission Color"].default_value = (1, 0.35, 0.04, 1)
    p.inputs["Emission Strength"].default_value = 2
    lathe("flame", [(0.32, 0.008), (0.35, 0.025), (0.40, 0.001)], flame, segments=20)
elif kind == "cottage":
    for i in range(12):
        box(
            "floorboards",
            (0, -1.5 + i * 0.27, -0.05),
            (4.6, 0.263, 0.1),
            wood if i % 3 else edge,
            0.006,
        )
    box("back_plaster", (0, 1.72, 1.45), (4.6, 0.12, 2.9), stone, 0.015)
    for x in (-2.25, 0, 2.25):
        box("timber_posts", (x, 1.60, 1.45), (0.14, 0.16, 2.9), wood, 0.012)
    for z in (0.18, 2.65):
        box("back_beams", (0, 1.60, z), (4.6, 0.16, 0.14), edge, 0.009)
    for x in (-1.15, 1.15):
        box("wall_inset", (x, 1.53, 1.65), (0.78, 0.08, 1.02), jade, 0.07)
        for dx in (-0.43, 0.43):
            box("inset_frame", (x + dx, 1.46, 1.65), (0.06, 0.06, 1.12), brass, 0.006)
        for z in (1.10, 2.20):
            box("inset_frame", (x, 1.46, z), (0.91, 0.06, 0.06), brass, 0.006)
    for x in (-2.15, 2.15):
        rod("front_posts", (x, -1.3, 0), (x, -1.3, 2.65), 0.075, wood)
        rod("eaves", (x, -1.3, 2.6), (x, 1.60, 2.6), 0.07, edge)
else:
    raise ValueError("Choose herb, bottle, workbench, shelf, lantern or cottage")

for obj in list(export.objects):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
