"""Actual PIE verification using only the installable bridge, without the C++ builder."""

import json
import os
import time
import traceback
from pathlib import Path

from prompt_to_scene_unreal import import_pending
from prompt_to_scene_unreal.game_creations import generated

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
root.mkdir(exist_ok=True)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if unreal.EditorAssetLibrary.does_asset_exist("/Game/GameplayFixture"):
    levels.load_level("/Game/GameplayFixture")
else:
    levels.new_level("/Game/GameplayFixture")
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
if not any("PTS.AdapterExample" in map(str, a.tags) for a in subsystem.get_all_level_actors()):
    example = subsystem.spawn_actor_from_class(
        generated("/PromptToScene/Examples/BP_PTSProjectAdapterExample"), unreal.Vector()
    )
    example.tags = [unreal.Name("PTS.AdapterExample")]
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "gameplay-ready").write_text("ready")
screen_prefix = os.environ.get("PTS_SCREEN_PREFIX", "apothecary")
play_at = None
capture_at = None


def play():
    global capture_at
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    actors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
    session = next(a for a in actors if "PTS.Flow:apothecary" in map(str, a.tags))

    def count(key):
        return dict(session.get_editor_property("Inventory")).get("apothecary_" + key, 0)

    def apply(key):
        return session.call_method("TryRule", args=(key,))

    assert not apply("craft_potion") and count("potion") == 0, "Missing materials were consumed"
    herb = next(
        a
        for a in actors
        if a.get_editor_property("tags") and "PTS.Asset:apothecary_herb_model" in map(str, a.tags)
    )
    herb.call_method("Interact")
    assert herb.get_editor_property("Collected") and count("herb") == 6, (
        "Pickup did not run bound rule"
    )
    assert not apply("collect_herb"), "Once-only collection repeated"
    assert apply("collect_bottle") and apply("craft_potion"), "Collect/craft failed"
    assert (count("herb"), count("bottle"), count("potion")) == (4, 2, 1)

    def host(kind):
        return next(
            a for a in actors if "PTS.Screen:" + screen_prefix + "_" + kind in map(str, a.tags)
        )

    inv_host = host("inventory")
    inv_host.call_method("Show")
    inv = inv_host.get_editor_property("WidgetRef")
    assert inv and inv.is_in_viewport()
    inv.call_method("RefreshItems")
    inv.call_method("SelectItem", args=(2,))
    assert inv.get_editor_property("UseButton").get_is_enabled(), "Use control disabled"
    inv.call_method("UseSelected")
    assert count("potion") == 0 and session.get_editor_property("Health") == 70
    assert apply("craft_potion") and apply("use_potion")
    assert session.get_editor_property("Health") == 100
    assert apply("craft_potion") and not apply("use_potion") and count("potion") == 1
    assert session.call_method("SaveProgress"), repr(
        {
            k: session.get_editor_property(k)
            for k in ("SaveKey", "SaveBlocked", "SaveError", "FlowId")
        }
    )
    session.set_editor_property("Inventory", {})
    session.set_editor_property("Health", 1.0)
    session.set_editor_property("Initialized", False)
    session.call_method("Initialize")
    assert count("potion") == 1 and session.get_editor_property("Health") == 100
    assert dict(session.get_editor_property("Completed")).get("collect_herb")
    # Foreign saves are retained and blocked instead of silently replaced.
    key = session.get_editor_property("SaveKey")
    data = unreal.GameplayStatics.load_game_from_slot(key, 0)
    data.set_editor_property("FlowId", "foreign_flow")
    unreal.GameplayStatics.save_game_to_slot(data, key, 0)
    session.set_editor_property("Initialized", False)
    session.call_method("Initialize")
    assert session.get_editor_property("SaveBlocked") and not session.call_method("SaveProgress")
    assert (
        unreal.GameplayStatics.load_game_from_slot(key, 0).get_editor_property("FlowId")
        == "foreign_flow"
    )
    unreal.GameplayStatics.delete_game_in_slot(key, 0)
    session.set_editor_property("SaveError", "")
    inv.call_method("RefreshItems")
    inv.call_method("SelectItem", args=(0,))
    # Pagination remains native when the UI is driven by existing project code.
    current = list(inv.get_editor_property("Items"))
    inv.set_editor_property("FlowId", "")
    inv.set_editor_property("FlowSession", None)
    inv.set_editor_property("Items", (current * 7)[:20])
    inv.call_method("RefreshItems")
    inv.call_method("NextPage")
    assert inv.get_editor_property("Page") == 1 and inv.get_editor_property("Item3")
    assert not inv.get_editor_property("Slot4").get_is_enabled()
    inv.set_editor_property("Items", current)
    inv.set_editor_property("FlowId", "apothecary")
    inv.call_method("RefreshItems")
    inv.call_method("SelectItem", args=(0,))
    hud = host("hud").get_editor_property("WidgetRef")
    hud.call_method("RefreshItems")
    assert abs(hud.get_editor_property("Health").get_editor_property("percent") - 1) < 0.001
    host("pause").call_method("Show")
    assert unreal.GameplayStatics.is_game_paused(world)
    host("pause").get_editor_property("WidgetRef").call_method("Resume")
    assert not unreal.GameplayStatics.is_game_paused(world)
    host("hud").call_method("Hide")
    (root / "gameplay-play-passed").write_text(
        "PIE pickup, atomic craft/use, full-health rejection, saved progress, "
        "foreign-save protection, dynamic inventory, HUD and pause passed."
    )
    adapter = next(a for a in actors if "PTS.AdapterExample" in map(str, a.tags))
    adapter.set_editor_property("Inventory", {"apothecary_herb": 4, "apothecary_bottle": 2})
    session.set_editor_property("Autosave", False)
    session.set_editor_property("Adapter", adapter)
    assert (
        apply("craft_potion")
        and dict(adapter.get_editor_property("Inventory"))["apothecary_potion"] == 1
    )
    adapter.set_editor_property("AllowTransactions", False)
    assert (
        not apply("craft_potion")
        and dict(adapter.get_editor_property("Inventory"))["apothecary_herb"] == 2
    )
    adapter.set_editor_property("AllowTransactions", True)
    assert apply("use_potion") and adapter.get_editor_property("Health") == 80
    session.set_editor_property("Adapter", None)
    (root / "gameplay-adapter-passed").write_text(
        "Native interface read/commit/rejection and external health passed"
    )
    capture_at = time.monotonic()


def tick(_delta):
    global play_at, capture_at
    try:
        if capture_at:
            if capture_at > 0 and time.monotonic() > capture_at + 1:
                world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
                unreal.SystemLibrary.execute_console_command(
                    world, "Shot showui filename=" + str(root / "inventory-ue.png")
                )
                capture_at = -time.monotonic()
            elif capture_at < 0 and time.monotonic() > -capture_at + 2:
                levels.editor_request_end_play()
                capture_at = None
                (root / "gameplay-command-done").write_text("done")
            return
        if play_at:
            if levels.is_in_play_in_editor() and time.monotonic() > play_at + 2:
                play()
                play_at = None
            return
        if levels.is_in_play_in_editor():
            return
        import_pending()
        path = root / "gameplay-command.json"
        if not path.exists():
            return
        command = json.loads(path.read_text())
        path.unlink()
        if command["operation"] == "stop":
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            unreal.SystemLibrary.quit_editor()
        elif command["operation"] == "play":
            record = json.loads((root / "gameplay/apothecary.json").read_text())
            unreal.GameplayStatics.delete_game_in_slot(record["save_key"], 0)
            levels.save_current_level()
            play_at = time.monotonic()
            levels.editor_request_begin_play()
        else:
            raise ValueError("Unknown smoke command")
    except Exception:
        (root / "gameplay-error.txt").write_text(traceback.format_exc())
        unreal.log_error(traceback.format_exc())
        if levels.is_in_play_in_editor():
            levels.editor_request_end_play()
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


handle = unreal.register_slate_post_tick_callback(tick)
