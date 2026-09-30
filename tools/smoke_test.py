"""Actual Blender -> Unity -> revision checks in a fresh disposable project."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from prompt_to_scene.core import build, status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--unity", required=True, type=Path)
    parser.add_argument("--urp", action="store_true", help="Verify URP 14 (Unity 2022.3)")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    local = repo / ".local"
    local.mkdir(exist_ok=True)
    project = Path(tempfile.mkdtemp(prefix="unity-smoke-", dir=local))
    for folder in ("Assets/Editor", "Packages", "ProjectSettings"):
        (project / folder).mkdir(parents=True)
    version = subprocess.check_output([str(args.unity), "-version"], text=True).strip()
    (project / "ProjectSettings/ProjectVersion.txt").write_text(f"m_EditorVersion: {version}\n")
    package = repo / "unity/Packages/com.prompttoscene.bridge"
    (project / "Packages/manifest.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "com.prompttoscene.bridge": "file:" + package.as_posix(),
                    "com.unity.modules.physics": "1.0.0",
                }
            }
        )
    )
    if args.urp:
        manifest_path = project / "Packages/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["dependencies"]["com.unity.render-pipelines.universal"] = "14.0.11"
        manifest_path.write_text(json.dumps(manifest))
        (project / "use-urp.txt").touch()
    shutil.copyfile(repo / "tools/UnitySmoke.cs", project / "Assets/Editor/UnitySmoke.cs")
    recipe = (repo / "examples/crate.py").read_text()
    print(f"Project: {project}", flush=True)
    evidence = []

    def run_unity(phase, method="UnitySmoke.Run"):
        log = project / f"unity-{phase}.log"
        result = subprocess.run(
            [
                str(args.unity),
                "-batchmode",
                "-nographics",
                "-projectPath",
                str(project),
                "-executeMethod",
                method,
                "-logFile",
                str(log),
            ],
            timeout=300,
        )
        if result.returncode or not (project / f".prompt-to-scene/{phase}-passed.txt").exists():
            raise RuntimeError(f"Unity {phase} failed; inspect {log}")

    for phase in ("initial", "revision"):
        script = (
            recipe
            if phase == "initial"
            else recipe.replace("(0.24, 0.085, 0.025)", "(0.025, 0.24, 0.085)")
        )
        queued = build(project, "crate", script, [2, 0, 3] if phase == "initial" else [99, 0, 99])
        print(f"Blender {phase}: {queued['triangles']} triangles, queued", flush=True)
        run_unity(phase)
        receipt = status(project, "crate")
        assert receipt["request_id"] == queued["request_id"]
        evidence.append(receipt)
        print(f"Unity {phase}: imported, prefab GUID {receipt['prefab_guid']}", flush=True)

    textured = (repo / "examples/textured_cube.py").read_text()
    queued = build(project, "textured_cube", textured, collider=False)
    source = Path(queued["source_blend"])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    saved = build(project, "saved_cube", "", collider=False, blend_file=source)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    run_unity("textures", "UnitySmoke.Textures")
    for name, request in (("textured_cube", queued), ("saved_cube", saved)):
        receipt = status(project, name)
        assert receipt["request_id"] == request["request_id"]
        evidence.append(receipt)
    print("Unity textures: base color + normal map; saved .blend republished unchanged", flush=True)

    unsupported = textured + (
        '\nnoise = nodes.new("ShaderNodeTexNoise")\n'
        'links.new(noise.outputs["Color"], shader.inputs["Base Color"])\n'
    )
    try:
        build(project, "unsupported", unsupported)
    except RuntimeError as error:
        assert "requires a direct Image Texture" in str(error)
        assert status(project, "unsupported")["status"] == "unknown"
    else:
        raise AssertionError("Procedural texture should have been rejected before queuing")
    (project / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print(
        "PASS: real Blender/Unity import, revision, textures, saved source and validation",
        flush=True,
    )


if __name__ == "__main__":
    main()
