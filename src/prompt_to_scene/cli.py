import argparse
import json
from pathlib import Path

from .core import build, inspect_project, wait_for_status


def main():
    parser = argparse.ArgumentParser(description="Prompt-to-Scene local workflow")
    parser.add_argument("--project", required=True, help="Unity directory or Unreal .uproject file")
    parser.add_argument("--engine", choices=("auto", "unity", "unreal"), default="auto")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect")
    check = commands.add_parser("status")
    check.add_argument("asset_id")
    check.add_argument("--request-id")
    check.add_argument(
        "--wait", type=float, default=0, help="Wait for this request, up to 30 seconds"
    )
    create = commands.add_parser("build")
    create.add_argument("asset_id")
    source = create.add_mutually_exclusive_group(required=True)
    source.add_argument("--script", type=Path)
    source.add_argument("--blend", type=Path)
    create.add_argument("--position", type=float, nargs=3, default=[0, 0, 0])
    create.add_argument("--no-collider", action="store_true")
    create.add_argument("--wait", type=float, default=0, help="Wait for import, up to 30 seconds")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            result = inspect_project(args.project, engine=args.engine)
        elif args.command == "status":
            result = wait_for_status(
                args.project, args.asset_id, args.request_id, args.wait, engine=args.engine
            )
        else:
            if not 0 <= args.wait <= 30:
                raise ValueError("--wait must be between 0 and 30")
            script = args.script.read_text() if args.script else ""
            result = build(
                args.project,
                args.asset_id,
                script,
                args.position,
                not args.no_collider,
                blend_file=args.blend,
                engine=args.engine,
            )
            if args.wait:
                result = wait_for_status(
                    args.project, args.asset_id, result["request_id"], args.wait, engine=args.engine
                )
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") in {"error", "superseded"} or result.get("wait_timed_out"):
        parser.exit(2)


if __name__ == "__main__":
    main()
