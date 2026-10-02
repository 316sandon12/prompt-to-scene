"""Owned scene look rigs, isolated native asset previews and local asset indexing."""

import hashlib
import json
import time

import unreal

from . import actions
from .development import vec
from .protocol import write_json

_pending = {}
_handle = None


def look_file(root):
    return root / "looks" / (hashlib.sha256(actions.scene().encode()).hexdigest()[:20] + ".json")


def owned():
    return [a for a in actions.actors().get_all_level_actors() if "PTS.Look" in map(str, a.tags)]


def spawn(cls, name, location=None):
    actor = actions.actors().spawn_actor_from_class(cls, location or unreal.Vector())
    actor.set_actor_label("PTS " + name)
    actor.tags = [unreal.Name("PTS.Look"), unreal.Name("PTS.Look:" + name)]
    actor.set_folder_path("PromptToScene/Presentation")
    return actor


def role(name, cls):
    return next((a for a in owned() if "PTS.Look:" + name in map(str, a.tags)), None) or spawn(
        cls, name
    )


def visible(actor, value):
    actor.set_is_temporarily_hidden_in_editor(not value)
    actor.set_actor_hidden_in_game(not value)
    component = actor.root_component
    if component:
        component.set_visibility(value, True)


def look(request, c, root):
    path = look_file(root)
    state = json.loads(path.read_text()) if path.is_file() else None
    result = {"development": {"command": "look", "preset": state["preset"] if state else "none"}}
    mode = c["mode"]
    if mode == "inspect":
        return result
    if mode == "restore":
        if state:
            by_id = {actions.guid(a): a for a in actions.actors().get_all_level_actors()}
            for row in state["previous"]:
                actor = by_id.get(row["id"])
                if actor:
                    actor.set_is_temporarily_hidden_in_editor(row["editor_hidden"])
                    actor.set_actor_hidden_in_game(row["game_hidden"])
                    if actor.root_component:
                        actor.root_component.set_visibility(row["visible"], True)
            for actor in owned():
                actions.actors().destroy_actor(actor)
            path.unlink()
        result["development"]["message"] = "Previous lighting restored"
        return result
    if mode == "capture":
        camera = next((a for a in owned() if isinstance(a, unreal.CameraActor)), None)
        if not camera:
            raise ValueError("Apply a scene look first")
        return capture(request, root, camera=camera)
    preset = c["preset"]
    if mode != "apply" or preset not in {"warm_cartoon", "cool_scifi", "moonlit", "neutral"}:
        raise ValueError("Unknown scene look")
    if not state:
        previous = []
        for actor in actions.actors().get_all_level_actors():
            if (
                isinstance(actor, (unreal.Light, unreal.SkyLight, unreal.SkyAtmosphere))
                and actor not in owned()
            ):
                previous.append(
                    dict(
                        id=actions.guid(actor),
                        editor_hidden=actor.is_temporarily_hidden_in_editor(),
                        game_hidden=actor.get_editor_property("hidden"),
                        visible=actor.root_component.get_editor_property("visible"),
                    )
                )
                visible(actor, False)
        state = dict(scene=actions.scene(), previous=previous)
    night, cool = preset == "moonlit", preset == "cool_scifi"
    key = role("Key", unreal.DirectionalLight)
    key.set_actor_rotation(unreal.Rotator(pitch=-25 if night else -45, yaw=145), False)
    component = key.light_component
    component.set_mobility(unreal.ComponentMobility.MOVABLE)
    component.set_editor_property("intensity", 0.8 if night else 5.0)
    component.set_light_color(
        unreal.LinearColor(
            *(
                (0.47, 0.6, 1)
                if night
                else (0.64, 0.85, 1)
                if cool
                else (1, 0.82, 0.61)
                if preset != "neutral"
                else (1, 1, 1)
            )
        )
    )
    component.set_editor_property("atmosphere_sun_light", True)
    fill = role("Fill", unreal.DirectionalLight)
    fill.set_actor_rotation(unreal.Rotator(pitch=-30, yaw=-35), False)
    fill.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    fill.light_component.set_editor_property("intensity", 0.15 if night else 1.2)
    fill.light_component.set_editor_property("cast_shadows", False)
    fill.light_component.set_light_color(unreal.LinearColor(0.55, 0.72, 1))
    role("Sky", unreal.SkyAtmosphere)
    post = role("Post", unreal.PostProcessVolume)
    post.set_editor_property("unbound", True)
    post.set_editor_property("priority", 1000)
    settings = post.get_editor_property("settings")
    settings.set_editor_property("override_auto_exposure_method", True)
    settings.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    settings.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    settings.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    for name, value in dict(
        auto_exposure_bias=-0.25 if night else 0.0,
        bloom_intensity=0.15,
        vignette_intensity=0.15,
        scene_color_tint=unreal.LinearColor(0.88, 0.95, 1)
        if cool or night
        else unreal.LinearColor(1, 0.97, 0.92),
    ).items():
        settings.set_editor_property("override_" + name, True)
        settings.set_editor_property(name, value)
    post.set_editor_property("settings", settings)
    camera = next((a for a in owned() if isinstance(a, unreal.CameraActor)), None)
    if not camera:
        camera = role("Camera", unreal.CameraActor)
        position = vec(c["position"])
        camera.set_actor_location(position + unreal.Vector(400, -500, 300), False, False)
        camera.set_actor_rotation(
            unreal.MathLibrary.find_look_at_rotation(
                camera.get_actor_location(), position + unreal.Vector(0, 0, 100)
            ),
            False,
        )
        camera.camera_component.set_editor_property("field_of_view", 45)
        camera.camera_component.set_editor_property("post_process_blend_weight", 0)
    state["preset"] = preset
    write_json(path, state)
    result["development"].update(
        preset=preset,
        changed=1,
        message="Owned lighting, atmosphere, post-process and fixed presentation camera applied",
    )
    return result


def index():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = [
        row
        for row in registry.get_assets_by_path("/Game", recursive=True)
        if str(row.asset_class_path.asset_name) in {"StaticMesh", "Blueprint"}
    ]
    entries = []
    for row in sorted(assets, key=lambda a: str(a.package_name))[:2000]:
        path = str(row.package_name)
        obj = row.get_asset()
        if isinstance(obj, unreal.Blueprint):
            cls = unreal.load_class(None, path + "." + str(row.asset_name) + "_C")
            default = unreal.get_default_object(cls) if cls else None
            if not isinstance(default, unreal.StaticMeshActor):
                continue
            mesh = default.static_mesh_component.static_mesh
        else:
            mesh = obj
        if not isinstance(mesh, unreal.StaticMesh):
            continue
        extent = mesh.get_bounds().box_extent
        entries.append(
            dict(
                path=path,
                name=str(row.asset_name),
                kind="blueprint" if isinstance(obj, unreal.Blueprint) else "mesh",
                size=[extent.x / 50, extent.y / 50, extent.z / 50],
                triangles=mesh.get_num_triangles(0),
                asset_id=unreal.EditorAssetLibrary.get_metadata_tag(mesh, "PromptToScene.AssetId"),
                tags=json.loads(
                    unreal.EditorAssetLibrary.get_metadata_tag(mesh, "PromptToScene.SlotNames")
                    or "[]"
                ),
            )
        )
    return {"development": dict(command="library", entries=entries, truncated=len(assets) > 2000)}


def library(request, c, root):
    if c["mode"] == "index":
        return index()
    path = c["path"]
    if not path.startswith("/Game/") or ".." in path:
        raise ValueError("Choose a project asset inside /Game/")
    obj = unreal.load_asset(path)
    if not isinstance(obj, (unreal.StaticMesh, unreal.Blueprint)):
        raise ValueError("Choose a mesh or static actor Blueprint")
    if c["mode"] not in {"place", "preview"}:
        raise ValueError("Choose index, place or preview")
    old_selection = actions.actors().get_selected_level_actors()
    position = (
        vec(c["position"]) if c["mode"] == "place" else unreal.Vector(1000000, 1000000, 1000000)
    )
    if isinstance(obj, unreal.Blueprint):
        cls = unreal.load_class(None, path + "." + path.rsplit("/", 1)[-1] + "_C")
        if not isinstance(unreal.get_default_object(cls), unreal.StaticMeshActor):
            raise ValueError("Only static actor Blueprints are indexed")
        actor = actions.actors().spawn_actor_from_class(cls, position)
    else:
        actor = actions.actors().spawn_actor_from_object(obj, position)
    if c["mode"] == "preview":
        return capture(request, root, preview_actor=actor, old_selection=old_selection)
    actions.actors().set_selected_level_actors([actor])
    return {"development": dict(command="library", changed=1, path=path)}


def capture(request, root, camera=None, preview_actor=None, old_selection=None):
    global _handle
    if _pending or actions._captures:
        if preview_actor:
            actions.actors().destroy_actor(preview_actor)
        raise ValueError(
            "Another viewport capture is running; wait for it before requesting this one"
        )
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    old_camera = editor.get_level_viewport_camera_info()
    old_selection = (
        old_selection if old_selection is not None else actions.actors().get_selected_level_actors()
    )
    if camera:
        editor.set_level_viewport_camera_info(
            camera.get_actor_location(), camera.get_actor_rotation()
        )
    else:
        actions.focus([preview_actor])
    path = root / "previews" / (request["request_id"] + ".png")
    path.parent.mkdir(exist_ok=True)
    task = unreal.AutomationLibrary.take_high_res_screenshot(960, 640, str(path), delay=0.5)
    _pending[request["request_id"]] = dict(
        root=root,
        path=path,
        started=time.monotonic(),
        task=task,
        old_camera=old_camera,
        selection=old_selection,
        actor=preview_actor,
    )
    if _handle is None:
        _handle = unreal.register_slate_post_tick_callback(tick)
    write_json(
        root / "action-receipts" / (request["request_id"] + ".json"),
        dict(status="queued", engine="unreal", request_id=request["request_id"]),
    )
    return None


def tick(_delta):
    global _handle
    for revision, state in list(_pending.items()):
        ready = state["path"].is_file() and state["path"].stat().st_size > 8
        timed_out = time.monotonic() - state["started"] > 30
        cancelled = (state["root"] / "cancel" / revision).exists()
        if not (ready or timed_out or cancelled):
            continue
        receipt = dict(
            request_id=revision,
            engine="unreal",
            status="cancelled" if cancelled else "completed" if ready else "error",
        )
        if ready:
            receipt["preview"] = "previews/" + state["path"].name
        else:
            receipt["error"] = "Native capture cancelled or timed out"
        if state["actor"]:
            actions.actors().destroy_actor(state["actor"])
        actions.actors().set_selected_level_actors(state["selection"])
        unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
            *state["old_camera"]
        )
        write_json(state["root"] / "action-receipts" / (revision + ".json"), receipt)
        del _pending[revision]
    if not _pending and _handle is not None:
        unreal.unregister_slate_post_tick_callback(_handle)
        _handle = None


def execute(request, c, root):
    return look(request, c, root) if c["command"] == "look" else library(request, c, root)
