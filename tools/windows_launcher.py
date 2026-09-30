"""Windowless launcher; the separate core keeps stdio available to MCP clients."""

import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    subprocess.Popen(
        [str(Path(sys.executable).with_name("prompt-to-scene-core.exe")), "--setup"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
    )
