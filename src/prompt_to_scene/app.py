"""Shared executable entry point for the setup app, MCP clients and detached workers."""

import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        from .server import main as serve

        serve()
    elif len(sys.argv) > 2 and sys.argv[1] == "--worker":
        from .workflow import worker

        worker(sys.argv[2])
    elif len(sys.argv) > 2 and sys.argv[1] == "--editor-service":
        from .editor_tools import service

        service(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from .cli import main as cli

        del sys.argv[1]
        cli()
    else:
        from .setup import main as setup

        setup()


if __name__ == "__main__":
    main()
