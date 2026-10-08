"""Exercise v0.10 in Blender and a native editor; disposable files stay in .local."""

import argparse
import json
import os
import shutil
import struct
import subprocess
import time
from pathlib import Path

from prompt_to_scene import (
    asset_templates,
    core,
    development,
    game_art,
    levels,
    production,
    project_profiles,
    quality,
    registry,
    reviews,
    styles,
    visual_feedback,
    workflow,
)

MODEL = """
import bpy
bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
c=bpy.data.collections.new("Export");bpy.context.scene.collection.children.link(c)
surfaces=[("ProbeEmission","opaque"),("ProbeMask","mask"),("ProbeBlend","blend")]
for i,(name,surface) in enumerate(surfaces):
    bpy.ops.mesh.primitive_cube_add(size=1,location=((i-1)*1.4,0,.5))
    o=bpy.context.object;o.name=name;o["pts_part"]=name
    for old in list(o.users_collection):old.objects.unlink(o)
    c.objects.link(o)
    m=bpy.data.materials.new(name);m.use_nodes=True;m["pts_surface"]=surface
    p=m.node_tree.nodes.get("Principled BSDF");p.inputs["Base Color"].default_value=(.05,.35,.2,1)
    p.inputs["Roughness"].default_value=.35
    if surface=="opaque":
        p.inputs["Emission Color"].default_value=(.1,.6,.25,1)
        p.inputs["Emission Strength"].default_value=4
    if surface=="blend":p.inputs["Alpha"].default_value=.3
    if surface=="mask":
        n=m.node_tree.nodes.new("ShaderNodeTexChecker");n.inputs["Scale"].default_value=5
        m.node_tree.links.new(n.outputs["Fac"],p.inputs["Alpha"])
    o.data.materials.append(m)
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["unity", "unreal"], required=True)
    parser.add_argument("--editor", required=True)
    parser.add_argument("--urp", action="store_true")
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    project = repo / ".local" / ("production-" + args.engine + ("-urp" if args.urp else ""))
    if project.exists() and not (args.reuse or args.verify_existing):
        raise ValueError("Keep prior evidence; choose a clean task-owned fixture directory")
    project.mkdir(parents=True, exist_ok=True)
    if args.reuse and not args.verify_existing:
        # This fixed fixture path is created only by this maintainer script.
        shutil.rmtree(core.state_root(project), ignore_errors=True)
    os.environ["PTS_HOME"] = str(project / "client-home")
    os.environ.pop("PTS_PROJECT", None)
    os.environ.pop("PTS_UNITY_PROJECT", None)
    if args.verify_existing:
        os.environ["PTS_PRODUCTION_EXISTING"] = "1"
    if args.engine == "unity":
        for path in ("Assets/Editor", "Packages", "ProjectSettings"):
            (project / path).mkdir(parents=True, exist_ok=True)
        dependencies = {"com.unity.modules.physics": "1.0.0"}
        if args.urp:
            dependencies["com.unity.render-pipelines.universal"] = "14.0.11"
            (project / "use-urp.txt").touch()
        (project / "Packages/manifest.json").write_text(json.dumps({"dependencies": dependencies}))
        for name in ("UnityProduction.cs", "UnitySmoke.cs"):
            shutil.copy2(repo / "tools" / name, project / "Assets/Editor" / name)
        target = project
        command = [
            args.editor,
            "-batchmode",
            "-projectPath",
            str(project),
            "-executeMethod",
            "UnityProduction.Existing" if args.verify_existing else "UnityProduction.Run",
            "-logFile",
            str(project / "engine.log"),
        ]
    else:
        if args.reuse and not args.verify_existing:
            (project / "Content/ProductionSmoke.umap").unlink(missing_ok=True)
        target = project / "Production.uproject"
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
            "-ExecutePythonScript=" + str(repo / "tools/unreal_production_driver.py"),
            "-abslog=" + str(project / "engine.log"),
        ]
    registry.connect(str(target))
    root = core.state_root(project)
    for marker in (
        "production-ready",
        "production-error.txt",
        "production-command.json",
        "production-command-done",
    ):
        (root / marker).unlink(missing_ok=True)
    evidence = json.loads((project / "evidence.json").read_text()) if args.verify_existing else {}
    output = (project / "console.log").open("w")
    editor = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)

    def ready(path, timeout=300):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            error = root / "production-error.txt"
            if error.exists():
                raise AssertionError(error.read_text())
            if path.exists():
                return
            if editor.poll() is not None:
                raise RuntimeError("Editor exited; inspect " + str(project / "engine.log"))
            time.sleep(0.3)
        raise TimeoutError(str(path))

    def wait(task):
        end = time.monotonic() + 900
        while time.monotonic() < end:
            state = workflow.job_status(str(target), task["request_id"])
            if state["status"] in workflow.TERMINAL:
                assert state["status"] in {"completed", "imported"}, state
                evidence[task["request_id"]] = state
                (project / "evidence.json").write_text(json.dumps(evidence, indent=2))
                print(state.get("stage", state["status"]), flush=True)
                return state
            if editor.poll() is not None:
                raise RuntimeError("Editor exited during a task")
            time.sleep(0.3)
        raise TimeoutError(str(task))

    def fixture(operation, asset_id=""):
        (root / "production-command-done").unlink(missing_ok=True)
        core.atomic_json(
            root / "production-command.json", dict(operation=operation, asset_id=asset_id)
        )
        ready(root / "production-command-done")

    try:
        ready(root / "production-ready")
        if args.verify_existing:
            before = reviews.capture(str(target), "material_probe", view="game")
            wait(before)
            fixture("lens", "material_probe")
            after = reviews.capture(
                str(target), "material_probe", before["review_id"], stage="after", view="game"
            )
            wait(after)
            sizes = [
                struct.unpack(
                    ">II", (root / "previews" / (task["request_id"] + ".png")).read_bytes()[16:24]
                )
                for task in (before, after)
            ]
            assert sizes[0] == sizes[1] == (1024, 576), sizes
            wait(
                development.configure(
                    str(target),
                    "material_probe",
                    "switch",
                    demo_input=False,
                    event_id="fixture_toggle",
                    interaction_point=[0.1, 0.2, 0.1],
                )
            )
            play = wait(
                development.playcheck(str(target), ["material_probe"], duration=1, capture=False)
            )
            assert play["development"]["passed"], play
            evidence["verification"].update(switch_play_mode=True, fixed_game_aspect=True)
            (project / "evidence.json").write_text(json.dumps(evidence, indent=2))
            print("PRODUCTION_EXISTING_PASS " + str(project), flush=True)
            return
        profile = project_profiles.read(str(target))
        profile["preparation"].update(texture_size=256, lod_ratios=[])
        project_profiles.configure(str(target), mode="save", settings=profile)
        game_art.configure(
            str(target),
            {
                "world": "A handmade herbalist shop",
                "gameplay": "gather and trade",
                "view": "first_person",
            },
        )
        styles.save(str(target), "cozy", "mobile")
        wait(
            production.submit(
                str(target),
                [
                    dict(
                        asset_id="material_probe",
                        method="custom",
                        script=MODEL,
                        position=[10, 0, 0],
                    )
                ],
            )
        )
        fixture("materials", "material_probe")
        fixture("camera", "material_probe")
        review = wait(quality.start(str(target), "material_probe", view="game"))
        proof = visual_feedback.evidence(str(target), review["request_id"])
        assert len(proof["images"]) == 2 and proof["view"] == "game"
        asset_templates.save(
            str(target), "portable_surfaces", "material_probe", "Portable material fixture"
        )
        wait(
            asset_templates.instantiate(
                str(target),
                "portable_surfaces",
                "surface_variant",
                part_changes={"ProbeBlend": {"scale": [1, 1, 1.15]}},
                position=[15, 0, 0],
            )
        )
        original = workflow.inspect_asset(str(target), "material_probe")["metadata"]["report"][
            "parts"
        ]
        variant = workflow.inspect_asset(str(target), "surface_variant")["metadata"]["report"][
            "parts"
        ]
        assert original["ProbeMask"]["geometry_hash"] == variant["ProbeMask"]["geometry_hash"]
        wait(
            levels.build(
                str(target), "shop", cell_size=6, modules=[{"cell": [0, 0, 0], "kind": "room"}]
            )
        )
        task = wait(
            production.submit(
                str(target),
                [
                    dict(
                        asset_id="shop_table",
                        method="recipe",
                        kind="table",
                        parameters={"width": 1.2, "depth": 0.7},
                    ),
                    dict(asset_id="shop_shelf", method="recipe", kind="shelf"),
                    dict(asset_id="ore", method="interactive", kind="resource"),
                ],
                description="Furnished gathering shop",
                furnish={"level_id": "shop"},
            )
        )
        assert task["dressing"]["clearance"]["development"]["passed"]
        asset_templates.save(str(target), "shop_furniture", "shop_table", "Matching wood furniture")
        wait(
            asset_templates.instantiate(
                str(target),
                "shop_furniture",
                "rubble",
                parameters={"height": 0.25},
                position=[25, 0, 0],
                family_style=True,
            )
        )
        wait(
            development.configure(
                str(target),
                "ore",
                "resource",
                uses=3,
                event_id="ore_mined",
                label="采集矿石",
                depleted_asset_id="rubble",
                demo_input=False,
            )
        )
        fixture("hooks", "ore")
        play = wait(development.playcheck(str(target), ["ore"], "shop", duration=1, capture=False))
        assert play["development"]["passed"], play
        assert all(c["passed"] for c in play["development"]["checks"])
        evidence["verification"] = dict(
            engine=args.engine,
            urp=args.urp,
            material_surfaces=True,
            native_game_camera=True,
            editable_custom_template=True,
            furnished_clearance=True,
            resource_play_mode=True,
            studio_comparison=proof["images"],
        )
        (project / "evidence.json").write_text(json.dumps(evidence, indent=2))
        print("PRODUCTION_SMOKE_PASS " + str(project), flush=True)
    finally:
        if editor.poll() is None:
            core.atomic_json(root / "production-command.json", {"operation": "stop"})
            try:
                editor.wait(timeout=45)
            except subprocess.TimeoutExpired:
                editor.terminate()
                editor.wait(timeout=15)
        output.close()


if __name__ == "__main__":
    main()
