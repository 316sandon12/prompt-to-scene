"""Blender-only local edits on named imported regions; originals stay recoverable."""

import hashlib
import json
import math
import runpy
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector


def apply(payload):
    scene = bpy.context.scene
    collection = bpy.data.collections["Export"]
    meshes = [o for o in collection.all_objects if o.type == "MESH"]
    helper = runpy.run_path(str(Path(__file__).with_name("blender_prepare.py")))
    if payload.get("normalize"):
        helper["normalize"](meshes, payload["normalize"])
    part, changes = payload["part"], payload["changes"]
    members = payload.get("members") or [part]
    locks = json.loads(scene.get("pts_part_locks", "{}")) or json.loads(
        scene.get("pts_recipe", "{}")
    ).get("locks", {})
    geometry = bool(set(changes) & {"scale", "offset", "rotation"} or payload.get("replacement"))
    material = bool(set(changes) & {"color", "roughness", "metallic"})
    for member in members:
        lock = locks.get(member, {})
        if geometry and lock.get("geometry") and payload.get("lock_geometry") is not False:
            raise ValueError(member + ": geometry is locked")
        if material and lock.get("material") and payload.get("lock_material") is not False:
            raise ValueError(member + ": material is locked")
    selected = [o for o in meshes if o.get("pts_part", o.name) in members]
    if not selected:
        raise ValueError("The chosen parts no longer exist")
    low, high = helper["bounds"](selected)
    center = Vector([(a + b) / 2 for a, b in zip(low, high)])
    replacement = payload.get("replacement")
    if replacement:
        path = Path(replacement["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != replacement["sha256"]:
            raise ValueError("Replacement model changed after submission")
        fresh = runpy.run_path(str(Path(__file__).with_name("blender_ingest.py")))["load"](
            str(path), clear=False
        )
        nlow, nhigh = helper["bounds"](fresh)
        ncenter = Vector([(a + b) / 2 for a, b in zip(nlow, nhigh)])
        factor = max(b - a for a, b in zip(low, high)) / max(b - a for a, b in zip(nlow, nhigh))
        for obj in fresh:
            for vertex in obj.data.vertices:
                vertex.co = (vertex.co - ncenter) * factor + center
        for obj in selected:
            bpy.data.objects.remove(obj, do_unlink=True)
        selected = fresh
    transform = Euler(
        tuple(math.radians(v) for v in changes.get("rotation", [0, 0, 0])), "XYZ"
    ).to_matrix().to_4x4() @ Matrix.Diagonal((*changes.get("scale", [1, 1, 1]), 1))
    offset = Vector(changes.get("offset", [0, 0, 0]))
    copied = {}
    for obj in selected:
        obj["pts_part"] = part
        if geometry:
            for vertex in obj.data.vertices:
                vertex.co = transform @ (vertex.co - center) + center + offset
            obj.data.update()
        if material:
            for slot in obj.material_slots:
                old = slot.material
                if old.name not in copied:
                    old_name = old.name
                    mat = old.copy()
                    target_name = (
                        old.name.split("__part_")[0]
                        + "__part_"
                        + hashlib.sha256(part.encode()).hexdigest()[:8]
                    )
                    if old.name == target_name:
                        old.name = target_name + "_previous"
                    mat.name = target_name
                    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                    for field, socket_name in (
                        ("color", "Base Color"),
                        ("roughness", "Roughness"),
                        ("metallic", "Metallic"),
                    ):
                        if field not in changes:
                            continue
                        socket = shader.inputs[socket_name]
                        if field == "color" and socket.is_linked:
                            mix = mat.node_tree.nodes.new("ShaderNodeMixRGB")
                            mix.blend_type = "MULTIPLY"
                            mix.inputs[0].default_value = 1
                            mat.node_tree.links.new(socket.links[0].from_socket, mix.inputs[1])
                            mix.inputs[2].default_value = (*changes[field], 1)
                            mat.node_tree.links.new(mix.outputs[0], socket)
                        else:
                            for link in list(socket.links):
                                mat.node_tree.links.remove(link)
                            socket.default_value = (
                                (*changes[field], 1) if field == "color" else changes[field]
                            )
                    copied[old_name] = mat
                    copied[old.name] = mat
                slot.material = copied[old.name]
    merged = {
        field: any(locks.get(member, {}).get(field, False) for member in members)
        for field in ("geometry", "material")
    }
    for field in ("geometry", "material"):
        if payload.get("lock_" + field) is not None:
            merged[field] = payload["lock_" + field]
    locks[part] = merged
    scene["pts_part_locks"] = json.dumps(locks)
    scene["pts_preserve_ratios"] = json.dumps(payload.get("preserve_ratios", {}))
    scene["pts_recipe"] = "{}"
    scene["pts_external"] = True
    scene["pts_bake_needed"] = False
