"""Executed inside a disposable Unreal Editor project by unreal_smoke_test.py."""

import json
from pathlib import Path

import prompt_to_scene_unreal as bridge

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
phase = json.loads((root / "smoke-phase.json").read_text())["phase"]
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if phase == "initial":
    assert levels.new_level("/Game/Smoke"), "Could not create fixture level"
else:
    assert levels.load_level("/Game/Smoke"), "Could not load fixture level"
bridge.import_pending()
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def result(asset_id):
    receipt = json.loads((root / f"receipts/{asset_id}.json").read_text())
    assert receipt["status"] == "imported", receipt
    matches = [
        a for a in actors.get_all_level_actors() if f"PTS.Asset:{asset_id}" in map(str, a.tags)
    ]
    assert len(matches) == 1, "Missing or duplicate actor"
    return receipt, matches[0]


if phase in {"initial", "revision"}:
    receipt, actor = result("crate")
    assert receipt["triangles"] == 1404, receipt
    assert abs(receipt["bounds_size"][2] - (1 if phase == "initial" else 1.25)) < 0.02, receipt
    location = actor.get_actor_location()
    assert abs(location.x - 200) < 0.01 and abs(location.y) < 0.01 and abs(location.z - 300) < 0.01
    assert receipt["collision_shapes"] == 1, receipt
    component = actor.static_mesh_component
    if phase == "initial":
        actor.set_actor_label("Artist label")
        actor.set_editor_property("tags", [*actor.tags, unreal.Name("User.Keep")])
        actor.set_actor_rotation(unreal.Rotator(yaw=27), False)
        assert abs(actor.get_actor_rotation().yaw - 27) < 0.01, "Fixture rotation was not set"
        actor.set_actor_scale3d(unreal.Vector(1.2, 1.2, 1.2))
        component.set_editor_property("cast_shadow", False)
        (root / "baseline.json").write_text(json.dumps(receipt))
    else:
        baseline = json.loads((root / "baseline.json").read_text())
        assert receipt["asset_path"] == baseline["asset_path"]
        assert receipt["actor_guid"] == baseline["actor_guid"]
        assert receipt["request_id"] != baseline["request_id"]
        assert actor.get_actor_label() == "Artist label"
        assert "User.Keep" in map(str, actor.tags)
        assert abs(actor.get_actor_rotation().yaw - 27) < 0.01
        assert abs(actor.get_actor_scale3d().x - 1.2) < 0.01
        assert not component.get_editor_property("cast_shadow")
        mesh = component.static_mesh
        material = next(
            mesh.get_material(i)
            for i in range(mesh.get_num_sections(0))
            if unreal.EditorAssetLibrary.get_metadata_tag(
                mesh.get_material(i), "PromptToScene.MaterialName"
            )
            == "Wood"
        )
        color = unreal.MaterialEditingLibrary.get_material_property_input_node(
            material, unreal.MaterialProperty.MP_BASE_COLOR
        ).get_editor_property("constant")
        assert color.g > color.r, "Green material revision missing"
    assert levels.save_current_level(), "Could not save fixture level"
else:
    for asset_id in ("textured_cube", "saved_cube"):
        receipt, actor = result(asset_id)
        assert receipt["triangles"] == 12 and receipt["collision_shapes"] == 0, receipt
        assert receipt["material_names"] == ["漆面 / Paint"], receipt
        mesh = actor.static_mesh_component.static_mesh
        material = mesh.get_material(0)
        library = unreal.MaterialEditingLibrary
        metallic = library.get_material_property_input_node(
            material, unreal.MaterialProperty.MP_METALLIC
        )
        roughness = library.get_material_property_input_node(
            material, unreal.MaterialProperty.MP_ROUGHNESS
        )
        assert abs(metallic.get_editor_property("r") - 0.2) < 0.001
        assert abs(roughness.get_editor_property("r") - 0.65) < 0.001
        base = library.get_material_property_input_node(
            material, unreal.MaterialProperty.MP_BASE_COLOR
        )
        assert base.get_editor_property("texture").get_editor_property("srgb")
        textures = library.get_used_textures(material)
        normals = [
            t
            for t in textures
            if t.get_editor_property("compression_settings")
            == unreal.TextureCompressionSettings.TC_NORMALMAP
        ]
        assert len(normals) == 1, "Normal texture missing"
        assert not normals[0].get_editor_property("srgb")
        assert normals[0].get_editor_property("flip_green_channel"), (
            "OpenGL -> DirectX normal conversion missing"
        )
        assert (
            library.get_material_property_input_node(material, unreal.MaterialProperty.MP_NORMAL)
            is not None
        )
(root / f"{phase}-passed.json").write_text(
    json.dumps({"result": "PASS", "unreal_version": unreal.SystemLibrary.get_engine_version()})
)
print("PTS_UNREAL_SMOKE_PASS " + phase)
