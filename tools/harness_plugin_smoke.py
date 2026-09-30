"""Register a bundle and invoke it inside a real isolated Harness profile, without an LLM."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from prompt_to_scene import clients


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsh", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pts harness ") as directory:
        root = Path(directory).resolve()
        os.environ["DSH_HOME"] = str(root / "dsh")
        os.environ["PTS_HOME"] = str(root / "pts")
        os.environ["PTS_PROBE_RESULT"] = str(root / "result.json")
        clients.install("harness", command=args.dsh)
        patch = root / "probe.json"
        patch.write_text(
            json.dumps(
                [
                    {
                        "insert": [
                            {
                                "id": "pts-native-probe",
                                "name": str(Path(__file__).with_name("harness_probe.mjs")),
                            }
                        ]
                    }
                ]
            )
        )
        with (root / "host.log").open("w") as log:
            subprocess.run(
                [args.dsh, "web", "--patch", str(patch), "--no-open", "--port", "0"],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=90,
            )
        assert json.loads((root / "result.json").read_text())["passed"]
        print("PASS: native Harness bundle registration and ToolRuntime invocation")


if __name__ == "__main__":
    main()
