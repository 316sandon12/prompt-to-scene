"""Run actual Blender -> Unreal import/revision/texture checks in a disposable project."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from prompt_to_scene.core import atomic_json, build, status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unreal", type=Path, required=True, help="UnrealEditor-Cmd executable")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    (repo / ".local").mkdir(exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="unreal-smoke-", dir=repo / ".local"))
    for folder in ("Content", "Config", "Plugins"):
        (project / folder).mkdir()
    shutil.copytree(repo / "unreal/PromptToScene", project / "Plugins/PromptToScene")
    descriptor = project / "Smoke.uproject"
    descriptor.write_text(
        json.dumps(
            {
                "FileVersion": 3,
                "EngineAssociation": "5.7",
                "Plugins": [{"Name": "PromptToScene", "Enabled": True}],
            }
        )
    )
    print(f"Project: {project}", flush=True)
    recipe = (repo / "examples/crate.py").read_text()
    evidence = []

    def run_editor(phase):
        atomic_json(project / ".prompt-to-scene/smoke-phase.json", {"phase": phase})
        log = project / f"unreal-{phase}.log"
        with log.open("w") as output:
            result = subprocess.run(
                [
                    str(args.unreal),
                    str(descriptor),
                    "-unattended",
                    "-nop4",
                    "-nosplash",
                    "-RenderOffscreen",
                    "-nosound",
                    "-PromptToSceneNoWatch",
                    "-ExecutePythonScript=" + str(repo / "tools/unreal_assertions.py"),
                    "-abslog=" + str(project / f"engine-{phase}.log"),
                ],
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=360,
            )
        if result.returncode or not (project / f".prompt-to-scene/{phase}-passed.json").exists():
            raise RuntimeError(f"Unreal {phase} failed; inspect {log}")
        print(f"Unreal {phase}: PASS", flush=True)

    for phase in ("initial", "revision"):
        script = (
            recipe
            if phase == "initial"
            else recipe.replace("(0.24, 0.085, 0.025)", "(0.025, 0.24, 0.085)")
            + "\nfor obj in collection.all_objects:\n"
            "    obj.location.z *= 1.25\n    obj.scale.z *= 1.25\n"
        )
        queued = build(
            descriptor, "crate", script, [2, 0, 3] if phase == "initial" else [99, 99, 99]
        )
        run_editor(phase)
        receipt = status(descriptor, "crate")
        assert receipt["status"] == "imported" and receipt["request_id"] == queued["request_id"]
        evidence.append(receipt)

    textured = (repo / "examples/textured_cube.py").read_text().replace('"Paint"', '"漆面 / Paint"')
    queued = build(descriptor, "textured_cube", textured, collider=False)
    source = Path(queued["source_blend"])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    saved = build(descriptor, "saved_cube", "", collider=False, blend_file=source)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    run_editor("textures")
    for name, request in (("textured_cube", queued), ("saved_cube", saved)):
        receipt = status(descriptor, name)
        assert receipt["status"] == "imported" and receipt["request_id"] == request["request_id"]
        evidence.append(receipt)
    (project / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(
        "PASS: Unreal geometry, PBR, revision, actor identity, textures and saved .blend",
        flush=True,
    )


if __name__ == "__main__":
    main()
