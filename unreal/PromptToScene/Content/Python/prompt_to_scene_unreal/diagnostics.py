"""Editor measurements and collision-surface placement; all public units are metres."""

import math

import unreal


def oriented(actor):
    mesh = actor.static_mesh_component.static_mesh
    if not mesh:
        return {}
    bounds = mesh.get_bounds()
    transform = actor.static_mesh_component.get_world_transform()
    position = actor.get_actor_location()
    angle = math.radians(actor.get_actor_rotation().yaw)
    c, s = math.cos(angle), math.sin(angle)
    points = []
    for n in range(8):
        corner = unreal.Vector(
            *(
                getattr(bounds.origin, k)
                + getattr(bounds.box_extent, k) * (1 if n & (1 << i) else -1)
                for i, k in enumerate(("x", "y", "z"))
            )
        )
        p = unreal.MathLibrary.transform_location(transform, corner) - position
        points.append([(c * p.x + s * p.y) / 100, (-s * p.x + c * p.y) / 100, p.z / 100])
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    footprint = []
    for x, y in ((low[0], low[1]), (high[0], low[1]), (high[0], high[1]), (low[0], high[1])):
        footprint.extend([position.x / 100 + c * x - s * y, position.y / 100 + s * x + c * y])
    return {"oriented_min": low, "oriented_max": high, "footprint": footprint}


def support(actor):
    center, extent = actor.get_actor_bounds(False)
    bottom = center.z - extent.z
    # Begin just above the bottom so an overhead shelf is not mistaken for the floor.
    start = unreal.Vector(center.x, center.y, bottom + 50)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    result = unreal.SystemLibrary.line_trace_single(
        world,
        start,
        start - unreal.Vector(0, 0, 1000000),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
        False,
        [actor],
        unreal.DrawDebugTrace.NONE,
        True,
    )
    if result:
        hit = result.to_tuple()
        if hit[0] and hit[7].z > 0.7:
            return (bottom - hit[5].z) / 100
    return None


def ground(actor, required=True):
    gap = support(actor)
    if gap is None:
        if required:
            raise ValueError("No collision surface was detected beneath " + actor.get_actor_label())
        return
    actor.modify()
    actor.set_actor_location(
        actor.get_actor_location() - unreal.Vector(0, 0, gap * 100), False, False
    )


def textures_used(material):
    library = unreal.MaterialEditingLibrary
    if hasattr(library, "get_material_used_textures"):
        return list(library.get_material_used_textures(material))
    textures = []
    if isinstance(material, unreal.MaterialInstanceConstant):
        textures += [
            library.get_material_instance_texture_parameter_value(material, n)
            for n in library.get_texture_parameter_names(material)
        ]
        material = material.get_editor_property("parent")
    while isinstance(material, unreal.MaterialInstanceConstant):
        material = material.get_editor_property("parent")
    if isinstance(material, unreal.Material):
        textures += list(library.get_used_textures(material))
    return [t for t in textures if isinstance(t, unreal.Texture2D)]


def inspect(actor):
    from . import actions, layout

    mesh = actor.static_mesh_component.static_mesh
    if not mesh:
        raise ValueError("Selected actor has no static mesh")
    component = actor.static_mesh_component
    materials = [component.get_material(i) for i in range(component.get_num_materials())]
    textures = {t.get_path_name(): t for m in materials if m for t in textures_used(m)}
    levels = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    gap = support(actor)
    state = actions.describe(actor)
    return {
        "id": state["id"],
        "asset_id": state["asset_id"],
        "mesh_key": mesh.get_path_name(),
        "triangles": mesh.get_num_triangles(0),
        "vertices": mesh.get_num_vertices(0),
        "material_slots": len(materials),
        "missing_materials": sum(m is None for m in materials),
        "texture_count": len(textures),
        "texture_bytes_estimate": sum(
            int(t.blueprint_get_size_x() * t.blueprint_get_size_y() * 4 * 4 / 3)
            for t in textures.values()
        ),
        "lod_triangles": [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
        "lod_vertices": [mesh.get_num_vertices(i) for i in range(mesh.get_num_lods())],
        "lod_screen_heights": list(levels.get_lod_screen_sizes(mesh)),
        "support_known": gap is not None,
        "support_gap": gap or 0,
        "overlap_candidates": [
            actions.guid(a)
            for a in layout.context()
            if a != actor and layout.overlap(state, actions.describe(a))
        ],
    }
