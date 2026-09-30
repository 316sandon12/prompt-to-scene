import argparse
import json
from pathlib import Path

from .core import build, inspect_project, status


def main():
    parser = argparse.ArgumentParser(description="Prompt-to-Scene local workflow")
    parser.add_argument("--project", required=True, help="Unity project directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect")
    check = commands.add_parser("status")
    check.add_argument("asset_id")
    create = commands.add_parser("build")
    create.add_argument("asset_id")
    source = create.add_mutually_exclusive_group(required=True)
    source.add_argument("--script", type=Path)
    source.add_argument("--blend", type=Path)
    create.add_argument("--position", type=float, nargs=3, default=[0, 0, 0])
    create.add_argument("--no-collider", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = inspect_project(args.project)
        elif args.command == "status":
            result = status(args.project, args.asset_id)
        else:
            script = args.script.read_text() if args.script else ""
            result = build(
                args.project,
                args.asset_id,
                script,
                args.position,
                not args.no_collider,
                blend_file=args.blend,
            )
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
