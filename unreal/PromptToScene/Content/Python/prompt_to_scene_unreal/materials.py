"""Explicit opaque PBR mapping. Generated material graphs belong to the bridge."""

import hashlib

import unreal

from .protocol import digest


def import_texture(source, target, name, normal, linear=False, prefix="T_"):
    if not name:
        return None
    fingerprint = hashlib.sha256((source / name).read_bytes()).hexdigest() + str((normal, linear))
    path = target + "/" + prefix + name.removeprefix("tex_").removesuffix(".png")
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        old = unreal.load_asset(path)
        if (
            isinstance(old, unreal.Texture2D)
            and unreal.EditorAssetLibrary.get_metadata_tag(old, "PromptToScene.ContentHash")
            == fingerprint
        ):
            return old
    task = unreal.AssetImportTask()
    task.filename = str(source / name)
    task.destination_path = target
    task.destination_name = prefix + name.removeprefix("tex_").removesuffix(".png")
    task.factory = unreal.TextureFactory()
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    results = task.get_objects()
    if len(results) != 1 or not isinstance(results[0], unreal.Texture2D):
        raise RuntimeError("Texture import failed: " + name)
    texture = results[0]
    texture.set_editor_property("srgb", not normal and not linear)
    texture.set_editor_property(
        "compression_settings",
        (
            unreal.TextureCompressionSettings.TC_NORMALMAP
            if normal
            else unreal.TextureCompressionSettings.TC_DEFAULT
        ),
    )
    # Blender tangent normals use OpenGL +Y; Unreal expects DirectX -Y.
    texture.set_editor_property("flip_green_channel", normal)
    texture.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
    texture.set_editor_property("address_y", unreal.TextureAddress.TA_WRAP)
    texture.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR)
    unreal.EditorAssetLibrary.set_metadata_tag(texture, "PromptToScene.ContentHash", fingerprint)
    if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
        raise RuntimeError("Could not save texture: " + name)
    return texture


def build_material(data, source, target, layout=None):
    layout = layout or {
        "materials": "",
        "textures": "",
        "material_prefix": "M_",
        "texture_prefix": "T_",
    }
    texture_target = (target + "/" + layout["textures"]).rstrip("/")
    target = (target + "/" + layout["materials"]).rstrip("/")
    unreal.EditorAssetLibrary.make_directory(target)
    unreal.EditorAssetLibrary.make_directory(texture_target)
    if data.get("reuse_path"):
        path = data["reuse_path"]
        if not path.startswith("/Game/") or ".." in path:
            raise ValueError("Reusable material must be inside /Game/")
        existing = unreal.EditorAssetLibrary.load_asset(path)
        if not isinstance(existing, unreal.MaterialInterface):
            raise ValueError("Reusable material is missing: " + path)
        return existing
    name = layout["material_prefix"] + digest(data["name"])
    path = target + "/" + name
    material = (
        unreal.EditorAssetLibrary.load_asset(path)
        if unreal.EditorAssetLibrary.does_asset_exist(path)
        else None
    )
    if material is None:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name, target, unreal.Material, unreal.MaterialFactoryNew()
        )
    if not isinstance(material, unreal.Material):
        raise RuntimeError("Managed material path contains an incompatible asset")
    library = unreal.MaterialEditingLibrary
    library.delete_all_material_expressions(material)
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("two_sided", False)

    def node(kind, x, y):
        return library.create_material_expression(material, kind, x, y)

    def connect(expression, property_):
        if not library.connect_material_property(expression, "", property_):
            raise RuntimeError("Could not connect material property: " + str(property_))

    uv = node(unreal.MaterialExpressionTextureCoordinate, -1250, -650)
    scale = node(unreal.MaterialExpressionScalarParameter, -1250, -500)
    scale.set_editor_property("parameter_name", "PTS_UVScale")
    scale.set_editor_property("default_value", 1.0)
    scaled_uv = node(unreal.MaterialExpressionMultiply, -1000, -600)
    library.connect_material_expressions(uv, "", scaled_uv, "A")
    library.connect_material_expressions(scale, "", scaled_uv, "B")

    base = import_texture(
        source, texture_target, data["base_color_texture"], False, prefix=layout["texture_prefix"]
    )
    tint = node(unreal.MaterialExpressionVectorParameter, -750, -450)
    tint.set_editor_property("parameter_name", "PTS_Color")
    tint.set_editor_property("default_value", unreal.LinearColor(*data["color"]))
    if base:
        color = node(unreal.MaterialExpressionTextureSample, -500, -250)
        color.set_editor_property("texture", base)
        library.connect_material_expressions(scaled_uv, "", color, "Coordinates")
        color.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        multiply_color = node(unreal.MaterialExpressionMultiply, -250, -250)
        library.connect_material_expressions(color, "RGB", multiply_color, "A")
        library.connect_material_expressions(tint, "RGB", multiply_color, "B")
        color = multiply_color
    else:
        color = tint
    connect(color, unreal.MaterialProperty.MP_BASE_COLOR)
    for key, value, prop, y in (
        ("metallic_texture", data["metallic"], unreal.MaterialProperty.MP_METALLIC, -50),
        ("roughness_texture", data["roughness"], unreal.MaterialProperty.MP_ROUGHNESS, 100),
    ):
        texture = import_texture(
            source,
            texture_target,
            data.get(key, ""),
            False,
            linear=True,
            prefix=layout["texture_prefix"],
        )
        if texture:
            scalar = node(unreal.MaterialExpressionTextureSample, -500, y)
            scalar.set_editor_property("texture", texture)
            library.connect_material_expressions(scaled_uv, "", scalar, "Coordinates")
            scalar.set_editor_property(
                "sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
            )
            if not library.connect_material_property(scalar, "R", prop):
                raise RuntimeError("Could not connect PBR map: " + key)
        else:
            scalar = node(unreal.MaterialExpressionScalarParameter, -250, y)
            scalar.set_editor_property(
                "parameter_name", "PTS_Roughness" if key == "roughness_texture" else "PTS_Metallic"
            )
            scalar.set_editor_property("default_value", value)
            connect(scalar, prop)
    normal = import_texture(
        source, texture_target, data["normal_texture"], True, prefix=layout["texture_prefix"]
    )
    if normal:
        sample = node(unreal.MaterialExpressionTextureSample, -750, 250)
        sample.set_editor_property("texture", normal)
        library.connect_material_expressions(scaled_uv, "", sample, "Coordinates")
        sample.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        strength = node(unreal.MaterialExpressionConstant3Vector, -750, 500)
        strength.set_editor_property(
            "constant", unreal.LinearColor(data["normal_strength"], data["normal_strength"], 1, 1)
        )
        multiply = node(unreal.MaterialExpressionMultiply, -450, 250)
        normalize = node(unreal.MaterialExpressionNormalize, -200, 250)
        if not all(
            (
                library.connect_material_expressions(sample, "RGB", multiply, "A"),
                library.connect_material_expressions(strength, "", multiply, "B"),
                library.connect_material_expressions(multiply, "", normalize, "VectorInput"),
            )
        ):
            raise RuntimeError("Could not connect normal-map graph")
        connect(normalize, unreal.MaterialProperty.MP_NORMAL)
    unreal.EditorAssetLibrary.set_metadata_tag(material, "PromptToScene.MaterialName", data["name"])
    library.recompile_material(material)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("Could not save material: " + data["name"])
    return material
