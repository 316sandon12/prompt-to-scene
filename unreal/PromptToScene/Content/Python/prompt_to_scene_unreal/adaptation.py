"""Reference-driven material-instance variants, selective assignment and durable undo."""

import hashlib
import json
import re

import unreal

from .protocol import write_json

LIB = unreal.MaterialEditingLibrary
ALIASES = {
    "color": ("PTS_Color", "BaseColor", "Base Color", "Color", "Tint"),
    "roughness": ("PTS_Roughness", "Roughness"),
    "texture_scale": ("PTS_UVScale", "UVScale", "Tiling", "TextureScale"),
}


def material_values(material):
    vectors = set(map(str, LIB.get_vector_parameter_names(material)))
    scalars = set(map(str, LIB.get_scalar_parameter_names(material)))
    instance = isinstance(material, unreal.MaterialInstanceConstant)
    values = {}
    for field, aliases in ALIASES.items():
        name = next((n for n in aliases if n in (vectors if field == "color" else scalars)), None)
        if not name:
            continue
        if field == "color":
            fn = (
                LIB.get_material_instance_vector_parameter_value
                if instance
                else LIB.get_material_default_vector_parameter_value
            )
            v = fn(material, name)
            value = [v.r, v.g, v.b, v.a]
        else:
            fn = (
                LIB.get_material_instance_scalar_parameter_value
                if instance
                else LIB.get_material_default_scalar_parameter_value
            )
            value = fn(material, name)
        values[field] = {"parameter": name, "value": value}
    return values


def signature(material):
    # Native asset contents include shader graphs, inherited settings and texture references.
    path = (
        str(
            unreal.PackageTools.package_name_to_filename(
                material.get_path_name().split(".")[0], ".uasset"
            )
        )
        if hasattr(unreal.PackageTools, "package_name_to_filename")
        else ""
    )
    from pathlib import Path

    if not path:
        package = material.get_path_name().split(".")[0]
        if package.startswith("/Game/"):
            path = str(Path(unreal.Paths.project_content_dir()) / (package[6:] + ".uasset"))
    contents = Path(path).read_bytes() if path and Path(path).is_file() else b""
    return hashlib.sha256(
        contents + json.dumps(material_values(material), sort_keys=True).encode()
    ).hexdigest()


def asset(path, cls):
    if not isinstance(path, str) or not path.startswith("/Game/") or ".." in path:
        raise ValueError("Choose an asset inside /Game/")
    obj = unreal.load_asset(path)
    if not isinstance(obj, cls):
        raise ValueError("Choose " + cls.__name__ + ": " + path)
    return obj


def reference(path):
    obj = asset(path, unreal.Object)
    if isinstance(obj, unreal.MaterialInterface):
        return obj
    if isinstance(obj, unreal.StaticMesh) and obj.get_num_sections(0):
        return obj.get_material(0)
    raise ValueError("Choose a material or StaticMesh as reference")


def execute(request, c, root):
    if c["mode"] == "preview":
        paths = c.get("paths", [])
        if not 1 <= len(paths) <= 20:
            raise ValueError("Choose 1–20 static meshes")
        source = reference(c["path"])
        values = material_values(source)
        fields = c.get("slots", list(ALIASES))
        if set(fields) - ALIASES.keys():
            raise ValueError("Unsupported adaptation field")
        plan = dict(
            plan_id=request["request_id"],
            reference=c["path"],
            status="preview",
            entries=[],
            assets=[],
            warnings=[],
        )
        folder = "/Game/PromptToScene/Adaptation/" + plan["plan_id"]
        unreal.EditorAssetLibrary.make_directory(folder)
        for index, path in enumerate(dict.fromkeys(paths)):
            mesh = asset(path, unreal.StaticMesh)
            variant_path = folder + "/SM_" + str(index)
            variant = unreal.EditorAssetLibrary.duplicate_asset(path, variant_path)
            if not isinstance(variant, unreal.StaticMesh):
                raise RuntimeError("Could not make preview mesh")
            for slot, row in enumerate(mesh.get_editor_property("static_materials")):
                before = row.material_interface
                if not before:
                    continue
                supported = material_values(before)
                applied = [field for field in fields if field in values and field in supported]
                if not applied:
                    plan["warnings"].append(
                        path + " slot " + str(slot) + ": no recognized material parameters"
                    )
                    continue
                if len(applied) != len(fields):
                    plan["warnings"].append(
                        path
                        + " slot "
                        + str(slot)
                        + ": applied "
                        + ", ".join(applied)
                        + "; unsupported fields skipped"
                    )
                if len(plan["entries"]) >= 200:
                    raise ValueError("At most 200 material slots per adaptation")
                identifier = str(len(plan["entries"]))
                name = "MI_" + identifier
                after = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
                    name,
                    folder,
                    unreal.MaterialInstanceConstant,
                    unreal.MaterialInstanceConstantFactoryNew(),
                )
                LIB.set_material_instance_parent(after, before)
                for field in applied:
                    parameter = supported[field]["parameter"]
                    value = values[field]["value"]
                    # UE 5.7's vector setter mutates correctly but always returns false.
                    # Read the native value back instead of trusting that return flag.
                    (
                        LIB.set_material_instance_vector_parameter_value(
                            after, parameter, unreal.LinearColor(*value)
                        )
                        if field == "color"
                        else LIB.set_material_instance_scalar_parameter_value(
                            after, parameter, value
                        )
                    )
                    actual = material_values(after).get(field, {}).get("value")
                    expected_values = value if isinstance(value, list) else [value]
                    actual_values = actual if isinstance(actual, list) else [actual]
                    if len(actual_values) != len(expected_values) or any(
                        a is None or abs(a - b) > 0.0001
                        for a, b in zip(actual_values, expected_values)
                    ):
                        raise RuntimeError(
                            "Material parameter could not be overridden: " + parameter
                        )
                LIB.update_material_instance(after)
                if not unreal.EditorAssetLibrary.save_loaded_asset(after, only_if_is_dirty=False):
                    raise RuntimeError("Could not save material variant")
                variant.set_material(slot, after)
                plan["entries"].append(
                    dict(
                        id=identifier,
                        path=path,
                        slot=slot,
                        before=before.get_path_name(),
                        after=after.get_path_name(),
                        fields=applied,
                        before_hash=signature(before),
                        after_hash=signature(after),
                        status="planned",
                    )
                )
            unreal.EditorAssetLibrary.save_loaded_asset(variant, only_if_is_dirty=False)
            plan["assets"].append(dict(path=path, variant=variant_path))
    else:
        if c["mode"] not in {"apply", "undo"} or not re.fullmatch(
            "[a-f0-9]{32}", c.get("plan_id", "")
        ):
            raise ValueError("Choose a saved preview to apply or undo")
        plan = json.loads((root / "adaptation" / (c["plan_id"] + ".json")).read_text())
        chosen = [
            row
            for row in plan["entries"]
            if (not c.get("slots") or row["id"] in c["slots"])
            and (row["status"] == "applied" if c["mode"] == "undo" else row["status"] != "applied")
        ]
        for row in chosen:
            mesh = asset(row["path"], unreal.StaticMesh)
            expected = row["after"] if c["mode"] == "undo" else row["before"]
            current = mesh.get_material(row["slot"])
            if not current or current.get_path_name() != expected:
                raise ValueError("Material assignment changed since preview: " + row["path"])
            if c["mode"] == "apply" and (
                signature(current) != row["before_hash"]
                or signature(asset(row["after"], unreal.MaterialInterface)) != row["after_hash"]
            ):
                raise ValueError("Material content changed; make a new preview")
            asset(row["before"] if c["mode"] == "undo" else row["after"], unreal.MaterialInterface)
        with unreal.ScopedEditorTransaction("Prompt-to-Scene reference adaptation"):
            for row in chosen:
                mesh = asset(row["path"], unreal.StaticMesh)
                mesh.modify()
                mesh.set_material(
                    row["slot"],
                    asset(
                        row["before"] if c["mode"] == "undo" else row["after"],
                        unreal.MaterialInterface,
                    ),
                )
                if not unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False):
                    raise RuntimeError("Could not save " + row["path"])
                row["status"] = "undone" if c["mode"] == "undo" else "applied"
                write_json(root / "adaptation" / (plan["plan_id"] + ".json"), plan)
        plan["status"] = "undone" if c["mode"] == "undo" else "applied"
    write_json(root / "adaptation" / (plan["plan_id"] + ".json"), plan)
    return {
        "development": dict(
            command="adapt",
            plan_id=plan["plan_id"],
            warnings=plan["warnings"],
            changed=sum(row["status"] == "applied" for row in plan["entries"]),
            message="Reference adaptation: " + plan["status"],
        )
    }
