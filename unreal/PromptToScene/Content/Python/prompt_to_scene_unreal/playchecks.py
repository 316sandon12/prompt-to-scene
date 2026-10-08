"""Bounded checks in a real PIE world; editor and runtime objects are kept separate."""

import json
import re
import shlex
import time
from pathlib import Path

import unreal

from . import actions, development
from .protocol import write_json

_state = None
_handle = None


def start(request, c, root):
    global _state, _handle
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if _state or levels.is_in_play_in_editor():
        raise ValueError("Finish the current Play session/check first")
    if not 1 <= c["duration"] <= 20 or len(c.get("asset_ids", [])) > 16:
        raise ValueError("Invalid play check")
    selected = []
    for name in c.get("asset_ids", []):
        found = actions.targets({"scope": "asset", "asset_id": name})
        if not found:
            raise ValueError("Interactive asset not loaded: " + name)
        selected.extend(found)
    plan = None
    if c.get("level_id"):
        path = root / "levels" / (c["level_id"] + ".json")
        plan = json.loads(path.read_text())
        if plan["scene"] != actions.scene():
            raise ValueError("Open the scene containing the generated level")
    logfile = None
    for arg in shlex.split(unreal.SystemLibrary.get_command_line()):
        if arg.lower().startswith("-abslog="):
            logfile = Path(arg.split("=", 1)[1])
    if logfile is None:
        logs = sorted(
            Path(unreal.Paths.project_log_dir()).glob("*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        logfile = logs[0] if logs else None
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    old_camera = editor.get_level_viewport_camera_info()
    old_selection = [actions.guid(a) for a in actions.actors().get_selected_level_actors()]
    camera = None
    if c.get("capture") and selected:
        actions.focus(selected)
        location, rotation = editor.get_level_viewport_camera_info()
        camera = actions.actors().spawn_actor_from_class(unreal.CameraActor, location, rotation)
        camera.tags = [unreal.Name("PTS.PlayCamera:" + request["request_id"])]
        camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
    _state = dict(
        request=request,
        command=c,
        root=root,
        stage="enter",
        started=time.monotonic(),
        checks=[],
        frames=[],
        plan=plan,
        camera=camera,
        old_camera=old_camera,
        selection=old_selection,
        log=logfile,
        log_offset=logfile.stat().st_size if logfile and logfile.is_file() else 0,
        screenshots=[],
        opened=[],
        last_frame=-1,
        last_real=None,
    )
    _handle = unreal.register_slate_post_tick_callback(tick)
    levels.editor_request_begin_play()
    return {
        "status": "queued",
        "development": {
            "command": "playcheck",
            "message": "Entering real PIE; poll the same request ID",
        },
    }


def assertion(name, check, passed, detail=""):
    _state["checks"].append(dict(asset_id=name, check=check, passed=bool(passed), detail=detail))


def screenshot(stage):
    s = _state
    suffix = "_before" if stage == "before" else ""
    path = s["root"] / "previews" / (s["request"]["request_id"] + suffix + ".png")
    path.parent.mkdir(exist_ok=True)
    s["screenshot_task"] = unreal.AutomationLibrary.take_high_res_screenshot(
        960, 640, str(path), delay=0.2
    )
    s["capture_path"] = path
    s["screenshots"].append("previews/" + path.name)
    s["stage"] = stage
    s["stage_start"] = time.monotonic()


def exercise(world):
    s = _state
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.StaticMeshActor)
    for name in s["command"].get("asset_ids", []):
        candidates = [a for a in actors if "PTS.Asset:" + name in map(str, a.tags)]
        assertion(name, "runtime_actor", bool(candidates))
        for actor in candidates:
            try:
                kind = actor.get_editor_property("TemplateKind")
                count = actor.get_editor_property("InteractionCount")
                distance = actor.get_editor_property("InteractionRange")
            except Exception:
                assertion(name, "runtime_template", False, "Configure interaction before testing")
                continue
            position = unreal.MathLibrary.transform_location(
                actor.get_actor_transform(), actor.get_editor_property("InteractionPoint")
            )
            actor.call_method("TryInteract", args=(position + unreal.Vector(distance * 3, 0, 0),))
            assertion(
                name, "range_rejection", actor.get_editor_property("InteractionCount") == count
            )
            pivot = actor.get_editor_property("MovingPivot")
            initial = tuple(
                getattr(pivot.get_editor_property("relative_rotation"), k)
                for k in ("roll", "pitch", "yaw")
            )
            moving_mesh = actor.get_editor_property("MovingMesh")
            center = unreal.SystemLibrary.get_component_bounds(moving_mesh)[0]
            before_center = (center.x, center.y, center.z)
            actor.call_method("TryInteract", args=(position,))
            assertion(
                name,
                "interaction_event",
                actor.get_editor_property("InteractionCount") == count + 1,
            )
            if kind == 2:
                assertion(
                    name,
                    "pickup_hidden",
                    actor.get_editor_property("Collected")
                    and actor.get_editor_property("hidden")
                    and not actor.get_actor_enable_collision(),
                )
            elif kind == 3:
                uses = actor.get_editor_property("UsesRequired")
                assertion(
                    name, "resource_progress", actor.get_editor_property("Collected") == (uses <= 1)
                )
                for _ in range(1, uses):
                    actor.call_method("TryInteract", args=(position,))
                assertion(
                    name,
                    "resource_depleted",
                    actor.get_editor_property("Collected")
                    and actor.get_editor_property("InteractionCount") == count + uses,
                )
                depleted = actor.get_editor_property("DepletedMesh")
                assertion(
                    name,
                    "depleted_visual",
                    actor.static_mesh_component.static_mesh == depleted
                    if depleted
                    else actor.get_editor_property("hidden"),
                )
                actor.call_method("TryInteract", args=(position,))
                assertion(
                    name,
                    "depletion_is_once",
                    actor.get_editor_property("InteractionCount") == count + uses,
                )
            elif kind == 4:
                assertion(name, "switch_on", actor.get_editor_property("Open"))
                actor.call_method("TryInteract", args=(position,))
                assertion(name, "switch_off", not actor.get_editor_property("Open"))
            else:
                after = pivot.get_editor_property("relative_rotation")
                moved = any(
                    abs(getattr(after, k) - initial[i]) > 1
                    for i, k in enumerate(("roll", "pitch", "yaw"))
                )
                center = unreal.SystemLibrary.get_component_bounds(moving_mesh)[0]
                after_center = (center.x, center.y, center.z)
                displaced = sum((a - b) ** 2 for a, b in zip(after_center, before_center)) > 0.01
                assertion(
                    name,
                    "opens_geometry",
                    actor.get_editor_property("Open") and moved and displaced,
                    f"rotation {initial} -> {after}; center {before_center} -> {after_center}",
                )
                s["opened"].append((name, actor, initial))
    if s["plan"]:
        # Ignore the default PIE player pawn; evaluate the level geometry, not its test observer.
        pawns = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Pawn)
        blockers = development.clearance(s["plan"], world, pawns)
        assertion(s["command"]["level_id"], "walk_clearance", not blockers, ", ".join(blockers))


def finish(status="completed", error=None):
    s = _state
    if s["stage"] == "exit":
        return
    if status == "completed":
        for name, actor, initial in s["opened"]:
            position = unreal.MathLibrary.transform_location(
                actor.get_actor_transform(), actor.get_editor_property("InteractionPoint")
            )
            actor.call_method("TryInteract", args=(position,))
            rotation = actor.get_editor_property("MovingPivot").get_editor_property(
                "relative_rotation"
            )
            assertion(
                name,
                "closes_again",
                not actor.get_editor_property("Open")
                and all(
                    abs(getattr(rotation, k) - initial[i]) < 0.1
                    for i, k in enumerate(("roll", "pitch", "yaw"))
                ),
            )
        assertion("scene", "runtime_frames", len(s["frames"]) >= 2)
    s["outcome"], s["error"], s["stage"] = status, error, "exit"
    s["stage_start"] = time.monotonic()
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()


def complete():
    global _state, _handle
    s = _state
    warnings = []
    if s["log"] and s["log"].is_file():
        with s["log"].open("rb") as stream:
            stream.seek(s["log_offset"])
            text = stream.read(2 * 1024 * 1024).decode("utf-8", "replace")
        failures = [
            line[-600:]
            for line in text.splitlines()
            if re.search(
                r"Log\w+: Error:|Blueprint Runtime Error|Accessed None trying to read", line
            )
        ]
        assertion("scene", "runtime_errors", not failures, "\n".join(failures[:20]))
    else:
        assertion("scene", "runtime_errors", False, "Engine log could not be read")
    if s["camera"]:
        actions.actors().destroy_actor(s["camera"])
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    editor.set_level_viewport_camera_info(*s["old_camera"])
    actions.actors().set_selected_level_actors(
        [a for a in actions.actors().get_all_level_actors() if actions.guid(a) in s["selection"]]
    )
    frames = sorted(s["frames"])
    result = dict(
        status=s["outcome"],
        request_id=s["request"]["request_id"],
        engine="unreal",
        development=dict(
            command="playcheck",
            passed=s["outcome"] == "completed" and all(c["passed"] for c in s["checks"]),
            checks=s["checks"],
            frames=len(frames),
            mean_frame_ms=sum(frames) / len(frames) if frames else 0,
            p95_frame_ms=frames[int((len(frames) - 1) * 0.95)] if frames else 0,
            screenshots=s["screenshots"],
            warnings=warnings,
            message="Actual PIE frame deltas on this machine; not a target-platform benchmark.",
        ),
    )
    if s.get("error"):
        result["error"] = s["error"]
    write_json(s["root"] / "action-receipts" / (s["request"]["request_id"] + ".json"), result)
    unreal.unregister_slate_post_tick_callback(_handle)
    _state = _handle = None


def tick(_delta):
    s = _state
    if not s:
        return
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    try:
        if s["stage"] == "exit":
            if not levels.is_in_play_in_editor():
                complete()
            elif time.monotonic() - s["stage_start"] > 20:
                # Keep requesting the native exit, never claim a restored editor early.
                levels.editor_request_end_play()
            return
        if (s["root"] / "cancel" / s["request"]["request_id"]).exists():
            finish("cancelled", "Play check cancelled")
            return
        if time.monotonic() - s["started"] > 90:
            finish("error", "Play check timed out")
            return
        if s["stage"] == "enter":
            if world:
                s["stage"], s["stage_start"] = "warmup", time.monotonic()
            return
        if not world:
            finish("error", "PIE ended before the check completed")
            return
        if s["stage"] == "warmup" and time.monotonic() - s["stage_start"] > 1:
            if s["command"].get("capture") and s["camera"]:
                screenshot("before")
            else:
                exercise(world)
                s["stage"], s["stage_start"] = "sample", time.monotonic()
        if s["stage"] in {"before", "after"}:
            if s["capture_path"].is_file() and s["capture_path"].stat().st_size > 8:
                if s["stage"] == "before":
                    exercise(world)
                    screenshot("after")
                else:
                    s["stage"], s["stage_start"] = "sample", time.monotonic()
            elif time.monotonic() - s["stage_start"] > 25:
                raise RuntimeError("PIE screenshot did not complete")
        if s["stage"] == "sample":
            frame = unreal.SystemLibrary.get_frame_count()
            real = unreal.GameplayStatics.get_real_time_seconds(world)
            if frame != s["last_frame"]:
                if s["last_real"] is not None and real > s["last_real"]:
                    s["frames"].append((real - s["last_real"]) * 1000)
                s["last_frame"], s["last_real"] = frame, real
            if time.monotonic() - s["stage_start"] >= s["command"]["duration"]:
                finish()
    except Exception as error:
        finish("error", str(error))
