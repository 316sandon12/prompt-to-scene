"""Authoring operations shared by the MCP interface and local dashboard."""

from copy import deepcopy

from . import core, design, kits, preparation, recipes, styles, workflow


def catalog(project=None):
    return {
        "styles": styles.PRESETS,
        "quality": styles.QUALITY,
        "recipes": {
            k: {"parameters": v, "parts": design.PARTS[k]} for k, v in recipes.DEFAULTS.items()
        },
        "project_style": styles.read(project),
        "kits": kits.KITS,
        "variants": design.VARIANTS,
        "preparation_defaults": preparation.options(),
    }


def set_style(project=None, preset=None, quality=None, overrides=None, reference_asset=None):
    if reference_asset:
        info = workflow.inspect_asset(project, reference_asset)
        recipe = (info.get("metadata") or {}).get("recipe") or {}
        art = deepcopy(recipe.get("style"))
        if not art:
            raise ValueError(
                "This asset has no saved art direction; use an explicit palette or material binding"
            )
        chosen = {k: art[k] for k in ("palette", "roundness", "taper", "wear", "material_bindings")}
        if "color" in recipe["parameters"]:
            chosen["palette"]["wood"] = recipe["parameters"]["color"]
        if "metal_color" in recipe["parameters"]:
            chosen["palette"]["metal"] = recipe["parameters"]["metal_color"]
        chosen.update(overrides or {})
        return styles.save(project, preset or art["preset"], quality or art["quality"], chosen)
    return styles.save(project, preset, quality, overrides)


def create(project, kind, asset_id, parameters=None, position=None, collider=True, quality=None):
    script, recipe = recipes.prepare(kind, parameters, style=styles.read(project), quality=quality)
    return submit_recipe(project, asset_id, script, recipe, position, collider)


def submit_recipe(project, asset_id, script, recipe, position=None, collider=True):
    quality = recipe["style"]["quality"]
    config = (
        None
        if quality == "draft"
        else preparation.options(
            {"ground": False, "collision": "convex" if collider else "none"}, quality
        )
    )
    return workflow.submit(
        project, asset_id, script, position, collider, recipe=recipe, preparation=config
    )


def optimize(project, asset_id, settings=None):
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Wait for the current asset to be imported before preparing it")
    from pathlib import Path

    source = Path(info["source_blend"])
    original = source.with_name("original.blend")
    if original.exists():
        source = original
    retained_settings = (info["metadata"].get("preparation") or {}).get("settings", {})
    config = preparation.options(
        {**retained_settings, **(settings or {})}, styles.read(project)["quality"]
    )
    return workflow.submit(
        project,
        asset_id,
        "",
        blend_file=str(source),
        collider=config["collision"] != "none",
        preparation=config,
        recipe=info["metadata"].get("recipe"),
        provenance=info["metadata"].get("provenance"),
    )


def current_recipe(project, asset_id):
    info = workflow.inspect_asset(project, asset_id)
    if info["current"].get("status") != "imported":
        raise ValueError("Wait for a successful import before editing this asset")
    recipe = (info.get("metadata") or {}).get("recipe")
    if not recipe:
        raise ValueError(
            "Custom asset: inspect its source and use build_asset; semantic edits require a recipe"
        )
    return info, recipe


def revise(project, asset_id, parameters=None, apply_project_style=False, quality=None):
    info, recipe = current_recipe(project, asset_id)
    script, updated = recipes.revise(
        recipe,
        parameters,
        style=styles.read(project) if apply_project_style else None,
        quality=quality,
    )
    return submit_recipe(
        project, asset_id, script, updated, collider=info["metadata"].get("collider", True)
    )


def edit_part(project, asset_id, part, changes=None, lock_geometry=None, lock_material=None):
    info = workflow.inspect_asset(project, asset_id)
    if not (info.get("metadata") or {}).get("recipe"):
        from . import parts

        return parts.edit(
            project,
            asset_id,
            part,
            changes,
            lock_geometry=lock_geometry,
            lock_material=lock_material,
        )
    info, recipe = current_recipe(project, asset_id)
    if part == "all":
        updated = recipe
        for name in design.PARTS[recipe["kind"]]:
            script, updated = recipes.edit_part(
                updated, name, changes, lock_geometry, lock_material
            )
    else:
        script, updated = recipes.edit_part(recipe, part, changes, lock_geometry, lock_material)
    return submit_recipe(
        project, asset_id, script, updated, collider=info["metadata"].get("collider", True)
    )


def create_set(project, items):
    if not isinstance(items, list) or not 1 <= len(items) <= 8:
        raise ValueError(
            "A prop set contains one to eight designs; use arrangement for repeated instances"
        )
    art = styles.read(project)
    prepared, names = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {
            "kind",
            "asset_id",
            "parameters",
            "position",
            "collider",
        }:
            raise ValueError(
                "Each design needs kind, asset_id and optional parameters/position/collider"
            )
        name = core.asset_id(item["asset_id"])
        if name in names:
            raise ValueError("Each design needs a unique asset ID")
        names.add(name)
        core.position_values(item.get("position"))
        script, recipe = recipes.prepare(item["kind"], item.get("parameters"), style=art)
        prepared.append((item, script, recipe))
    tasks = []
    try:
        for item, script, recipe in prepared:
            tasks.append(
                submit_recipe(
                    project,
                    item["asset_id"],
                    script,
                    recipe,
                    item.get("position"),
                    item.get("collider", True),
                )
            )
    except Exception as error:
        return {
            "status": "partial",
            "tasks": tasks,
            "error": str(error),
            "message": "Already submitted tasks remain valid; resume only missing designs",
        }
    return {
        "status": "building",
        "tasks": tasks,
        "style": art,
        "message": "Wait for each exact import, then arrange_props to place repeated instances",
    }
