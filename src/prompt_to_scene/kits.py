"""Curated coherent prop sets with readable silhouettes and useful real-world proportions."""

from copy import deepcopy

from . import core, game_art, recipes, registry, styles, workflow

KITS = {
    "reading_corner": {
        "label": "薄荷阅读角",
        "style": "cozy",
        "description": "圆润薄荷漆面、浅暖木色、轻巧的阅读家具",
        "items": [
            {"kind": "chair", "variant": 0},
            {"kind": "table", "variant": 2, "parameters": {"width": 0.85, "depth": 0.65}},
            {"kind": "shelf", "variant": 2},
        ],
    },
    "village_market": {
        "label": "乡村集市",
        "style": "heritage",
        "description": "旧木、深铁件和交叉加固结构，适合村落摊位",
        "items": [
            {"kind": "table", "variant": 1},
            {"kind": "crate", "variant": 1},
            {"kind": "barrel", "variant": 1},
            {"kind": "sign", "variant": 1},
        ],
    },
    "makers_workshop": {
        "label": "工匠工作间",
        "style": "workshop",
        "description": "钢制支架、琥珀漆面和明确的柜体分区",
        "items": [
            {"kind": "table", "variant": 1},
            {"kind": "stool", "variant": 2},
            {"kind": "cabinet", "variant": 1},
            {"kind": "shelf", "variant": 1},
        ],
    },
}


def blueprint(project, kit, prefix, quality=None):
    if kit not in KITS:
        raise ValueError("Choose a kit from inspect_library")
    core.asset_id(prefix)
    chosen = KITS[kit]
    art = styles.preset(chosen["style"], quality or styles.read(project)["quality"])
    prepared = []
    for index, item in enumerate(chosen["items"]):
        asset = core.asset_id(prefix + "_" + item["kind"])
        brief = game_art.for_recipe(project, asset, item["kind"])
        script, recipe = recipes.prepare(
            item["kind"],
            {**item.get("parameters", {}), "variant": item["variant"]},
            style=brief["style"] if brief else art,
            art_design=brief,
            quality=quality,
        )
        recipe["kit"] = kit
        # Explicit, spaced initial positions make the set immediately reviewable.
        position = [index * 2.4, 0, 0]
        prepared.append((asset, script, recipe, position))
    return prepared, art


def create(project, kit, prefix, quality=None):
    from .authoring import submit_recipe

    prepared, art = blueprint(project, kit, prefix, quality)
    target = registry.resolve(project)
    tasks = []
    for asset, _, _, _ in prepared:
        info = core.status(target.project_file or target.root, asset)
        if info["status"] != "unknown":
            raise ValueError("Kit prefix is already in use; choose a new prefix")
    for asset, script, recipe, position in prepared:
        try:
            tasks.append(submit_recipe(project, asset, script, recipe, position))
        except Exception as error:
            return {"status": "partial", "tasks": tasks, "error": str(error), "kit": kit}
    return {
        "status": "building",
        "kit": kit,
        "style": deepcopy(art),
        "tasks": tasks,
        "created_utc": workflow.now(),
        "message": "Matching assets appear in a spaced row; place them with arrange_props.",
    }
