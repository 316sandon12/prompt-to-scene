"""Measured static-mesh preparation. Executed only by Blender's bundled Python."""

import json
import math
import runpy
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree


def triangle_count(mesh):
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def bounds(meshes):
    points = [obj.matrix_world @ vertex.co for obj in meshes for vertex in obj.data.vertices]
    if not points or any(not math.isfinite(c) for v in points for c in v):
        raise ValueError("Source has empty or non-finite geometry")
    return [min(v[i] for v in points) for i in range(3)], [
        max(v[i] for v in points) for i in range(3)
    ]


def normalize(meshes, config):
    axis = config["up_axis"]
    rotation = Matrix.Identity(3)
    if axis not in {"auto", "Z"}:
        up = Vector((0, 0, 0))
        up["XYZ".index(axis[-1])] = -1 if axis.startswith("-") else 1
        rotation = up.rotation_difference(Vector((0, 0, 1))).to_matrix()
    for obj in meshes:
        matrix = obj.matrix_world.copy()
        obj.parent = None
        obj.data = obj.data.copy()
        obj.data.transform(matrix)
        if matrix.determinant() < 0:
            obj.data.flip_normals()
        obj.matrix_world = Matrix.Identity(4)
        obj.data.transform(rotation.to_4x4())
    low, high = bounds(meshes)
    size = max(b - a for a, b in zip(low, high))
    if size < 1e-9:
        raise ValueError("Source geometry has zero size")
    factor = config["target_size"] / size if config["target_size"] else config["unit_scale"]
    offset = Vector(((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2]))
    for obj in meshes:
        for vertex in obj.data.vertices:
            vertex.co = (vertex.co - (offset if config["ground"] else Vector())) * factor
        obj.data.update()
    return {
        "input_bounds": [low, high],
        "output_bounds": bounds(meshes),
        "scale_applied": factor,
        "up_axis": axis,
        "grounded": config["ground"],
    }


def boundary_edges(mesh):
    counts = {}
    for poly in mesh.polygons:
        for edge in poly.edge_keys:
            counts[edge] = counts.get(edge, 0) + 1
    return sum(v == 1 for v in counts.values())


def sampled_error(before, after, diagonal):
    """Two-way vertex + face-centroid sampling; explicitly not a Hausdorff guarantee."""

    def geometry(mesh):
        mesh.calc_loop_triangles()
        points = [v.co.copy() for v in mesh.vertices]
        faces = [tuple(t.vertices) for t in mesh.loop_triangles]
        if not points or not faces:
            raise ValueError("Reduction removed all faces")
        bvh = BVHTree.FromPolygons(points, faces, all_triangles=True)
        samples = points[:: max(1, len(points) // 4096)]
        samples += [
            sum((points[i] for i in face), Vector()) / 3
            for face in faces[:: max(1, len(faces) // 4096)]
        ]
        return bvh, samples

    first, a = geometry(before)
    second, b = geometry(after)
    distance = max(
        tree.find_nearest(point)[3]
        for tree, points in ((second, a), (first, b))
        for point in points
    )
    return {
        "sampled_max_deviation_percent": distance / max(diagonal, 1e-8) * 100,
        "samples": len(a) + len(b),
        "two_sided": True,
        "new_boundary_edges": max(0, boundary_edges(after) - boundary_edges(before)),
    }


def reduce_object(obj, ratio, threshold):
    original = obj.data
    before = triangle_count(original)
    if before < 24 or ratio >= 0.999:
        return {
            "before": before,
            "after": before,
            "accepted": True,
            "sampled_max_deviation_percent": 0,
            "samples": 0,
            "new_boundary_edges": 0,
        }
    obj.data = original.copy()
    # glTF/FBX split vertices at UV and normal seams. Weld coincident geometry while
    # retaining face-corner UVs, so collapse does not pull those shells apart.
    low = [min(v.co[i] for v in original.vertices) for i in range(3)]
    high = [max(v.co[i] for v in original.vertices) for i in range(3)]
    diagonal = (Vector(high) - Vector(low)).length
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=max(1e-9, diagonal * 1e-7))
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    boundary_before = boundary_edges(obj.data)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("PTS measured reduction", "DECIMATE")
    modifier.ratio = max(0.01, ratio)
    modifier.use_collapse_triangulate = True
    try:
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        error = sampled_error(original, obj.data, diagonal)
        error["new_boundary_edges"] = max(0, boundary_edges(obj.data) - boundary_before)
        accepted = (
            error["sampled_max_deviation_percent"] <= threshold and not error["new_boundary_edges"]
        )
        attempted = triangle_count(obj.data)
    except Exception:
        obj.modifiers.clear()
        obj.data = original
        raise
    if not accepted:
        reduced = obj.data
        obj.data = original
        bpy.data.meshes.remove(reduced)
    return {
        "before": before,
        "after": triangle_count(obj.data),
        "attempted": attempted,
        "accepted": accepted,
        "threshold_percent": threshold,
        **error,
    }


def compatible_materials(meshes):
    materials = {slot.material for obj in meshes for slot in obj.material_slots}
    if len(materials) > 20:
        raise ValueError("Use at most 20 source materials per asset")
    for mat in materials:
        if not mat or not mat.use_nodes:
            raise ValueError("External materials must use opaque Principled PBR")
        nodes = mat.node_tree.nodes
        output = next(
            (n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None
        )
        if not output or not output.inputs["Surface"].is_linked:
            raise ValueError("Missing material surface: " + mat.name)
        shader = output.inputs["Surface"].links[0].from_node
        if shader.type != "BSDF_PRINCIPLED":
            raise ValueError(mat.name + ": mixed/unlit shaders need an opaque Principled export")
        for key, default in (
            ("Alpha", 1),
            ("Transmission Weight", 0),
            ("Coat Weight", 0),
            ("Subsurface Weight", 0),
            ("Sheen Weight", 0),
        ):
            socket = shader.inputs.get(key)
            if socket and (socket.is_linked or abs(socket.default_value - default) > 1e-5):
                raise ValueError(mat.name + ": unsupported " + key + "; use opaque PBR")
        for key in ("Volume", "Displacement"):
            if output.inputs[key].is_linked:
                raise ValueError(mat.name + ": apply geometry displacement before importing")
        if shader.inputs["Emission Color"].is_linked or (
            shader.inputs["Emission Strength"].default_value > 0
            and max(shader.inputs["Emission Color"].default_value[:3]) > 0.0001
        ):
            raise ValueError(mat.name + ": emissive materials are outside the opaque prop contract")
        for node in nodes:
            if node.type == "TEX_IMAGE" and (not node.image or node.image.size[0] == 0):
                raise ValueError(mat.name + ": missing source texture")
    return materials


def prepare(meshes, folder, config):
    scene = bpy.context.scene
    external = bool(scene.get("pts_external"))
    total = sum(triangle_count(o.data) for o in meshes)
    if total > 2000000:
        raise ValueError("Source exceeds two million triangles; simplify it before importing")
    report = {
        "triangles_before": total,
        "settings": config,
        "objects": {},
        "lods": [],
        "warnings": [],
        "error_metric": "two-sided sampled surface distance, per-object diagonal",
    }
    if external:
        compatible_materials(meshes)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / "original.blend"))
    report["normalization"] = normalize(meshes, config)
    low, high = bounds(meshes)
    scene["pts_preview_frame"] = json.dumps([low, high])
    if external:
        runpy.run_path(str(Path(__file__).with_name("blender_preview.py")))["render"](
            meshes, folder, views=[("before", (1.4, -2, 1.25))]
        )
    ratio = min(
        1.0,
        config["triangle_budget"]
        / max(1, total)
        * (0.96 if total > config["triangle_budget"] else 1),
    )
    original_meshes = {obj.name: obj.data for obj in meshes}
    for obj in meshes:
        report["objects"][obj.name] = reduce_object(obj, ratio, config["max_deviation_percent"])
    report["triangles_after"] = sum(triangle_count(o.data) for o in meshes)
    report["budget_passed"] = report["triangles_after"] <= config["triangle_budget"]
    (folder / "preparation.json").write_text(json.dumps(report))
    if not report["budget_passed"]:
        raise ValueError(
            "Cannot meet the triangle budget within the sampled shape-error limit. "
            "The source is retained; increase triangle_budget or max_deviation_percent."
        )
    if external:
        sources = {}
        try:
            for obj in meshes:
                source = obj.copy()
                source.data = original_meshes[obj.name]
                source.name = "PTS normal source " + obj.name
                source.hide_render = True
                bpy.context.scene.collection.objects.link(source)
                sources[obj.name] = source
            runpy.run_path(str(Path(__file__).with_name("blender_surfaces.py")))["bake"](
                meshes, folder, config["texture_size"], unwrap=False, normal_sources=sources
            )
            report["normal_bake"] = "source-to-reduced, paired-object tangent-space projection"
        finally:
            for source in sources.values():
                bpy.data.objects.remove(source, do_unlink=True)
    else:
        scene["pts_texture_size"] = config["texture_size"]
    # Preparation is complete in the saved source. Restoration must not normalize twice.
    scene["pts_preparation_report"] = json.dumps(report)
    scene["pts_prepared"] = True
    return report


def make_lods(meshes, config, report):
    levels = []
    collection = bpy.data.collections.get("PTS_LODs")
    if collection:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        collection = bpy.data.collections.new("PTS_LODs")
        bpy.context.scene.collection.children.link(collection)
    for ratio in config["lod_ratios"]:
        copies, checks = [], []
        for obj in meshes:
            clone = obj.copy()
            clone.data = obj.data.copy()
            clone.name = obj.name + "_LOD"
            collection.objects.link(clone)
            copies.append(clone)
            checks.append(reduce_object(clone, ratio, config["max_deviation_percent"]))
        count = sum(triangle_count(o.data) for o in copies)
        previous = levels[-1][1]["triangles"] if levels else report["triangles_after"]
        if count >= previous:
            report["warnings"].append(f"LOD ratio {ratio} skipped: no safe reduction")
            for obj in copies:
                bpy.data.objects.remove(obj, do_unlink=True)
            continue
        info = {
            "file": f"lod_{len(levels) + 1}.fbx",
            "ratio": ratio,
            "triangles": count,
            "screen_height": [0.5, 0.2, 0.08][len(levels)],
            "sampled_max_deviation_percent": max(
                c["sampled_max_deviation_percent"] for c in checks if c["accepted"]
            ),
            "kept_objects": sum(not c["accepted"] for c in checks),
        }
        levels.append((copies, info))
    report["lods"] = [info for _, info in levels]
    return levels
