"""Native v0.6 evidence, including a fixture HTTP provider (not an AI quality test)."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from prompt_to_scene import core


async def exercise_usage_preset(call, wait, fixture, scene, position, target, prefix):
    source = Path(__file__).resolve().parents[1] / ".local/v05-fixtures/fixture.glb"
    name = prefix + "_mobile"
    baseline = await wait(
        await call(
            "import_asset",
            {
                "asset_id": name,
                "source": {"path": str(source)},
                "settings": {"triangle_budget": 18000, "texture_size": 256},
                "position": position(25, -25),
            },
        )
    )
    before = next(a for a in (await scene())["assets"] if a["asset_id"] == name)
    optimized = await wait(
        await call("apply_usage_preset", {"asset_id": name, "preset": "mobile_prop"})
    )
    assert baseline["triangles"] == 14976
    assert 0 < optimized["triangles"] <= 8000
    assert optimized["report"]["preparation"]["settings"]["texture_size"] == 512
    after = next(a for a in (await scene())["assets"] if a["asset_id"] == name)
    assert before["id"] == after["id"] and before["position"] == after["position"]
    await fixture("check_preparation", name)
    await fixture("check_usage_preset", name)
    metrics = await call(
        "inspect_performance", {"asset_id": name, "preset": "mobile_prop", "wait_seconds": 10}
    )
    row = metrics["metrics"][0]
    assert row["triangles"] == optimized["triangles"] and len(row["lod_triangles"]) == 3
    assert row["lod_triangles"][0] > row["lod_triangles"][1] > row["lod_triangles"][2] > 0
    print("PASS: mobile usage preset changes real geometry, textures and native LODs", flush=True)


async def exercise_workbench(client, call, wait, fixture, scene, position, target, prefix):
    root = core.state_root(target.root)
    up = 1 if target.engine == "unity" else 2
    await call("set_project_style", {"preset": "cozy", "quality": "draft"})
    table = prefix + "_table"
    await wait(
        await call(
            "create_prop", {"kind": "table", "asset_id": table, "position": position(12, 12)}
        )
    )
    await fixture("select", table)
    rotation = [0, 0, 0]
    rotation[up] = 37
    await wait(
        await call("edit_scene", {"operation": "transform", "values": {"rotate": rotation}}),
        "completed",
    )
    before = await scene()
    anchor = next(o for o in before["assets"] if o["asset_id"] == table)
    assert len(anchor["footprint"]) == 8 and "oriented_min" in anchor
    assert abs(anchor["rotation"][up] - 37) < 0.01
    assert all(abs(anchor["rotation"][i]) < 0.01 for i in range(3) if i != up)
    # Actual furnished kit at a clear position, independent of the temporary staging row.
    composition = await wait(
        await call(
            "compose_scene", {"prefix": prefix + "_kit", "position": position(-10, -10), "yaw": 37}
        ),
        "completed",
    )
    assert len(composition["layout"]["objects"]) == 3
    kit_ids = [t["asset_id"] for t in composition["asset_tasks"]]
    await fixture("check_facing", prefix + "_kit_chair")
    await fixture("select_all", prefix + "_kit")
    template = prefix + "_layout"
    await wait(await call("compose_scene", {"mode": "save", "template": template}), "completed")
    placed = await wait(
        await call(
            "compose_scene",
            {"mode": "place", "template": template, "position": position(-20, 10), "yaw": 21},
        ),
        "completed",
    )
    assert len(placed["layout"]["created_ids"]) == 3
    await wait(await call("undo_scene_edit", {"undo_id": placed["undo_id"]}), "completed")
    chair = next(n for n in kit_ids if n.endswith("_chair"))
    await fixture("select", table)
    arranged = await call(
        "arrange_props",
        {
            "items": [{"asset_id": chair, "count": 2}],
            "relation": "around",
            "face_anchor": True,
            "gap": 0.4,
        },
    )
    arranged = await wait(arranged, "completed")
    assert arranged["changed"] == 2
    await wait(await call("undo_scene_edit", {"undo_id": arranged["undo_id"]}), "completed")
    perf = await call("inspect_performance", {"asset_id": chair, "wait_seconds": 10})
    assert perf["status"] == "completed" and perf["metrics"][0]["triangles"] > 0
    assert perf["metrics"][0]["support_known"], perf
    # A measured small support gap should be repaired once and photographed from one frame.
    move = [0, 0, 0]
    move[up] = 0.12
    await wait(
        await call(
            "edit_scene",
            {
                "operation": "transform",
                "scope": "asset",
                "asset_id": chair,
                "values": {"move": move},
            },
        ),
        "completed",
    )
    quality = await wait(
        await call("review_quality", {"asset_id": chair, "auto_fix": True}), "completed"
    )
    assert (
        quality["repair_count"] == 1 and abs(quality["after"]["metrics"][0]["support_gap"]) < 0.01
    ), quality
    old_after = quality["review"]["after"]
    await wait(
        await call(
            "repair_quality",
            {"request_id": quality["request_id"], "part": "seat", "changes": {"roughness": 0.65}},
        ),
        "completed",
    )
    quality = await call("get_task_status", {"request_id": quality["request_id"]})
    assert quality["repair_count"] == 2 and quality["review"]["after"] != old_after
    rejected = await client.call_tool(
        "repair_quality",
        {"request_id": quality["request_id"], "part": "seat", "changes": {"roughness": 0.6}},
    )
    assert rejected.isError
    for stage, request_id in (
        ("before", quality["review"]["before"]),
        ("after", quality["review"]["after"]),
    ):
        result = await client.call_tool("get_preview", {"request_id": request_id})
        images = [c for c in result.content if c.type == "image"]
        assert images
        (target.root / ("workbench-" + stage + ".png")).write_bytes(
            base64.b64decode(images[0].data)
        )
    source = Path(__file__).resolve().parents[1] / ".local/v05-fixtures/fixture.glb"
    assert source.exists(), source
    name = prefix + "_external"
    settings = {"texture_size": 256, "triangle_budget": 18000, "lod_ratios": [0.5, 0.25]}
    await wait(
        await call(
            "import_asset",
            {
                "asset_id": name,
                "source": {"provider": "local", "path": str(source)},
                "settings": settings,
                "position": position(30, 30),
            },
        )
    )
    info = await call("inspect_asset", {"asset_id": name})
    parts = info["report"]["parts"]
    ceramic = next(p for p in parts if "Ceramic" in p)
    rim = next(p for p in parts if "Rim" in p)
    untouched = parts[ceramic]["geometry_hash"]
    await wait(
        await call(
            "edit_imported_part",
            {"asset_id": name, "part": "trim", "members": [rim], "lock_geometry": True},
        )
    )
    await wait(
        await call(
            "edit_imported_part", {"asset_id": name, "part": "trim", "changes": {"roughness": 0.7}}
        )
    )
    info = await call("inspect_asset", {"asset_id": name})
    assert info["report"]["parts"][ceramic]["geometry_hash"] == untouched
    assert info["report"]["parts"]["trim"]["locks"]["geometry"]
    # Identical geometry and unchanged other material: native mesh reuse + cached maps.
    updated = await wait(
        await call(
            "edit_imported_part", {"asset_id": name, "part": "trim", "changes": {"roughness": 0.45}}
        )
    )
    assert updated["geometry_reused"], updated
    info = await call("inspect_asset", {"asset_id": name})
    assert info["report"]["bake_cache"]["reused_materials"], info["report"]
    locked = await client.call_tool(
        "edit_imported_part",
        {"asset_id": name, "part": "trim", "changes": {"scale": [1.1, 1.1, 1.1]}},
    )
    assert locked.isError
    # Failed builds leave current imported asset available; explicitly unlock for replacement.
    await wait(
        await call(
            "edit_imported_part",
            {
                "asset_id": name,
                "part": "trim",
                "lock_geometry": False,
                "replacement_path": str(source),
            },
        )
    )
    final = await call("inspect_asset", {"asset_id": name})
    assert final["report"]["parts"][ceramic]["geometry_hash"] == untouched
    perf = await call(
        "inspect_performance", {"asset_id": name, "wait_seconds": 10, "preset": "mobile_prop"}
    )
    assert (
        perf["metrics"][0]["texture_count"] >= 4 and len(perf["metrics"][0]["lod_triangles"]) == 3
    )
    await call(
        "set_art_brief",
        {
            "image_path": str(target.root / "workbench-before.png"),
            "notes": "Round forms and soft colors",
        },
    )
    reference = await client.call_tool("get_art_reference", {})
    assert any(c.type == "image" for c in reference.content)
    provider_requests = []
    data = source.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            assert self.path == "/jobs"
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            provider_requests.append(payload)
            body = json.dumps({"id": "fixture"}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/model.glb":
                body = data
            else:
                body = json.dumps(
                    {
                        "status": "SUCCEEDED",
                        "model_url": f"http://127.0.0.1:{self.server.server_port}/model.glb",
                    }
                ).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    try:
        core.atomic_json(
            root / "isolated-client-home/providers.json",
            {"local": {"endpoint": f"http://127.0.0.1:{provider.server_port}"}},
        )
        generated = await wait(
            await call(
                "generate_model",
                {
                    "asset_id": prefix + "_generated",
                    "prompt": "Fixture transport verification",
                    "provider": "local",
                    "settings": settings,
                    "image_paths": [str(target.root / "workbench-before.png")],
                },
            ),
            "completed",
        )
        candidate = generated["candidates"][0]["asset_task"]
        assert len(provider_requests) == 1 and provider_requests[0]["images"][0].startswith(
            "data:image/png;base64,"
        )
        await wait(
            await call(
                "publish_prepared",
                {"asset_id": candidate["asset_id"], "request_id": candidate["request_id"]},
            )
        )
    finally:
        provider.shutdown()
        provider.server_close()
    await exercise_usage_preset(call, wait, fixture, scene, position, target, prefix)
    print(
        "PASS: scene layout, quality repair, metrics, external parts/cache/replacement, "
        "fixture provider -> Blender -> engine",
        flush=True,
    )
