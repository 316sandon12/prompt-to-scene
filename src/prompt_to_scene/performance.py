"""Use-case budgets and native editor measurements, without inferred frame-rate claims."""

from . import authoring, workflow

PRESETS = {
    "mobile_prop": {
        "label": "移动端场景道具",
        "triangle_budget": 8000,
        "texture_size": 512,
        "material_slots": 2,
        "texture_mib": 8,
        "lod_ratios": [0.5, 0.2],
    },
    "scene_prop": {
        "label": "桌面场景道具",
        "triangle_budget": 20000,
        "texture_size": 1024,
        "material_slots": 4,
        "texture_mib": 32,
        "lod_ratios": [0.5, 0.25],
    },
    "hero_prop": {
        "label": "近景主角道具",
        "triangle_budget": 100000,
        "texture_size": 2048,
        "material_slots": 8,
        "texture_mib": 128,
        "lod_ratios": [0.6, 0.3],
    },
}


def summarize(result, preset="scene_prop"):
    if preset not in PRESETS:
        raise ValueError("Unknown usage preset")
    budget = PRESETS[preset]
    metrics = result.get("metrics", [])
    notes, meshes = [], {}
    for row in metrics:
        meshes.setdefault(row.get("mesh_key", row["id"]), []).append(row["id"])
        for field, limit in (
            ("triangles", budget["triangle_budget"]),
            ("material_slots", budget["material_slots"]),
            ("texture_bytes_estimate", budget["texture_mib"] * 1024**2),
        ):
            if row.get(field, 0) > limit:
                notes.append(
                    {
                        "object_id": row["id"],
                        "metric": field,
                        "value": row[field],
                        "budget": limit,
                        "recommendation": {
                            "triangles": "Prepare from original with this use-case budget",
                            "material_slots": "Reuse a shared material or author an atlas",
                            "texture_bytes_estimate": (
                                "Reduce texture resolution; inspect platform compression"
                            ),
                        }[field],
                    }
                )
    return {
        **result,
        "usage_preset": preset,
        "budget": budget,
        "recommendations": notes,
        "shared_mesh_instances": [ids for ids in meshes.values() if len(ids) > 1],
        "measurement_note": (
            "Native editor geometry/material counts. Texture estimate is RGBA8+mips, "
            "not compressed GPU allocation. No FPS or draw-call count is inferred."
        ),
    }


def inspect(project, asset_id=None, request_id=None, preset="scene_prop", wait_seconds=0):
    if preset not in PRESETS:
        raise ValueError("Unknown usage preset")
    task = (
        {"request_id": request_id}
        if request_id
        else workflow.action(
            project, "analyze", asset_id=asset_id, scope="asset" if asset_id else "selected"
        )
    )
    result = workflow.job_status(project, task["request_id"], wait_seconds)
    return summarize(result, preset) if result["status"] == "completed" else result


def optimize(project, asset_id, preset):
    if preset not in PRESETS:
        raise ValueError("Unknown usage preset")
    values = {k: PRESETS[preset][k] for k in ("triangle_budget", "texture_size", "lod_ratios")}
    return authoring.optimize(project, asset_id, values)
