"""Read actual native image properties and retained brush references in the UE editor."""

import json
from pathlib import Path

from prompt_to_scene_unreal import import_pending

import unreal

root = Path(unreal.Paths.project_dir()).resolve() / ".prompt-to-scene"
retained = None
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
(root / "image-ready").write_text("ready")


def tick(_delta):
    global retained
    try:
        import_pending()
        path = root / "image-command.json"
        if not path.exists():
            return
        command = json.loads(path.read_text())
        path.unlink()
        if command["operation"] == "stop":
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            unreal.SystemLibrary.quit_editor()
            return
        row = json.loads((root / "image-receipts" / (command["asset_id"] + ".json")).read_text())
        texture = unreal.load_asset(row["texture_path"])
        brush_asset = unreal.load_asset(row["brush_path"])
        brush = brush_asset.get_editor_property("brush")
        assert texture.get_editor_property("srgb")
        assert texture.get_editor_property("lod_group") == unreal.TextureGroup.TEXTUREGROUP_UI
        assert (
            texture.get_editor_property("mip_gen_settings")
            == unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS
        )
        assert texture.blueprint_get_size_x() == 128 and texture.blueprint_get_size_y() == 64
        assert brush.resource_object == texture and brush.draw_as == unreal.SlateBrushDrawType.BOX
        margin = brush.margin
        assert [margin.left, margin.top, margin.right, margin.bottom] == [
            8 / 128,
            4 / 64,
            12 / 128,
            6 / 64,
        ]
        if command["operation"] == "retain":
            retained = (texture, brush_asset)
        if command["operation"] == "verify":
            assert retained == (texture, brush_asset), "Existing native image references changed"
        (root / "image-command-done").write_text("done")
    except Exception as error:
        (root / "image-error.txt").write_text(str(error))
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
        unreal.SystemLibrary.quit_editor()


handle = unreal.register_slate_post_tick_callback(tick)
