"""Small native read-contract check. No Blender, images, asset imports or package builds."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from prompt_to_scene import core, registry, scene_context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["unity", "unreal"], required=True)
    parser.add_argument("--editor", required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = repo / ".local/scene-context" / args.engine
    root.mkdir(parents=True, exist_ok=False)
    os.environ["PTS_HOME"] = str(root / "client-home")
    for name in ("PTS_PROJECT", "PTS_UNITY_PROJECT"):
        os.environ.pop(name, None)
    if args.engine == "unity":
        for name in ("Assets/Editor", "Packages", "ProjectSettings"):
            (root / name).mkdir(parents=True)
        core.atomic_json(
            root / "Packages/manifest.json",
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
            repo / "tools/UnitySceneContext.cs", root / "Assets/Editor/UnitySceneContext.cs"
        )
        target = root
        command = [
            args.editor,
            "-batchmode",
            "-nographics",
            "-projectPath",
            str(root),
            "-executeMethod",
            "UnitySceneContext.Run",
            "-logFile",
            str(root / "engine.log"),
        ]
    else:
        target = root / "SceneContext.uproject"
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
            "-ExecutePythonScript=" + str(repo / "tools/unreal_scene_context.py"),
            "-abslog=" + str(root / "engine.log"),
        ]
    registry.connect(str(target))
    # This fixture only checks native reads; it does not need an auxiliary studio process.
    (core.state_root(root) / "launcher.json").unlink(missing_ok=True)
    with (root / "process.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            code = process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise RuntimeError("Native check timed out; inspect the retained engine.log") from None
    if (root / "native-error.txt").exists() or not (root / "scene-context-result.json").exists():
        raise RuntimeError(f"{args.engine} check failed; inspect {root / 'engine.log'}")
    result = json.loads((root / "scene-context-result.json").read_text())
    if args.engine == "unreal" and not (root / "native-pass.txt").is_file():
        raise RuntimeError("UE script did not finish")
    core.atomic_json(core.state_root(root) / "action-receipts" / ("a" * 32 + ".json"), result)
    scene_context.save(target, "a" * 32, {"fit": "fit"})
    brief = scene_context.brief(target)
    assert brief["max_size_m"] == [2, 1, 0.5]
    assert brief["camera"]["primary"]
    assert scene_context.projected_bounds(brief["target"], brief["camera"])["status"] == "estimated"
    print("PASS", args.engine, "native measurements → retained model/image brief", flush=True)
    if code:
        raise RuntimeError(
            f"Native assertions passed, but {args.engine} exited with code {code}; "
            "inspect engine.log before declaring the whole run successful"
        )


if __name__ == "__main__":
    main()
