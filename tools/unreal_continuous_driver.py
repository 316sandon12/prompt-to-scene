"""v0.15 real PIE travel/migration checks in a normal-plugin fixture only."""

import json
import runpy
import time
import traceback
from pathlib import Path

from prompt_to_scene_unreal.game_creations import generated

import unreal

# Retain the v0.14 gameplay checks and native request pump, using a separate command file below.
runpy.run_path(str(Path(__file__).with_name("unreal_gameplay_driver.py")))
root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
phase, started = 0, 0


def session(objects):
    return next(a for a in objects if "PTS.Flow:apothecary" in map(str, a.tags))


def migrated_settings(obj):
    obj.set_editor_property("SaveVersion", 2)
    obj.set_editor_property("ItemAliases", {"old_herb": "apothecary_herb"})
    obj.set_editor_property("RuleAliases", {"old_collect": "collect_herb"})
    obj.set_editor_property("Autosave", False)


def done(name):
    (root / ("continuous-" + name)).write_text("passed")


def tick(_delta):
    global phase, started
    try:
        if phase:
            if not levels.is_in_play_in_editor() or time.monotonic() - started < 2:
                return
            world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
            instances = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor)
            active = session(instances)

            def count(key):
                return dict(active.get_editor_property("Inventory")).get(key, 0)

            if phase == 1:
                assert count("apothecary_herb") == 3 and count("old_herb") == 0
                assert dict(active.get_editor_property("Completed")).get("collect_herb")
                assert not active.call_method("TryRule", args=("collect_herb",))
                for rule in ("collect_bottle", "craft_potion", "use_potion"):
                    assert active.call_method("TryRule", args=(rule,)), rule
                assert active.get_editor_property("Health") == 55
                key = active.get_editor_property("SaveKey")
                backup = unreal.GameplayStatics.load_game_from_slot(key + "_before_v1", 0)
                assert backup and dict(backup.get_editor_property("Inventory"))["old_herb"] == 3
                phase, started = 2, time.monotonic()
                unreal.GameplayStatics.open_level(world, "/Game/ContinuousB")
                return
            if "ContinuousB" not in world.get_path_name():
                return
            assert count("apothecary_herb") == 1 and count("apothecary_potion") == 0
            assert active.get_editor_property("Health") == 55
            assert dict(active.get_editor_property("Completed")).get("collect_herb")
            saved = unreal.GameplayStatics.load_game_from_slot(
                active.get_editor_property("SaveKey"), 0
            )
            assert saved.get_editor_property("SaveVersion") == 2
            done("travel-passed")
            phase = 0
            levels.editor_request_end_play()
            return
        if levels.is_in_play_in_editor():
            return
        path = root / "continuous-command.json"
        if not path.exists():
            return
        command = json.loads(path.read_text())
        path.unlink()
        operation = command["operation"]
        if operation == "provider":
            example = next(
                a for a in actors.get_all_level_actors() if "PTS.AdapterExample" in map(str, a.tags)
            )
            actors.set_selected_level_actors([example])
            levels.save_current_level()
            done("provider-ready")
        elif operation == "adapter":
            current = session(actors.get_all_level_actors())
            assert current.get_editor_property("Adapter")
            current.modify()
            current.set_editor_property("Adapter", None)
            levels.save_current_level()
            done("adapter-passed")
        elif operation == "second_scene":
            levels.save_current_level()
            levels.new_level("/Game/ContinuousB")
            done("second-ready")
        elif operation == "travel":
            migrated_settings(session(actors.get_all_level_actors()))
            levels.save_current_level()
            levels.load_level("/Game/GameplayFixture")
            current = session(actors.get_all_level_actors())
            migrated_settings(current)
            record = json.loads((root / "gameplay/apothecary.json").read_text())
            defaults = unreal.get_default_object(generated(record["definition_path"]))
            migrated_settings(defaults)
            unreal.EditorAssetLibrary.save_asset(record["definition_path"])
            data = unreal.GameplayStatics.create_save_game_object(
                generated("/PromptToScene/Templates/BP_PTSGameSave")
            )
            for key, value in dict(
                FlowId="apothecary",
                SaveKey=record["save_key"],
                SaveVersion=1,
                Inventory={"old_herb": 3},
                Completed={"old_collect": True},
                Health=25.0,
            ).items():
                data.set_editor_property(key, value)
            assert unreal.GameplayStatics.save_game_to_slot(data, record["save_key"], 0)
            levels.save_current_level()
            phase, started = 1, time.monotonic()
            levels.editor_request_begin_play()
        elif operation == "save":
            levels.save_all_dirty_levels()
            unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
            done("saved")
        else:
            raise ValueError("Unknown continuous operation")
    except Exception:
        (root / "continuous-error.txt").write_text(traceback.format_exc())
        unreal.log_error(traceback.format_exc())
        phase = 0
        if levels.is_in_play_in_editor():
            levels.editor_request_end_play()


handle = unreal.register_slate_post_tick_callback(tick)
