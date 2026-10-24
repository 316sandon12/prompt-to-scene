"""Coherent structural/material/UI directions, with actual Blender draft comparisons."""

import hashlib
import uuid
from copy import deepcopy

from . import background, core, creations, game_art, preparation, registry, workflow

DIRECTIONS = {
    "forest_apothecary": dict(
        name="森林药剂师",
        notes="榫接木框、玉釉陶器、黄铜包边、亚麻束带；柔和轮廓与低对比细节。",
        labels=[
            "Timber apothecary",
            "Herbalist workbench",
            "Glazed jar display",
            "Jade lantern",
            "Sage bundle",
            "Porcelain bottle",
            "Forest remedy",
        ],
        theme=dict(
            background="#182521",
            surface="#283D32",
            accent="#D4BB7B",
            text="#F5F1E3",
            muted="#AAB7A8",
        ),
    ),
    "wasteland_workshop": dict(
        name="废土维修站",
        notes="铆接钢板、错落补丁、耐磨橙漆、粗织带；厚重支撑与清晰机械接缝。",
        labels=[
            "Salvage shelter",
            "Repair bench",
            "Supply rack",
            "Caged worklight",
            "Salvage coils",
            "Filter canister",
            "Field medical pack",
        ],
        theme=dict(
            background="#24211C",
            surface="#3D352B",
            accent="#E5A15F",
            text="#F4E6D2",
            muted="#B7A992",
        ),
    ),
    "orbital_workshop": dict(
        name="轨道科研站",
        notes="分层装甲、嵌入式接缝、白色陶瓷与深色铝框、青蓝指示条；模块化与悬挑结构。",
        labels=[
            "Orbital module",
            "Fabrication console",
            "Sample cabinet",
            "Task beacon",
            "Power cells",
            "Sample capsule",
            "Medical injector",
        ],
        theme=dict(
            background="#111E2D",
            surface="#21384D",
            accent="#6DD9E8",
            text="#E9F3FA",
            muted="#A2B9CC",
        ),
    ),
}


def catalog(project):
    """List three editable structural directions and the project's explicit selection."""
    cached = core.read_optional_json(game_art.root(project) / "direction-studies" / "current.json")
    study = workflow.job_status(project, cached["request_id"]) if cached else None
    return {
        "study": {k: study.get(k) for k in ("request_id", "status", "stage", "candidates")}
        if study
        else None,
        "directions": [dict(kit_id=k, **v) for k, v in DIRECTIONS.items()],
        "selected": core.read_optional_json(game_art.root(project) / "kit-direction.json"),
    }


def settings(kit_id, palette=None):
    if kit_id not in DIRECTIONS:
        raise ValueError("Choose a kit_id from art_directions")
    result = deepcopy(DIRECTIONS[kit_id])
    if palette is not None:
        from .art_samples import validate_theme

        result["theme"] = validate_theme(palette, result["theme"])
    return result


def select(project, kit_id, palette=None):
    """Remember a chosen direction; optional #RRGGBB UI palette adapts it to this project.

    This is an explicit art decision, not an automatic beauty score. Existing artwork stays intact.
    New kits inherit this palette when their direction matches. Their primary surfaces and trims
    use the same colors as the interface. Hosts should read accepted/avoid samples before choosing.
    """
    row = dict(kit_id=kit_id, **settings(kit_id, palette), revision=uuid.uuid4().hex)
    core.atomic_json(game_art.root(project) / "kit-direction.json", row)
    return row


def source(kit_id, kind, palette=None):
    settings(kit_id, palette)
    root = registry.resources() / "examples"
    forest = (root / "forest_apothecary.py").read_text(encoding="utf-8")
    if kit_id == "forest_apothecary":
        script = (
            (root / "herbalist_potion.py").read_text(encoding="utf-8")
            if kind == "potion"
            else forest
        )
    else:
        script = forest.split('if kind == "herb":', 1)[0]
        script += (root / "industrial_workshop.py").read_text(encoding="utf-8")
    prefix = f"PTS_ASSET_KIND = {kind!r}\nPTS_DIRECTION = {kit_id!r}\n"
    if palette:
        # Color the material itself before export/baking, not just the preview/UI.
        script += "\nfor m in bpy.data.materials:\n"
        script += "    if m.use_nodes:\n"
        script += "        p=m.node_tree.nodes.get('Principled BSDF')\n"
        script += f"        colors={palette!r}\n"
        script += (
            "        key='accent' if any(s in m.name.lower() for s in ('brass','trim','gold',"
            "'indicator')) else 'surface' if any(s in m.name.lower() for s in "
            "('jade','glaze','panel')) else None\n"
        )
        script += "        if key and key in colors:\n"
        script += (
            "            c=colors[key].lstrip('#'); "
            "p.inputs['Base Color'].default_value=tuple((int(c[i:i+2],16)/255)**2.2 "
            "for i in (0,2,4))+(1,)\n"
        )
    return prefix + script


def preview(project):
    """Compare actual 3D workbench drafts in consistent studio views; does not place assets."""
    path = game_art.root(project) / "direction-studies" / "current.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        "".join(source(k, "workbench") for k in DIRECTIONS).encode()
    ).hexdigest()
    with background.lock(path):
        cached = core.read_optional_json(path)
        if cached and cached.get("digest") == digest:
            task = workflow.job_status(project, cached["request_id"])
            if task["status"] not in {"error", "cancelled"}:
                return task
        task = background.submit(project, "direction_study", {})
        core.atomic_json(path, dict(digest=digest, request_id=task["request_id"]))
        return task


def run(job):
    candidates = []
    for kit_id, spec in DIRECTIONS.items():
        name = "direction_" + job.id[:12] + "_" + kit_id.split("_")[0]
        job.update(stage="Comparing art direction · " + spec["name"])
        task = creations.step(
            job,
            kit_id,
            lambda: workflow.submit(
                job.project,
                name,
                source(kit_id, "workbench")
                + '\nbpy.context.scene["pts_preview_frame"] = "[[-0.9,-0.55,0],[0.9,0.55,1.35]]"\n',
                preview_only=True,
                preparation=preparation.options(
                    dict(
                        ground=False,
                        collision="none",
                        texture_size=256,
                        triangle_budget=50000,
                        lod_ratios=[],
                    )
                ),
                provenance={"art_direction": kit_id, "license": "MIT"},
            ),
        )
        candidates.append(
            dict(
                kit_id=kit_id,
                asset_id=name,
                request_id=task["request_id"],
                previews=task.get("previews", []),
                theme=spec["theme"],
            )
        )
    return dict(
        stage="Three actual geometry drafts ready",
        candidates=candidates,
        preview_source="Blender studio render; use review in the game camera after import",
        appearance_accepted=False,
    )
