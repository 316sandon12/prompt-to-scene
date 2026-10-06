"""Editor adapter for portable gameplay and level contracts. Runtime is ordinary Blueprint."""

import json
import math
import re

import unreal

from . import actions, locations, protection
from .protocol import write_json


def vec(values, scale=100):
    if len(values) != 3 or any(not math.isfinite(v) for v in values):
        raise ValueError("Expected three finite coordinates")
    return unreal.Vector(*(v * scale for v in values))


def execute(request, root):
    c = json.loads(request.get("development_json", "{}"))
    command = c.get("command")
    if command == "interaction":
        data = interaction(request["asset_id"], c)
    elif command in {"protection", "update_review"}:
        data = protection.execute(request, c)
    elif command == "level":
        data = level(c, root)
    elif command in {"look", "library"}:
        from . import presentation

        return presentation.execute(request, c, root)
    elif command == "playcheck":
        from . import playchecks

        return playchecks.start(request, c, root)
    elif command == "organize":
        from . import organization

        return organization.execute(request, c, root)
    elif command == "adapt":
        from . import adaptation

        return adaptation.execute(request, c, root)
    else:
        raise ValueError("Unknown development command")
    return {"development": data, "scene": actions.scene()}


def interaction(asset_id, c):
    kind = c["template"]
    if (
        kind not in {"door", "chest", "pickup"}
        or not 0.1 <= c["distance"] <= 20
        or abs(c["angle"]) > 170
    ):
        raise ValueError("Invalid interaction settings")
    base = protection.mesh_for(asset_id)
    moving = protection.mesh_for(c["moving_asset_id"]) if kind != "pickup" else None
    template = unreal.load_class(
        None, "/PromptToScene/Templates/BP_PTSInteraction.BP_PTSInteraction_C"
    )
    if not template:
        raise RuntimeError("Interaction Blueprint template missing. Install the current UE bridge.")
    path = locations.asset(asset_id, "blueprint")
    bp = unreal.load_asset(path) if unreal.EditorAssetLibrary.does_asset_exist(path) else None
    keep = bool(bp and c.get("preserve_configuration"))
    if not bp:
        bp = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(path, template)
    if not bp:
        raise RuntimeError("Could not create the asset Blueprint")
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    cls = unreal.load_class(None, path + "." + path.rsplit("/", 1)[-1] + "_C")
    defaults = unreal.get_default_object(cls)
    default_tags = [
        str(t)
        for t in defaults.tags
        if not str(t).startswith(("PTS.Asset:", "PTS.Interaction:", "PTS.Part:"))
    ]
    default_tags += ["PTS.Asset:" + asset_id, "PTS.Interaction:" + kind]
    if moving:
        default_tags.append("PTS.Part:" + c["moving_asset_id"])
    defaults.set_editor_property("tags", [unreal.Name(t) for t in default_tags])
    defaults.set_editor_property("TemplateKind", {"door": 0, "chest": 1, "pickup": 2}[kind])
    rotation = (
        unreal.Rotator(pitch=c["angle"]) if kind == "chest" else unreal.Rotator(yaw=c["angle"])
    )
    if not keep:
        defaults.set_editor_property("InteractionRange", c["distance"] * 100)
        defaults.set_editor_property("OpenRotation", rotation)
        defaults.set_editor_property(
            "auto_receive_input",
            unreal.AutoReceiveInput.PLAYER0
            if c["demo_input"]
            else unreal.AutoReceiveInput.DISABLED,
        )
    defaults.static_mesh_component.set_static_mesh(base)
    # Editable inherited component templates make the Blueprint reusable from the content browser.
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    library = unreal.SubobjectDataBlueprintFunctionLibrary
    for handle in subsystem.k2_gather_subobject_data_for_blueprint(bp):
        data = library.get_data(handle)
        component = library.get_object_for_blueprint(data, bp)
        if not isinstance(component, unreal.SceneComponent):
            continue
        name = str(library.get_variable_name(data))
        if name == "MovingPivot":
            component.set_editor_property("relative_location", vec(c["pivot"]))
            component.set_editor_property("relative_rotation", unreal.Rotator())
        if name == "MovingMesh":
            component.set_static_mesh(moving)
            component.set_editor_property("relative_location", vec(c["offset"]))
            component.set_collision_profile_name("BlockAll")
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    unreal.EditorAssetLibrary.save_loaded_asset(bp, only_if_is_dirty=False)
    cls = unreal.load_class(None, path + "." + path.rsplit("/", 1)[-1] + "_C")
    targets = actions.targets({"scope": "asset", "asset_id": asset_id})
    converted = []
    with unreal.ScopedEditorTransaction("Prompt-to-Scene: interaction"):
        for actor in targets:
            if actor.get_class() != cls:
                if actor.get_class() != unreal.StaticMeshActor.static_class():
                    raise ValueError(
                        "Attach a template to a plain managed StaticMeshActor; "
                        "keep custom Blueprint actors intact"
                    )
                replacement = actions.actors().spawn_actor_from_class(
                    cls, actor.get_actor_location(), actor.get_actor_rotation()
                )
                replacement.set_actor_scale3d(actor.get_actor_scale3d())
                replacement.set_actor_label(actor.get_actor_label())
                replacement.tags = actor.tags
                replacement.static_mesh_component.set_editor_property(
                    "override_materials",
                    actor.static_mesh_component.get_editor_property("override_materials"),
                )
                for child in actor.get_attached_actors():
                    child.attach_to_actor(
                        replacement,
                        "",
                        unreal.AttachmentRule.KEEP_WORLD,
                        unreal.AttachmentRule.KEEP_WORLD,
                        unreal.AttachmentRule.KEEP_WORLD,
                        False,
                    )
                actions.actors().destroy_actor(actor)
                actor = replacement
            actor.set_editor_property("TemplateKind", {"door": 0, "chest": 1, "pickup": 2}[kind])
            if not keep:
                actor.set_editor_property("InteractionRange", c["distance"] * 100)
                actor.set_editor_property("OpenRotation", rotation)
                actor.set_editor_property(
                    "auto_receive_input",
                    unreal.AutoReceiveInput.PLAYER0
                    if c["demo_input"]
                    else unreal.AutoReceiveInput.DISABLED,
                )
            actor.static_mesh_component.set_static_mesh(base)
            actor.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            actor.get_editor_property("MovingPivot").set_editor_property(
                "relative_location", vec(c["pivot"])
            )
            component = actor.get_editor_property("MovingMesh")
            component.set_static_mesh(moving)
            component.set_editor_property("relative_location", vec(c["offset"]))
            component.set_collision_profile_name("BlockAll")
            tags = [
                str(t)
                for t in actor.tags
                if not str(t).startswith(("PTS.Interaction:", "PTS.Part:"))
            ]
            tags += ["PTS.Interaction:" + kind]
            if moving:
                tags.append("PTS.Part:" + c["moving_asset_id"])
            actor.tags = [unreal.Name(t) for t in tags]
            converted.append(actor)
        if moving:
            for actor in actions.targets({"scope": "asset", "asset_id": c["moving_asset_id"]}):
                actions.actors().destroy_actor(actor)
        actions.actors().set_selected_level_actors(converted)
    for mesh in [base, *([moving] if moving else [])]:
        enable_collision(mesh)
    return dict(
        command="interaction",
        template=kind,
        prefab=path,
        changed=len(converted),
        message=(
            "Native Blueprint: TryInteract(WorldPosition in cm), Interact and OnInteracted. "
            "Demo input: aim and press E."
        ),
    )


def enable_collision(mesh):
    body = mesh.get_editor_property("body_setup")
    body.set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    )
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for section in range(mesh.get_num_sections(0)):
        editor.enable_section_collision(mesh, True, 0, section)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)


def clearance(plan, world=None, ignore=None):
    world = world or unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    radius, height = plan["player_radius"] * 100, plan["player_height"] * 100
    blockers = []
    for row in plan["checkpoints"]:
        foot = vec(row["position"])
        p = foot + unreal.Vector(0, 0, height / 2)
        excluded = list(ignore or [])
        for _ in range(32):
            hit = unreal.SystemLibrary.capsule_trace_single(
                world,
                p,
                p + unreal.Vector(0, 0, 0.1),
                radius,
                height / 2,
                unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                False,
                excluded,
                unreal.DrawDebugTrace.NONE,
                True,
            )
            if not hit or not hit.to_tuple()[0]:
                break
            data = hit.to_tuple()
            actor = data[9]
            if actor:
                center, extent = actor.get_actor_bounds(True)
                if center.z + extent.z <= foot.z + plan.get("max_step", 0.22) * 100 + 0.5:
                    excluded.append(actor)
                    continue
            name = actor.get_name() if actor else "blocking geometry"
            if name not in blockers:
                blockers.append(name)
            break
        if len(blockers) >= 20:
            break
    return blockers


def level(c, root):
    name = c["level_id"]
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise ValueError("Invalid level ID")
    tag = "PTS.Level:" + name
    existing = [a for a in actions.actors().get_all_level_actors() if tag in map(str, a.tags)]
    path = root / "levels" / (name + ".json")
    if c["mode"] == "check":
        plan = json.loads(path.read_text())
        if plan["scene"] != actions.scene() or not existing:
            raise ValueError("Load the scene containing this generated level")
        blockers = clearance(plan)
        return dict(
            command="level",
            level_id=name,
            passed=not blockers,
            conflicts=blockers,
            samples=len(plan["checkpoints"]),
            module_count=plan["module_count"],
        )
    if c["mode"] == "remove":
        for actor in existing:
            actions.actors().destroy_actor(actor)
        path.unlink(missing_ok=True)
        return dict(command="level", changed=len(existing))
    if c["mode"] != "build" or len(c["boxes"]) > 1000 or len(c["checkpoints"]) > 2000:
        raise ValueError("Invalid level plan")
    mesh = unreal.load_asset("/Engine/BasicShapes/Cube.Cube")
    created = []
    try:
        with unreal.ScopedEditorTransaction("Prompt-to-Scene: build modular level"):
            for row in c["boxes"]:
                if any(v <= 0 for v in row["size"]):
                    raise ValueError("Invalid block size")
                actor = actions.actors().spawn_actor_from_object(
                    mesh, vec(row["position"]), unreal.Rotator(yaw=row["yaw"])
                )
                actor.set_actor_scale3d(vec(row["size"], 1))
                actor.set_actor_label(name + "_" + row["name"])
                actor.tags = [unreal.Name(tag)]
                actor.set_folder_path("PromptToScene/Levels/" + name)
                actor.static_mesh_component.set_material(0, level_material(row["material"]))
                created.append(actor)
            blockers = clearance(c, ignore=existing)
            if blockers:
                raise ValueError("Walk clearance blocked by: " + ", ".join(blockers))
            for actor in existing:
                actions.actors().destroy_actor(actor)
        write_json(path, {**c, "scene": actions.scene()})
        return dict(
            command="level",
            level_id=name,
            changed=len(created),
            passed=True,
            samples=len(c["checkpoints"]),
            module_count=c["module_count"],
        )
    except Exception:
        for actor in created:
            actions.actors().destroy_actor(actor)
        raise


def level_material(name):
    colors = {"floor": (0.3, 0.25, 0.20), "wall": (0.73, 0.69, 0.58), "trim": (0.24, 0.38, 0.4)}
    if name not in colors:
        raise ValueError("Unknown block material")
    path = "/Game/PromptToScene/LevelMaterials/M_" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        "M_" + name,
        "/Game/PromptToScene/LevelMaterials",
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -250, 0
    )
    expression.set_editor_property("constant", unreal.LinearColor(*colors[name], 1))
    unreal.MaterialEditingLibrary.connect_material_property(
        expression, "", unreal.MaterialProperty.MP_BASE_COLOR
    )
    rough = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -250, 150
    )
    rough.set_editor_property("r", 0.65)
    unreal.MaterialEditingLibrary.connect_material_property(
        rough, "", unreal.MaterialProperty.MP_ROUGHNESS
    )
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    return material
