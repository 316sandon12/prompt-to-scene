"""Real MCP → Blender → native editor scenarios used by authoring_smoke --preparation."""

import base64
import hashlib
import json
from pathlib import Path

from prompt_to_scene import core


async def exercise_preparation(client, call, wait, fixture, scene, position, target, prefix):
    repo = Path(__file__).resolve().parents[1]
    root = core.state_root(target.root)
    source = repo / ".local/v05-fixtures/fixture.glb"
    assert source.is_file(), "Run tools/external_fixture.py in Blender first"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    asset = prefix + "_external"
    settings = {"triangle_budget": 3500, "texture_size": 256, "target_size": 1.5}
    await call("set_project_style", {"preset": "cozy", "quality": "mobile"})
    draft = await wait(
        await call(
            "import_asset",
            {
                "asset_id": asset,
                "source": {"path": str(source)},
                "settings": settings,
                "preview_only": True,
            },
        ),
        "completed",
    )
    assert not any(o["asset_id"] == asset for o in (await scene())["assets"])
    report = draft["report"]["preparation"]
    assert report["triangles_before"] == 14976
    assert report["triangles_after"] <= 3500 and len(report["lods"]) == 2
    assert "before.png" in draft["previews"]
    imported = await wait(
        await call(
            "publish_prepared",
            {
                "asset_id": asset,
                "request_id": draft["request_id"],
            },
        )
    )
    assert imported["lod_count"] == 3 and imported["collision_count"] > 0
    assert abs(max(imported["bounds_size"]) - 1.5) < 0.02, imported
    await fixture("check", asset)
    await fixture("check_preparation", asset)
    native = json.loads((root / "preparation-native.json").read_text())
    assert native["triangles"] == [
        report["triangles_after"],
        *[x["triangles"] for x in report["lods"]],
    ]
    core.atomic_json(target.root / "preparation-native-first.json", native)
    info = await call("inspect_asset", {"asset_id": asset})
    assert Path(info["source_blend"]).with_name("original.blend").is_file()
    assert info["metadata"]["provenance"]["sha256"] == digest
    await fixture("select", asset)
    edited = await call(
        "edit_scene", {"operation": "transform", "values": {"move": position(2, 1)}}
    )
    if edited["status"] == "queued":
        await wait(edited, "completed")
    before = next(o for o in (await scene())["assets"] if o["asset_id"] == asset)
    review = await call("capture_review", {"asset_id": asset, "view": "studio"})
    await wait(review, "completed")
    frame = root / "preview-frames" / (review["review_id"] + ".json")
    frame_bytes = frame.read_bytes()
    # Increase fidelity from the original, removing now unwanted LODs/collision on reimport.
    revised = await wait(
        await call(
            "prepare_asset",
            {
                "asset_id": asset,
                "settings": {
                    **settings,
                    "triangle_budget": 8000,
                    "collision": "none",
                    "lod_ratios": [],
                },
            },
        )
    )
    key = "prefab_guid" if target.engine == "unity" else "actor_guid"
    assert revised[key] == imported[key]
    assert revised["lod_count"] == 1 and revised["collision_count"] == 0
    assert revised["report"]["preparation"]["triangles_before"] == 14976
    assert 3500 < revised["triangles"] <= 8000
    await fixture("check_preparation", asset)
    after = next(o for o in (await scene())["assets"] if o["asset_id"] == asset)
    assert before["id"] == after["id"] and before["position"] == after["position"]
    capture = await call(
        "capture_review",
        {"asset_id": asset, "review_id": review["review_id"], "view": "studio", "stage": "after"},
    )
    await wait(capture, "completed")
    assert frame.read_bytes() == frame_bytes, "Comparison camera drifted"
    review = await call("get_review", {"review_id": review["review_id"]})
    for stage in ("before", "after"):
        result = await client.call_tool("get_preview", {"request_id": review[stage]})
        images = [c for c in result.content if c.type == "image"]
        assert images, result
        (target.root / ("preparation-" + stage + ".png")).write_bytes(
            base64.b64decode(images[0].data)
        )
    kit = await call("create_style_kit", {"kit": "reading_corner", "prefix": prefix + "_kit"})
    assert len(kit["tasks"]) == 3
    for task in kit["tasks"]:
        await wait(task)
    chair = prefix + "_kit_chair"
    await fixture("select", chair)
    info = await call("inspect_asset", {"asset_id": chair})
    edited = await call(
        "edit_selected_prop", {"part": "backrest", "changes": {"scale": [1, 1, 1.2]}}
    )
    if edited.get("inspection_request_id"):
        edited = await call(
            "edit_selected_prop",
            {
                "part": "backrest",
                "changes": {"scale": [1, 1, 1.2]},
                "inspection_request_id": edited["inspection_request_id"],
            },
        )
    await wait(edited)
    revised = await call("inspect_asset", {"asset_id": chair})
    for part, values in info["report"]["parts"].items():
        assert (values["geometry_hash"] == revised["report"]["parts"][part]["geometry_hash"]) == (
            part != "backrest"
        )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    print(
        "PASS: preparation, native LOD/collision, retained original, "
        "fixed-frame review, kit and selected edit",
        flush=True,
    )
