"""Native image/UI imports with stable Texture2D and SlateBrushAsset references."""

import hashlib
import json
import re
import struct

from .protocol import write_json


def validate(request, root):
    data = json.loads(request.get("image_json", "{}"))
    name = data.get("asset_id", "")
    revision = data.get("revision", "")
    if (
        data.get("schema_version") != 1
        or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name)
        or name != request.get("asset_id")
        or not re.fullmatch(r"[a-f0-9]{32}", revision)
    ):
        raise ValueError("Invalid image identity")
    if data.get("file") != f"images/{name}/{revision}/image.png":
        raise ValueError("Image file must match the retained revision")
    source = root / data["file"]
    if not source.resolve().is_relative_to(root.resolve()) or not source.is_file():
        raise ValueError("Image must stay inside the project state directory")
    if source.stat().st_size > 20 * 1024**2:
        raise ValueError("Image exceeds 20 MiB")
    content = source.read_bytes()
    if (
        hashlib.sha256(content).hexdigest() != data.get("sha256")
        or content[:8] != b"\x89PNG\r\n\x1a\n"
        or len(content) < 33
    ):
        raise ValueError("Prepared image is missing, changed or not a PNG")
    width, height = data.get("width"), data.get("height")
    if any(type(v) is not int or not 16 <= v <= 4096 for v in (width, height)) or struct.unpack(
        ">II", content[16:24]
    ) != (width, height):
        raise ValueError("Image dimensions do not match the manifest")
    if data.get("kind") not in {"icon", "button", "panel", "portrait", "background", "texture"}:
        raise ValueError("Unsupported image kind")
    if any(type(data.get(key)) is not bool for key in ("transparent", "pixel_art")):
        raise ValueError("Image flags must be booleans")
    border = data.get("border")
    if (
        not isinstance(border, list)
        or len(border) != 4
        or any(type(v) is not int or v < 0 for v in border)
        or border[0] + border[2] >= width
        or border[1] + border[3] >= height
    ):
        raise ValueError("Invalid nine-slice margins")
    if data["kind"] not in {"button", "panel"} and any(border):
        raise ValueError("Nine-slice is supported on button/panel assets")
    expected = data.get("expected_revision", "")
    if expected and not re.fullmatch(r"[a-f0-9]{32}", expected):
        raise ValueError("Invalid expected image revision")
    path = root / "image-receipts" / (name + ".json")
    current = json.loads(path.read_text()) if path.exists() else None
    if (current["revision"] if current else "") not in {expected, revision}:
        raise ValueError("Image changed after this import was queued; publish again to update it")
    if current and (current["kind"] == "texture") != (data["kind"] == "texture"):
        raise ValueError("Choose a new asset ID when changing between UI and surface texture")
    return data, source, current


def execute(request, root):
    import unreal

    data, source, current = validate(request, root)
    library = unreal.EditorAssetLibrary
    name = data["asset_id"]
    destination = "/Game/PromptToScene/Images/" + name
    texture_path = (current or {}).get("texture_path") or destination + "/T_" + name
    brush_path = (current or {}).get("brush_path") or destination + "/B_" + name
    texture = unreal.load_asset(texture_path) if library.does_asset_exist(texture_path) else None
    brush_asset = unreal.load_asset(brush_path) if library.does_asset_exist(brush_path) else None
    if current and not texture:
        raise ValueError(
            "Managed texture moved or was removed; restore its recorded path before updating"
        )
    for asset, kind in ((texture, unreal.Texture2D), (brush_asset, unreal.SlateBrushAsset)):
        if asset and (
            not isinstance(asset, kind)
            or library.get_metadata_tag(asset, "PromptToScene.Image") != name
        ):
            raise ValueError("Image destination contains an unowned asset")
    task = unreal.AssetImportTask()
    task.filename = str(source)
    task.destination_path, task.destination_name = texture_path.rsplit("/", 1)
    # Receipts use package paths without .Object suffix.
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    task.factory = unreal.TextureFactory()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture = unreal.load_asset(texture_path)
    if not isinstance(texture, unreal.Texture2D):
        raise RuntimeError("Native texture import did not produce a Texture2D")
    ui = data["kind"] != "texture"
    properties = {
        "srgb": True,
        "compression_settings": unreal.TextureCompressionSettings.TC_EDITOR_ICON
        if ui
        else unreal.TextureCompressionSettings.TC_DEFAULT,
        "compression_no_alpha": False,
        "lod_group": unreal.TextureGroup.TEXTUREGROUP_UI
        if ui
        else unreal.TextureGroup.TEXTUREGROUP_WORLD,
        "mip_gen_settings": unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS
        if ui
        else unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP,
        "filter": unreal.TextureFilter.TF_NEAREST
        if data["pixel_art"]
        else unreal.TextureFilter.TF_BILINEAR,
        "address_x": unreal.TextureAddress.TA_CLAMP if ui else unreal.TextureAddress.TA_WRAP,
        "address_y": unreal.TextureAddress.TA_CLAMP if ui else unreal.TextureAddress.TA_WRAP,
        "max_texture_size": 4096,
    }
    for key, value in properties.items():
        texture.set_editor_property(key, value)
    library.set_metadata_tag(texture, "PromptToScene.Image", name)
    library.set_metadata_tag(texture, "PromptToScene.ImageRevision", data["revision"])
    library.save_loaded_asset(texture)
    if ui:
        if not brush_asset:
            brush_asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                brush_path.rsplit("/", 1)[1],
                brush_path.rsplit("/", 1)[0],
                unreal.SlateBrushAsset,
                unreal.SlateBrushAssetFactory(),
            )
        if not brush_asset:
            raise RuntimeError("Could not create native UI brush")
        library.set_metadata_tag(brush_asset, "PromptToScene.Image", name)
        brush = unreal.SlateBrush()
        brush.set_editor_property("resource_object", texture)
        # FDeprecateSlateVector2D is the native FSlate brush dimension wrapper in UE 5.7.
        size = unreal.DeprecateSlateVector2D()
        size.set_editor_property("x", float(data["width"]))
        size.set_editor_property("y", float(data["height"]))
        brush.set_editor_property("image_size", size)
        border = data["border"]
        brush.set_editor_property(
            "draw_as",
            unreal.SlateBrushDrawType.BOX if any(border) else unreal.SlateBrushDrawType.IMAGE,
        )
        brush.set_editor_property(
            "margin",
            unreal.Margin(
                border[0] / data["width"],
                border[1] / data["height"],
                border[2] / data["width"],
                border[3] / data["height"],
            ),
        )
        brush_asset.set_editor_property("brush", brush)
        library.save_loaded_asset(brush_asset)
    result = dict(
        asset_id=name,
        revision=data["revision"],
        kind=data["kind"],
        texture_path=texture_path,
        brush_path=brush_path if ui else "",
        width=texture.blueprint_get_size_x(),
        height=texture.blueprint_get_size_y(),
        border=data["border"],
        engine="unreal",
        request_id=request["request_id"],
    )
    if (result["width"], result["height"]) != (data["width"], data["height"]):
        raise RuntimeError("Native texture dimensions differ from the prepared image")
    write_json(root / "image-receipts" / (name + ".json"), result)
    return {"image": result}
