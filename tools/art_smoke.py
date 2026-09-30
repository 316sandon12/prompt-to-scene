"""Real Blender evidence for art-directed geometry, baking, locks and isolated source views."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from prompt_to_scene import core, design, recipes, styles


def main():
    root = Path(__file__).resolve().parents[1] / ".local/v04-art-smoke"
    (root / "Assets").mkdir(parents=True, exist_ok=True)
    (root / "ProjectSettings").mkdir(exist_ok=True)

    def build(item):
        kind, style = item
        script, recipe = recipes.prepare(kind, style=styles.preset(style, "mobile"))
        result = core.build(
            root, kind + "_" + style, script, recipe=recipe, preview_only=True, timeout=600
        )
        work = Path(result["source_blend"]).parent
        report = json.loads((work / "report.json").read_text())
        assert report["texture_count"] >= 10 and report["checks"]["budget"] == "passed"
        assert set(report["parts"]) == set(design.PARTS[kind])
        for view in ("studio", "front", "back"):
            assert (work / (view + ".png")).stat().st_size > 5000
        assert not (root / ".prompt-to-scene/inbox" / f"{kind}_{style}.json").exists()
        print("PASS", kind, style, report["triangles"], flush=True)
        return result

    jobs = [
        (kind, ("cozy", "heritage", "workshop")[i % 3]) for i, kind in enumerate(design.DEFAULTS)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(build, jobs))
    # Native geometry invariants, beyond comparing Python plans.
    _, original = recipes.prepare("chair", style=styles.preset("cozy", "draft"))
    script, locked = recipes.edit_part(original, "backrest", lock_geometry=True)
    first = core.build(root, "locked_chair", script, recipe=locked, preview_only=True, timeout=300)
    script, revised = recipes.revise(locked, {"height": 1.4, "seat_height": 0.5})
    second = core.build(
        root, "locked_chair", script, recipe=revised, preview_only=True, timeout=300
    )
    before, after = first["report"]["parts"], second["report"]["parts"]
    assert before["backrest"]["geometry_hash"] == after["backrest"]["geometry_hash"]
    assert before["legs"]["geometry_hash"] != after["legs"]["geometry_hash"]
    script, edited = recipes.edit_part(
        revised, "seat", {"material": "paint", "color": [0.4, 0.05, 0.02]}
    )
    third = core.build(root, "locked_chair", script, recipe=edited, preview_only=True, timeout=300)
    assert {p: r["geometry_hash"] for p, r in second["report"]["parts"].items()} == {
        p: r["geometry_hash"] for p, r in third["report"]["parts"].items()
    }
    (root / "evidence.json").write_text(
        json.dumps({"library": results, "locks": [first, second, third]}, indent=2)
    )
    print(
        "PASS: all recipe exports, PBR maps, source views, isolated drafts and native part locks",
        flush=True,
    )


if __name__ == "__main__":
    main()
