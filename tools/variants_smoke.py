"""Render all 27 structural draft variants in real Blender, without engine publication."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from prompt_to_scene import core, design, recipes, styles


def main():
    root = Path(__file__).resolve().parents[1] / ".local/v05-variants-smoke"
    (root / "Assets").mkdir(parents=True, exist_ok=True)
    (root / "ProjectSettings").mkdir(exist_ok=True)

    def build(item):
        kind, variant = item
        script, recipe = recipes.prepare(
            kind, {"variant": variant}, style=styles.preset("cozy", "draft")
        )
        result = core.build(
            root, f"{kind}_{variant}", script, recipe=recipe, preview_only=True, timeout=600
        )
        assert set(result["report"]["parts"]) == set(design.PARTS[kind])
        folder = Path(result["source_blend"]).parent
        for view in ("studio", "front", "back"):
            assert (folder / (view + ".png")).stat().st_size > 5000
        assert not (core.state_root(root) / "inbox" / f"{kind}_{variant}.json").exists()
        print("PASS", kind, variant, flush=True)
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(build, [(k, v) for k in design.DEFAULTS for v in range(3)]))
    for kind in design.DEFAULTS:
        hashes = [
            json.dumps(r["report"]["parts"], sort_keys=True)
            for r in results
            if r["asset_id"].startswith(kind + "_")
        ]
        assert len(set(hashes)) == 3
    core.atomic_json(root / "evidence.json", results)


if __name__ == "__main__":
    main()
