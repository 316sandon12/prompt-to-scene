"""Build a reproducible before/after Blender comparison without starting native editors.

Run from the checkout: uv run python tools/game_art_smoke.py
All disposable data stays under .local/game-art-demo; only selected final evidence is retained.
"""

import argparse
import json
import os
from pathlib import Path

from prompt_to_scene import core, game_art, preparation, recipes, registry, styles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=["before", "after", "all"], default="all")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parents[1] / ".local/game-art-demo"
    os.environ["PTS_HOME"] = str(folder / "home")
    os.environ.pop("PTS_PROJECT", None)
    os.environ.pop("PTS_UNITY_PROJECT", None)
    project = folder / "Project"
    (project / "Assets").mkdir(parents=True, exist_ok=True)
    (project / "ProjectSettings").mkdir(exist_ok=True)
    registry.connect(str(project), install_bridge=False)
    art = styles.save(
        project,
        "cozy",
        "desktop",
        {
            "wear": 0.16,
            "palette": {
                "wood": [0.26, 0.12, 0.047],
                "paint": [0.055, 0.19, 0.135],
                "metal": [0.13, 0.1, 0.055],
            },
        },
    )
    game_art.configure(
        project,
        {
            "world": "A quiet mountain village; the herbalist inherited a handmade timber shop.",
            "gameplay": "Collect, sort and sell herbs. Players examine storage furniture close up.",
            "style_notes": "Warm muted wood and green paint; restrained brass, quiet grain.",
            "view": "first_person",
            "construction": "handcrafted",
        },
    )
    brief = game_art.plan(
        project,
        "after",
        "Handmade herbalist storage cabinet",
        role="interactable",
        focal_point="paired ring handles",
        recipe_kind="cabinet",
        decisions={
            "silhouette": "Shaped crown over a squat, stable cabinet",
            "structure": "Framed doors, side rails, turned feet and visible hinges",
            "story": "Carefully maintained timber furniture",
        },
    )
    results_path = folder / "results.json"
    results = json.loads(results_path.read_text()) if results_path.is_file() else {}
    for name, asset_design in (("before", None), ("after", brief)):
        if args.asset != "all" and args.asset != name:
            continue
        script, recipe = recipes.prepare("cabinet", style=art, art_design=asset_design)
        script += (
            '\nimport bpy\nbpy.context.scene["pts_preview_frame"] = '
            '"[[-0.7,-0.4,0],[0.7,0.4,1.45]]"\n'
        )
        built = core.build(
            str(project),
            name,
            script,
            recipe=recipe,
            preview_only=True,
            timeout=600,
            preparation=preparation.options({"ground": False}),
        )
        assert built["status"] == "completed", built
        results[name] = built
        print(
            json.dumps(
                {"asset": name, "status": built["status"], "request_id": built["request_id"]}
            ),
            flush=True,
        )
    results_path.write_text(json.dumps(results, indent=2))
    print(str(results_path), flush=True)


if __name__ == "__main__":
    main()
