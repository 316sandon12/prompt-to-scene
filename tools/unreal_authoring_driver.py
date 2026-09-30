"""Disposable real Unreal scene for the v0.4 authoring smoke test."""

import json
import time
from pathlib import Path

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.new_level("/Game/AuthoringSmoke_" + str(int(time.time())))
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
floor = actors.spawn_actor_from_object(
    unreal.load_asset("/Engine/BasicShapes/Cube.Cube"), unreal.Vector(0, 0, -50)
)
floor.set_actor_scale3d(unreal.Vector(100, 100, 1))
light = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 600))
light.set_actor_rotation(unreal.Rotator(pitch=-45, yaw=30), False)
light.light_component.set_editor_property("intensity", 5)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "authoring-ready").write_text("ready")
deadline = time.monotonic() + 1800


def finish(error=None):
    if error:
        (root / "authoring-error.txt").write_text(str(error))
    unreal.unregister_slate_post_tick_callback(handle)
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


def tick(_delta):
    try:
        if time.monotonic() > deadline:
            raise RuntimeError("Authoring timeout")
        path = root / "authoring-command.json"
        if not path.exists():
            return
        command = json.loads(path.read_text())
        path.unlink()
        if command["operation"] == "stop":
            finish()
            return
        selected = [
            a
            for a in actors.get_all_level_actors()
            if any(
                (
                    str(t).startswith("PTS.Asset:" + command["asset_id"])
                    if command["operation"] == "select_all"
                    else str(t) == "PTS.Asset:" + command["asset_id"]
                )
                for t in a.tags
            )
        ]
        assert selected, "Fixture asset missing"
        if command["operation"] in {"select", "select_all"}:
            actors.set_selected_level_actors(selected)
        if command["operation"] == "check_facing":
            chair = selected[0]
            name = command["asset_id"].rsplit("_", 1)[0] + "_table"
            table = next(
                a for a in actors.get_all_level_actors() if "PTS.Asset:" + name in map(str, a.tags)
            )
            mesh = chair.static_mesh_component.static_mesh.get_static_mesh_description(0)
            points = [
                mesh.get_vertex_position(unreal.VertexID(id_value=i))
                for i in range(mesh.get_vertex_count())
            ]
            top = max(p.z for p in points)
            back = [p for p in points if p.z > top * 0.7]
            center = unreal.Vector(
                sum(p.x for p in back) / len(back), sum(p.y for p in back) / len(back), 0
            )
            backward = unreal.MathLibrary.transform_direction(chair.get_actor_transform(), center)
            to_table = table.get_actor_location() - chair.get_actor_location()
            assert backward.x * to_table.x + backward.y * to_table.y < -1, (
                "Chair backrest faces the table"
            )
        if command["operation"] == "check":
            for actor in selected:
                for material in actor.static_mesh_component.get_materials():
                    while isinstance(material, unreal.MaterialInstanceConstant):
                        material = material.get_editor_property("parent")
                    textures = unreal.MaterialEditingLibrary.get_used_textures(material)
                    assert len(textures) >= 4, "Baked PBR map missing in UE"
                    linear = [t for t in textures if not t.get_editor_property("srgb")]
                    assert len(linear) >= 3, "PBR data texture color spaces incorrect"
        if command["operation"] == "check_preparation":
            mesh = selected[0].static_mesh_component.static_mesh
            subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
            receipt = json.loads((root / "receipts" / (command["asset_id"] + ".json")).read_text())
            count = subsystem.get_lod_count(mesh)
            assert count == receipt["lod_count"]
            triangles = [mesh.get_num_triangles(i) for i in range(count)]
            assert triangles[0] == receipt["triangles"]
            assert all(a > b for a, b in zip(triangles, triangles[1:]))
            collisions = subsystem.get_simple_collision_count(
                mesh
            ) + subsystem.get_convex_collision_count(mesh)
            assert collisions == receipt["collision_count"]
            (root / "preparation-native.json").write_text(
                json.dumps({"triangles": triangles, "colliders": collisions})
            )
        if command["operation"] == "check_usage_preset":
            from prompt_to_scene_unreal.diagnostics import textures_used

            textures = [
                t
                for m in selected[0].static_mesh_component.get_materials()
                for t in textures_used(m)
            ]
            assert len(textures) >= 8
            assert all(
                t.blueprint_get_size_x() == 512 and t.blueprint_get_size_y() == 512
                for t in textures
            )
        if command["operation"] == "capture_material":
            material = next(
                m
                for m in selected[0].static_mesh_component.get_materials()
                if unreal.EditorAssetLibrary.get_metadata_tag(m, "PromptToScene.MaterialName")
                == "Wood"
            )
            path = material.get_path_name().split(".")[0]
            file = Path(unreal.Paths.project_content_dir()) / (
                path.removeprefix("/Game/") + ".uasset"
            )
            (root / "authoring-material.json").write_text(
                json.dumps({"path": path, "file": str(file.resolve())})
            )
        if command["operation"] == "check_reuse":
            reference = json.loads((root / "authoring-material.json").read_text())
            assert any(
                m.get_path_name().split(".")[0] == reference["path"]
                for m in selected[0].static_mesh_component.get_materials()
            ), "Existing material was not reused"
        (root / "authoring-command-done").write_text("done")
    except Exception as error:
        finish(error)


handle = unreal.register_slate_post_tick_callback(tick)
