"""Original art benchmarks with related items, native UI and a playable crafting loop."""

from . import (
    art_directions,
    art_samples,
    background,
    core,
    creations,
    development,
    game_art,
    gameplay,
    preparation,
    registry,
    styles,
    workflow,
)

PARTS = {
    "cottage": ("Timber apothecary", [0, 0, 0]),
    "workbench": ("Brass-trimmed workbench", [0, 0.55, 0]),
    "shelf": ("Glazed jar display", [-1.35, 1.35, 0]),
    "lantern": ("Jade lantern", [0.95, 1.25, 0]),
    "herb": ("Sage bundle", [-0.55, 0.28, 0.93]),
    "bottle": ("Porcelain bottle", [0.32, 0.28, 0.93]),
    "potion": ("Forest remedy", [1.25, 0.4, 0]),
}
NOTES = (
    "Jade glaze, satin brass, oiled walnut, linen bindings; rounded functional joinery, "
    "broad readable silhouettes and restrained surface detail. "
    "Compare at the actual game camera distance."
)


def catalog(project=None):
    """Inspect the original editable art set and saved installations; no paid service is used."""
    result = {
        "kits": [
            dict(
                kit_id=k,
                name=v["name"],
                assets=list(PARTS),
                art_direction=v["notes"],
                license="MIT",
            )
            for k, v in art_directions.DIRECTIONS.items()
        ]
    }
    if project is not None or registry.read().get("active"):
        result["installed"] = [
            core.read_optional_json(p)
            for p in sorted((game_art.root(project) / "art-kits").glob("*.json"))
        ]
    return result


def create(
    project,
    prefix="apothecary",
    kit_id="forest_apothecary",
    origin=None,
    gameplay_enabled=True,
    adopt_theme=False,
):
    """Make seven editable original assets, three rendered icons/items and native UI.

    gameplay_enabled connects collect/craft/use/save; an existing player/controller can call
    the normal range-checked interactions. origin is target-engine XYZ meters. adopt_theme
    explicitly adopts the kit palette for future project UI. Existing project lighting and
    controllers are retained; use game-camera review for final appearance.
    """
    art_directions.settings(kit_id)
    core.asset_id(prefix)
    for kind in PARTS:
        core.asset_id(prefix + "_" + kind + "_model")
    if type(gameplay_enabled) is not bool or type(adopt_theme) is not bool:
        raise ValueError("Kit options must be booleans")
    root = game_art.root(project)
    previous = core.read_optional_json(root / "art-kits" / (prefix + ".json"))
    if previous:
        return {
            "status": "completed",
            **previous,
            "message": "This set already exists; edit its retained assets or choose a new prefix.",
        }
    for kind in PARTS:
        name = prefix + "_" + kind + "_model"
        if workflow.inspect_asset(project, name)["current"].get("status") != "unknown":
            raise ValueError("An asset uses this prefix. Resume its task or choose a new prefix.")
    return background.submit(
        project,
        "art_kit",
        dict(
            prefix=prefix,
            kit_id=kit_id,
            origin=core.position_values(origin),
            gameplay_enabled=gameplay_enabled,
            adopt_theme=adopt_theme,
        ),
        prefix,
    )


def rule_settings(prefix):
    herb, bottle, potion = [prefix + "_" + k for k in ("herb", "bottle", "potion")]
    return dict(
        title="Forest apothecary",
        item_ids=[herb, bottle, potion],
        initial_health=40,
        screen_ids=[prefix + "_" + kind for kind in ("inventory", "hud", "pause")],
        rules=[
            dict(
                rule_id="collect_herb",
                label="Collect sage",
                trigger="interact",
                asset_id=herb + "_model",
                rewards=[dict(item_id=herb, quantity=6)],
                once=True,
            ),
            dict(
                rule_id="collect_bottle",
                label="Collect bottles",
                trigger="interact",
                asset_id=bottle + "_model",
                rewards=[dict(item_id=bottle, quantity=3)],
                once=True,
            ),
            dict(
                rule_id="craft_potion",
                label="Brew remedy (2 sage + 1 bottle)",
                trigger="craft",
                costs=[dict(item_id=herb, quantity=2), dict(item_id=bottle, quantity=1)],
                rewards=[dict(item_id=potion, quantity=1)],
            ),
            dict(
                rule_id="brew_at_table",
                label="Brew remedy",
                trigger="interact",
                asset_id=prefix + "_workbench_model",
                costs=[dict(item_id=herb, quantity=2), dict(item_id=bottle, quantity=1)],
                rewards=[dict(item_id=potion, quantity=1)],
            ),
            dict(
                rule_id="use_potion",
                label="Drink remedy (+30 health)",
                trigger="use",
                item_id=potion,
                costs=[dict(item_id=potion, quantity=1)],
                heal=30,
            ),
        ],
    )


def run(job, prefix, kit_id, origin, gameplay_enabled, adopt_theme):
    spec = art_directions.settings(kit_id)
    selected = art_directions.catalog(job.project)["selected"]
    palette = selected["theme"] if selected and selected["kit_id"] == kit_id else None
    if palette:
        spec["theme"] = palette
    labels = dict(zip(PARTS, spec["labels"]))
    engine = registry.resolve(job.project).engine
    root = game_art.root(job.project)
    assets = []
    for kind, (name, local) in PARTS.items():
        asset = prefix + "_" + kind + "_model"
        job.update(stage="Making " + spec["name"] + " · " + labels[kind])
        script = art_directions.source(kit_id, kind, palette)
        position = [local[0], local[2], -local[1]] if engine == "unity" else local
        position = [a + b for a, b in zip(position, origin)]
        settings = preparation.options(
            dict(
                ground=False,
                collision="none" if kind == "cottage" else "box",
                triangle_budget=50000,
                texture_size=512,
                lod_ratios=[],
            )
        )
        result = creations.step(
            job,
            "model_" + kind,
            lambda: workflow.submit(
                job.project,
                asset,
                script,
                position,
                preparation=settings,
                provenance={
                    "license": "MIT",
                    "source": "Prompt-to-Scene original art kit",
                    "art_kit": kit_id,
                    "art_direction": spec["notes"],
                },
            ),
        )
        assets.append(dict(asset_id=asset, request_id=result["request_id"], kind=kind))
    if adopt_theme:
        art_samples.theme(
            job.project, {k: v for k, v in spec["theme"].items() if k in art_samples.DEFAULT_THEME}
        )
    for kind in ("herb", "bottle", "potion"):
        item_id = prefix + "_" + kind
        job.update(stage="Linking matching item and icon · " + kind)
        creations.step(
            job,
            "item_" + kind,
            lambda: creations.create_item(
                job.project,
                item_id,
                model_asset_id=item_id + "_model",
                name=labels[kind],
                description="Restores 30 health."
                if kind == "potion"
                else "Crafting material · " + labels[kind],
                place_pickup=False,
            ),
        )
    items = [prefix + "_" + kind for kind in ("herb", "bottle", "potion")]
    for kind in ("inventory", "hud", "pause"):
        creations.step(
            job,
            "screen_" + kind,
            lambda: creations.create_ui(
                job.project, prefix + "_" + kind, kind, items, theme=spec["theme"]
            ),
        )
    if gameplay_enabled:
        for kind, interaction in (
            ("herb", "pickup"),
            ("bottle", "pickup"),
            ("workbench", "switch"),
        ):
            creations.step(
                job,
                "interaction_" + kind,
                lambda: development.configure(
                    job.project,
                    prefix + "_" + kind + "_model",
                    interaction,
                    label="Brew remedy" if kind == "workbench" else "Collect " + kind,
                    event_id=prefix + "_" + kind,
                ),
            )
        creations.step(
            job,
            "gameplay",
            lambda: gameplay.configure(job.project, prefix, themed_rules(prefix, spec)),
        )
    potion = core.read_optional_json(root / "game-items" / (prefix + "_potion.json"))
    if not adopt_theme and "sample_saved" not in job.state:
        job.update(sample_saved=None)
    if "sample_saved" not in job.state:
        from . import image_assets

        preview = image_assets.preview(
            job.project, potion["icon_asset_id"], potion["icon_revision"]
        )
        sample = art_samples.save(
            job.project,
            spec["name"] + " material benchmark",
            "material",
            preview["path"],
            spec["notes"],
            sample_id=prefix + "_benchmark",
        )
        job.update(sample_saved=sample["sample_id"])
    row = dict(
        prefix=prefix,
        kit_id=kit_id,
        assets=assets,
        item_ids=items,
        flow_id=prefix if gameplay_enabled else None,
        sample_id=job.state["sample_saved"],
        benchmark_icon=dict(asset_id=potion["icon_asset_id"], revision=potion["icon_revision"]),
        style_snapshot=styles.read(job.project),
        appearance_accepted=False,
    )
    core.atomic_json(root / "art-kits" / (prefix + ".json"), row)
    return {"stage": "Art set ready · inspect in the game camera", **row}


def themed_rules(prefix, spec):
    rules = rule_settings(prefix)
    rules["title"] = spec["name"]
    labels = spec["labels"]
    for r in rules["rules"]:
        r["label"] = {
            "collect_herb": "Collect " + labels[4],
            "collect_bottle": "Collect " + labels[5],
            "craft_potion": "Craft " + labels[6],
            "brew_at_table": "Craft " + labels[6],
            "use_potion": "Use " + labels[6] + " (+30 health)",
        }[r["rule_id"]]
    return rules
