"""Exercise generated UMG and item Blueprints in PIE without the maintainer C++ plugin."""

import json
import os
import time
import traceback
from pathlib import Path

from prompt_to_scene_unreal import import_pending
from prompt_to_scene_unreal.game_creations import generated, widgets

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels.new_level("/Game/Creations_" + str(int(time.time())))
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "creation-ready").write_text("ready")
suffix = os.environ.get("PTS_CREATION_UI_SUFFIX", "")
retained = None
play_at = None
capture_at = None


def row(kind, name):
    return json.loads((root / kind / (name + ".json")).read_text())


def play():
    global capture_at
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    assert world
    items = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)

    def host(name):
        return next(a for a in items if "PTS.Screen:" + name + suffix in map(str, a.tags))

    inv_host = host("inventory")
    inv_host.call_method("Show")
    inv = inv_host.get_editor_property("WidgetRef")
    assert inv and inv.is_in_viewport()
    inv.call_method("SelectItem", args=(0,))
    assert str(inv.get_editor_property("DetailName").get_text()) == "Forest remedy"
    assert inv.get_editor_property("DetailIcon").get_editor_property(
        "brush"
    ).resource_object == inv.get_editor_property("Item0").get_editor_property("Icon")
    pickup = next(a for a in items if "PTS.Item:forest_potion" in map(str, a.tags))
    assert pickup.get_editor_property("ItemData") == inv.get_editor_property("Item0")
    pickup.call_method("Interact")
    assert pickup.get_editor_property("Collected") and pickup.get_editor_property("hidden")
    hud = host("hud").get_editor_property("WidgetRef")
    assert hud and hud.is_in_viewport()
    skill_box = hud.get_editor_property("Icon0").get_parent()
    assert skill_box.get_editor_property("width_override") == 48
    assert skill_box.get_editor_property("height_override") == 48
    hud.call_method("SetHealth", args=(0.4,))
    assert abs(hud.get_editor_property("Health").get_editor_property("percent") - 0.4) < 0.001
    hud.call_method(
        "SetSkillIcon", args=(0, inv.get_editor_property("Item0").get_editor_property("Icon"))
    )
    assert hud.get_editor_property("Icon0").get_editor_property(
        "brush"
    ).resource_object == inv.get_editor_property("Item0").get_editor_property("Icon")
    pause_host = host("pause")
    pause_host.call_method("Show")
    assert unreal.GameplayStatics.is_game_paused(world)
    pause = pause_host.get_editor_property("WidgetRef")
    pause.call_method("OnSettings")
    pause.call_method("Resume")
    assert not unreal.GameplayStatics.is_game_paused(world) and not pause.is_in_viewport()
    (root / "creation-play-passed").write_text("inventory details, pickup data, HUD, pause, hooks")
    host("hud").call_method("Hide")
    capture_at = time.monotonic()


def tick(_delta):
    global retained, play_at, capture_at
    try:
        if capture_at:
            if capture_at > 0 and time.monotonic() > capture_at + 0.8:
                world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
                inv_host = next(
                    actor
                    for actor in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
                    if "PTS.Screen:inventory" + suffix in map(str, actor.tags)
                )
                inv = inv_host.get_editor_property("WidgetRef")
                detail_box = inv.get_editor_property("DetailIcon").get_parent()
                assert detail_box.get_editor_property("width_override") == 200
                assert detail_box.get_editor_property("height_override") == 200
                unreal.SystemLibrary.execute_console_command(
                    world, "Shot showui filename=" + str(root / "inventory-ue.png")
                )
                capture_at = -time.monotonic()
            elif capture_at < 0 and time.monotonic() > -capture_at + 2:
                levels.editor_request_end_play()
                capture_at = None
                (root / "creation-command-done").write_text("done")
            return
        if play_at:
            if levels.is_in_play_in_editor() and time.monotonic() > play_at + 2:
                play()
                play_at = None
            return
        if levels.is_in_play_in_editor():
            return
        import_pending()
        path = root / "creation-command.json"
        if not path.exists():
            return
        cmd = json.loads(path.read_text())
        path.unlink()
        if cmd["operation"] == "stop":
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            unreal.SystemLibrary.quit_editor()
            return
        record = row("game-items", "forest_potion")
        data = unreal.load_asset(record["item_path"])
        screen = row("game-screens", "inventory" + suffix)
        bp = unreal.load_asset(screen["prefab_path"])
        if cmd["operation"] == "retain":
            retained = (data, data.get_editor_property("Icon"), generated(record["pickup_path"]))
            data.set_editor_property("DisplayName", unreal.Text("Forest remedy"))
            data.set_editor_property(
                "Description", unreal.Text("Restores health on a long journey.")
            )
            data.set_editor_property("MaxStack", 7)
            title = next(w for w in widgets(bp) if w.get_name() == "Title")
            title.set_text(unreal.Text("HERBALIST SATCHEL"))
            panel = next(w for w in widgets(bp) if w.get_name() == "Panel")
            panel.set_padding(unreal.Margin(41, 32, 32, 32))
            unreal.BlueprintEditorLibrary.compile_blueprint(bp)
            unreal.EditorAssetLibrary.save_loaded_asset(bp, False)
            unreal.EditorAssetLibrary.save_loaded_asset(data, False)
        elif cmd["operation"] == "verify":
            assert retained == (
                data,
                data.get_editor_property("Icon"),
                generated(record["pickup_path"]),
            )
            assert str(data.get_editor_property("DisplayName")) == "Forest remedy"
            assert (
                str(data.get_editor_property("Description")) == "Restores health on a long journey."
            )
            assert data.get_editor_property("MaxStack") == 7
            assert (
                unreal.get_default_object(generated(screen["prefab_path"])).get_editor_property(
                    "Item0"
                )
                == data
            )
            assert (
                str(next(w for w in widgets(bp) if w.get_name() == "Title").get_text())
                == "HERBALIST SATCHEL"
            )
            assert (
                next(w for w in widgets(bp) if w.get_name() == "Panel")
                .get_editor_property("padding")
                .left
                == 41
            )
            assert (
                len(
                    [
                        a
                        for a in actors.get_all_level_actors()
                        if "PTS.Item:forest_potion" in map(str, a.tags)
                    ]
                )
                == 1
            )
            levels.save_current_level()
        elif cmd["operation"] == "play":
            play_at = time.monotonic()
            levels.editor_request_begin_play()
            return
        (root / "creation-command-done").write_text("done")
    except Exception:
        (root / "creation-error.txt").write_text(traceback.format_exc())
        unreal.log_error(traceback.format_exc())
        if levels.is_in_play_in_editor():
            levels.editor_request_end_play()
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


handle = unreal.register_slate_post_tick_callback(tick)
