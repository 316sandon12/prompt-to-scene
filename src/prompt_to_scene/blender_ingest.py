"""Read common static model formats inside Blender, preserving source material graphs."""

from pathlib import Path

import bpy
from mathutils import Matrix


def load(filename, clear=True):
    path = Path(filename)
    if clear:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
        for collection in list(bpy.data.collections):
            bpy.data.collections.remove(collection)
    existing = set(bpy.context.scene.objects)
    if path.suffix.lower() in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path), import_pack_images=True)
    elif path.suffix.lower() == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False)
    elif path.suffix.lower() == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            if clear and "Export" in source.collections:
                target.collections = ["Export"]
            else:
                target.objects = source.objects
        for collection in target.collections:
            bpy.context.scene.collection.children.link(collection)
        for obj in target.objects:
            if obj and not obj.users_collection:
                bpy.context.scene.collection.objects.link(obj)
    else:
        raise ValueError("Unsupported model format")
    original = [o for o in bpy.context.scene.objects if o not in existing]
    if any(obj.type == "ARMATURE" for obj in original):
        raise ValueError("This asset contains a rig; import a static mesh version")
    meshes = [obj for obj in original if obj.type == "MESH"]
    if not meshes:
        raise ValueError("No mesh geometry was found in the source")
    collection = bpy.data.collections.get("Export") or bpy.data.collections.new("Export")
    if collection.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(collection)
    graph = bpy.context.evaluated_depsgraph_get()
    for obj in meshes:
        if obj.animation_data or obj.data.shape_keys:
            raise ValueError("Animated or shape-key meshes need a static export first")
        ancestors, parent = [], obj.parent
        while parent:
            ancestors.insert(0, parent.name)
            parent = parent.parent
        obj["pts_source_path"] = "/".join(ancestors + [obj.name])
        matrix = obj.matrix_world.copy()
        evaluated = obj.evaluated_get(graph)
        obj.data = bpy.data.meshes.new_from_object(evaluated, depsgraph=graph)
        obj.modifiers.clear()
        obj.parent = None
        obj.data.transform(matrix)
        if matrix.determinant() < 0:
            obj.data.flip_normals()
        obj.matrix_world = Matrix.Identity(4)
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
        obj.hide_render = False
        obj.hide_set(False)
        obj["pts_part"] = obj.name
        if not obj.data.materials:
            mat = bpy.data.materials.new("ImportedSurface")
            mat.use_nodes = True
            obj.data.materials.append(mat)
    for obj in original:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
    # Isolate slots for baking: each object's bake target then belongs to one material.
    for obj in meshes:
        if len(obj.data.materials) > 1:
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="MATERIAL")
            bpy.ops.object.mode_set(mode="OBJECT")
    for obj in collection.all_objects:
        if obj.type != "MESH":
            continue
        indices = {p.material_index for p in obj.data.polygons}
        if len(indices) != 1:
            raise ValueError("Source has an empty or invalid material region")
        material = obj.data.materials[next(iter(indices))]
        if material is None:
            raise ValueError("A source material slot is empty")
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.material_index = 0
    bpy.context.scene["pts_external"] = True
    return [o for o in collection.all_objects if o.type == "MESH" and o not in existing]
