"""Native staging check; all generated projects/logs stay in .local/scene-studio."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from prompt_to_scene import core, registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["unity", "unreal"], required=True)
    parser.add_argument("--editor", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    folder = repo / ".local/scene-studio" / args.engine
    folder.mkdir(parents=True, exist_ok=False)
    os.environ["PTS_HOME"] = str(folder / "client-home")
    for key in ("PTS_PROJECT", "PTS_UNITY_PROJECT"):
        os.environ.pop(key, None)
    if args.engine == "unity":
        for name in ("Assets/Editor", "Packages", "ProjectSettings"):
            (folder / name).mkdir(parents=True)
        core.atomic_json(
            folder / "Packages/manifest.json",
            {
                "dependencies": {
                    "com.unity.modules.physics": "1.0.0",
                    "com.unity.modules.ui": "1.0.0",
                    "com.unity.modules.imgui": "1.0.0",
                    "com.unity.ugui": "1.0.0",
                }
            },
        )
        shutil.copy2(
            repo / "tools/UnitySceneStaging.cs", folder / "Assets/Editor/UnitySceneStaging.cs"
        )
        target = folder
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(folder),
            "-executeMethod",
            "UnitySceneStaging.Run",
            "-logFile",
            str(folder / "engine.log"),
        ]
    else:
        target = folder / "SceneStaging.uproject"
        core.atomic_json(
            target,
            {
                "FileVersion": 3,
                "EngineAssociation": "5.7",
                "Plugins": [{"Name": "PromptToScene", "Enabled": True}],
            },
        )
        command = [
            args.editor,
            str(target),
            "-unattended",
            "-nosound",
            "-nop4",
            "-RenderOffscreen",
            "-ExecutePythonScript=" + str(repo / "tools/unreal_scene_staging.py"),
            "-abslog=" + str(folder / "engine.log"),
        ]
    registry.connect(str(target))
    (core.state_root(folder) / "launcher.json").unlink(missing_ok=True)
    with (folder / "process.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            code = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise RuntimeError("Native staging timed out; inspect the retained logs") from None
    if not (folder / "native-pass.txt").is_file():
        raise RuntimeError(
            f"Native check failed; inspect {folder / 'native-error.txt'} and engine.log"
        )
    print(args.engine, (folder / "native-pass.txt").read_text(), "exit", code)
    if code:
        raise RuntimeError("Assertions passed but the editor exit was not clean")


if __name__ == "__main__":
    main()
