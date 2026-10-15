"""Read saved maps and engine toolchain location before AutomationTool builds a player."""

import json
import re
from pathlib import Path

import unreal

from .gameplay import result


def execute(request, command, root):
    spec = json.loads(command.get("content_json", "{}"))
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    current = world.get_path_name().split(".")[0] if world else ""
    scenes = spec.get("scenes") or [current]
    if command.get("mode") == "prepare":
        if not scenes or any(
            not re.fullmatch(r"/Game/[A-Za-z0-9_/]+", s)
            or not unreal.EditorAssetLibrary.does_asset_exist(s)
            for s in scenes
        ):
            raise ValueError("Choose saved /Game maps before packaging")
        dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        if dirty:
            raise ValueError("Save edited maps before packaging the game")
        if unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages():
            raise ValueError("Save edited project assets before packaging the game")
    elif command.get("mode") != "inspect":
        raise ValueError("Unknown delivery action")
    return result(
        dict(
            engine="unreal",
            version=unreal.SystemLibrary.get_engine_version(),
            scenes=scenes,
            engine_root=str(
                Path(
                    unreal.Paths.convert_relative_path_to_full(unreal.Paths.engine_dir())
                ).resolve()
            ),
        ),
        "Native engine and saved maps inspected",
    )
