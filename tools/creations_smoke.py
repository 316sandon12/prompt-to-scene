"""Real Blender + native editor validation of linked items and editable game UI."""

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from prompt_to_scene import (
    art_samples,
    authoring,
    core,
    creations,
    registry,
    visual_assets,
    workflow,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["unity", "unreal"], required=True)
    parser.add_argument("--editor", required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--ui-suffix", default="")
    args = parser.parse_args()
    os.environ["PTS_CREATION_UI_SUFFIX"] = args.ui_suffix
    repo = Path(__file__).resolve().parents[1]
    project = repo / ".local" / "iteration-v13" / args.engine
    if project.exists() and not args.reuse:
        raise ValueError("Inspect the existing fixture, then use --reuse")
    project.mkdir(parents=True, exist_ok=True)
    os.environ["PTS_HOME"] = str(project / "client-home")
    os.environ.pop("PTS_PROJECT", None)
    os.environ.pop("PTS_UNITY_PROJECT", None)
    if args.engine == "unity":
        for folder in ("Assets/Editor", "Packages", "ProjectSettings"):
            (project / folder).mkdir(parents=True, exist_ok=True)
        (project / "Packages/manifest.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        "com.unity.modules.physics": "1.0.0",
                        "com.unity.modules.ui": "1.0.0",
                        "com.unity.modules.imgui": "1.0.0",
                        "com.unity.ugui": "1.0.0",
                    }
                }
            )
        )
        shutil.copy2(repo / "tools/UnityCreations.cs", project / "Assets/Editor/UnityCreations.cs")
        target = project
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(project),
            "-executeMethod",
            "UnityCreations.Run",
            "-logFile",
            str(project / "engine.log"),
        ]
    else:
        target = project / "Creations.uproject"
        target.write_text(
            json.dumps(
                {
                    "FileVersion": 3,
                    "EngineAssociation": "5.7",
                    "Plugins": [{"Name": "PromptToScene", "Enabled": True}],
                }
            )
        )
        command = [
            args.editor,
            str(target),
            "-unattended",
            "-nosound",
            "-nop4",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_creations_driver.py"),
            "-abslog=" + str(project / "engine.log"),
        ]
    registry.connect(str(target))
    root = core.state_root(project)
    for name in (
        "creation-ready",
        "creation-error.txt",
        "creation-command.json",
        "creation-command-done",
        "creation-play-passed",
    ):
        (root / name).unlink(missing_ok=True)
    output = (project / "console.log").open("w")
    process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)

    def ready(check, seconds=480):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if (root / "creation-error.txt").exists():
                raise AssertionError((root / "creation-error.txt").read_text())
            if process.poll() is not None:
                raise RuntimeError("Editor exited: " + str(project / "engine.log"))
            result = check()
            if result:
                return result
            time.sleep(0.3)
        raise TimeoutError("Creation fixture timed out")

    def wait(task):
        def check():
            state = workflow.job_status(str(target), task["request_id"])
            if state["status"] in workflow.TERMINAL:
                assert state["status"] in {"completed", "imported"}, state
                print(state.get("stage", state["status"]), flush=True)
                return state

        return ready(check, 900)

    def native(operation):
        (root / "creation-command-done").unlink(missing_ok=True)
        core.atomic_json(root / "creation-command.json", {"operation": operation})
        ready(lambda: (root / "creation-command-done").exists())

    try:
        ready(lambda: (root / "creation-ready").exists())
        script = (repo / "examples/herbalist_potion.py").read_text()
        for index, (name, color) in enumerate(
            (
                ("forest_potion", "(.035, .24, .12)"),
                ("moon_potion", "(.04, .10, .38)"),
                ("ember_potion", "(.40, .05, .035)"),
            )
        ):
            if not (root / "game-items" / (name + ".json")).exists():
                info = workflow.inspect_asset(str(target), name + "_model")
                if info["current"].get("status") not in {"unknown", "imported"}:
                    wait(
                        workflow.submit(
                            str(target),
                            name + "_model",
                            script.replace("(.035, .24, .12)", color),
                            [index * 1.2, 0, 0],
                        )
                    )
                    info = workflow.inspect_asset(str(target), name + "_model")
                model = (
                    {"model_asset_id": name + "_model"}
                    if info["current"].get("status") == "imported"
                    else {
                        "model": {
                            "method": "custom",
                            "script": script.replace("(.035, .24, .12)", color),
                            "position": [index * 1.2, 0, 0],
                        }
                    }
                )
                wait(
                    creations.create_item(
                        str(target),
                        name,
                        name=name.replace("_", " ").title(),
                        description="Handcrafted herbalist potion with a brass band and leaf seal.",
                        **model,
                    )
                )
        for kind in ("inventory", "hud", "pause"):
            wait(
                creations.create_ui(
                    str(target),
                    kind + args.ui_suffix,
                    kind,
                    ["forest_potion", "moon_potion", "ember_potion"],
                    title="HERBALIST SATCHEL"
                    if kind == "inventory"
                    else "ADVENTURER"
                    if kind == "hud"
                    else "PAUSED",
                )
            )
        native("retain")
        wait(
            authoring.edit_part(
                str(target), "forest_potion_model", "emblem", changes={"color": [0.1, 0.4, 0.06]}
            )
        )
        wait(
            creations.create_item(
                str(target),
                "forest_potion",
                model_asset_id="forest_potion_model",
                name="Do not replace this manual name",
            )
        )
        wait(
            creations.create_ui(
                str(target),
                "inventory" + args.ui_suffix,
                "inventory",
                ["forest_potion", "moon_potion", "ember_potion"],
                title="Do not replace manual title",
            )
        )
        native("verify")
        view = wait(visual_assets.submit(str(target), "forest_potion_model"))
        geometry = visual_assets.read(str(target), "forest_potion_model", view["model_revision"])
        assert {"body", "cork", "emblem"} <= {p["name"] for p in geometry["parts"]}
        assert sum(len(p["position"]) for p in geometry["parts"]) > 100
        items = creations.catalog(str(target))["game-items"]
        icon = next(x for x in items if x["item_id"] == "forest_potion")
        sample = art_samples.save(
            str(target),
            "Forest glaze & brass",
            "model",
            str(root / "images" / icon["icon_asset_id"] / icon["icon_revision"] / "image.png"),
            "Retain rounded jade ceramic, warm brass and the restrained leaf seal.",
        )
        native("play")
        assert (root / "creation-play-passed").exists()
        evidence = {
            "engine": args.engine,
            "items": items,
            "screens": creations.catalog(str(target))["game-screens"],
            "geometry_parts": sorted({p["name"] for p in geometry["parts"]}),
            "model_view_revision": view["model_revision"],
            "sample": sample["sample_id"],
            "native_manual_edits_and_references_retained": True,
            "play_hooks_verified": True,
        }
        core.atomic_json(project / "evidence.json", evidence)
        print(json.dumps(evidence), flush=True)
    finally:
        if process.poll() is None:
            core.atomic_json(root / "creation-command.json", {"operation": "stop"})
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        output.close()


if __name__ == "__main__":
    main()
