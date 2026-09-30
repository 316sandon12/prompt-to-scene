"""Actual source-geometry studio views; never presented as engine screenshots."""

import bpy
from mathutils import Vector


def render(meshes, folder):
    points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector([min(v[i] for v in points) for i in range(3)])
    high = Vector([max(v[i] for v in points) for i in range(3)])
    center = (low + high) / 2
    size = max((high - low).length, 0.1)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 12
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.world.use_nodes = True
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value = (
        0.16,
        0.18,
        0.22,
        1,
    )
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.5
    created = []
    for offset, power, width in (((-2, -3, 4), 550, 3), ((3, -1, 2), 250, 3), ((0, 3, 3), 400, 2)):
        light = bpy.data.lights.new("PTS studio softbox", "AREA")
        light.energy = power * size * size
        light.size = width * size
        obj = bpy.data.objects.new("PTS studio softbox", light)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(offset) * size
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
        created.append(obj)
    bpy.ops.mesh.primitive_plane_add(size=size * 200, location=(center.x, center.y, low.z - 0.004))
    floor = bpy.context.object
    material = bpy.data.materials.new("PTS studio floor")
    material.diffuse_color = (0.11, 0.13, 0.16, 1)
    floor.data.materials.append(material)
    created.append(floor)
    data = bpy.data.cameras.new("PTS studio camera")
    camera = bpy.data.objects.new("PTS studio camera", data)
    scene.collection.objects.link(camera)
    created.append(camera)
    scene.camera = camera
    data.type = "ORTHO"
    data.ortho_scale = size * 1.2
    names = []
    try:
        for name, direction in (
            ("studio", (1.4, -2, 1.25)),
            ("front", (0, -3, 0.45)),
            ("back", (-1.5, 2, 1.1)),
        ):
            camera.location = center + Vector(direction) * size
            camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = str(folder / (name + ".png"))
            bpy.ops.render.render(write_still=True)
            names.append(name + ".png")
    finally:
        for obj in created:
            bpy.data.objects.remove(obj, do_unlink=True)
        scene.camera = None
    return names
