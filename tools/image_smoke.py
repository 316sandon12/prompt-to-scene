"""Focused native image import/update/restore validation. No Blender or paid generation."""

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw

from prompt_to_scene import core, image_assets, registry, workflow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["unity", "unreal"], required=True)
    parser.add_argument("--editor", required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--demo-only", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    project = repo / ".local" / ("images-" + args.engine)
    if project.exists() and not args.reuse:
        raise ValueError("Fixture already exists; inspect it or use --reuse")
    project.mkdir(parents=True, exist_ok=True)
    os.environ["PTS_HOME"] = str(project / "client-home")
    os.environ.pop("PTS_PROJECT", None)
    os.environ.pop("PTS_UNITY_PROJECT", None)
    if args.engine == "unity":
        for folder in ("Assets/Editor", "Packages", "ProjectSettings"):
            (project / folder).mkdir(parents=True, exist_ok=True)
        (project / "Packages/manifest.json").write_text(
            json.dumps({"dependencies": {"com.unity.modules.physics": "1.0.0"}})
        )
        shutil.copy2(repo / "tools/UnityImages.cs", project / "Assets/Editor/UnityImages.cs")
        target = project
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(project),
            "-executeMethod",
            "UnityImages.Run",
            "-logFile",
            str(project / "engine.log"),
        ]
    else:
        target = project / "Images.uproject"
        if not target.exists():
            target.write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.7"}))
        command = [
            args.editor,
            str(target),
            "-unattended",
            "-nosound",
            "-nop4",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_image_driver.py"),
            "-abslog=" + str(project / "engine.log"),
        ]
    registry.connect(str(target))
    root = core.state_root(project)
    for name in ("image-ready", "image-error.txt", "image-command.json", "image-command-done"):
        (root / name).unlink(missing_ok=True)
    output = (project / "console.log").open("w")
    process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)

    def ready(check, seconds=240):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if (root / "image-error.txt").exists():
                raise AssertionError((root / "image-error.txt").read_text())
            if process.poll() is not None:
                raise RuntimeError("Native editor exited; inspect " + str(project / "engine.log"))
            result = check()
            if result:
                return result
            time.sleep(0.2)
        raise TimeoutError("Native image fixture timed out")

    def wait(task):
        def completed():
            state = workflow.job_status(str(target), task["request_id"])
            if state["status"] in workflow.TERMINAL:
                assert state["status"] == "completed", state
                return state

        return ready(completed)

    def native(operation):
        (root / "image-command-done").unlink(missing_ok=True)
        core.atomic_json(
            root / "image-command.json", {"operation": operation, "asset_id": "ui_panel"}
        )
        ready(lambda: (root / "image-command-done").exists())

    try:
        ready(lambda: (root / "image-ready").exists())
        if args.demo_only:
            result = wait(image_assets.example(str(target)))
            assert result["image"]["width"] == 256 and result["image"]["height"] == 256
            core.atomic_json(project / "demo-evidence.json", result)
            print(json.dumps(result), flush=True)
            return
        source = project / "panel.png"

        def draw(color):
            image = Image.new("RGBA", (128, 64))
            ImageDraw.Draw(image).rounded_rectangle((1, 1, 126, 62), radius=8, fill=color)
            image.save(source)

        draw((40, 100, 60, 255))
        first = wait(
            image_assets.import_image(
                str(target),
                "ui_panel",
                str(source),
                kind="panel",
                width=128,
                height=64,
                border=[8, 4, 12, 6],
            )
        )
        native("retain")
        draw((120, 50, 80, 255))
        second = wait(
            image_assets.import_image(
                str(target),
                "ui_panel",
                str(source),
                kind="panel",
                width=128,
                height=64,
                border=[8, 4, 12, 6],
            )
        )
        native("verify")
        restored = wait(image_assets.publish(str(target), "ui_panel", first["image"]["revision"]))
        native("verify")
        assert (
            first["image"]["texture_path"]
            == second["image"]["texture_path"]
            == restored["image"]["texture_path"]
        )
        evidence = dict(
            engine=args.engine,
            imported=first["image"],
            updated=second["image"],
            restored=restored["image"],
            native_reference_retained=True,
            nine_slice_verified=True,
            source_alpha=True,
        )
        core.atomic_json(project / "evidence.json", evidence)
        print(json.dumps(evidence), flush=True)
    finally:
        if process.poll() is None:
            core.atomic_json(root / "image-command.json", {"operation": "stop"})
            try:
                process.wait(timeout=20)
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
