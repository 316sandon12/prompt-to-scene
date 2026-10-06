"""Install in an isolated Codex home and call a tool through its real app-server."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from prompt_to_scene import clients


def main():
    with tempfile.TemporaryDirectory(prefix="pts codex ") as directory:
        root = Path(directory).resolve()
        os.environ["CODEX_HOME"] = str(root / "codex")
        os.environ["PTS_HOME"] = str(root / "pts")
        Path(os.environ["CODEX_HOME"]).mkdir()
        clients.install("codex")
        original_version = clients.__version__
        try:
            clients.__version__ = original_version + "-upgrade-test"
            assert json.loads(clients.install("codex")["details"])["version"] == clients.__version__
        finally:
            clients.__version__ = original_version
        clients.install("codex")
        with (root / "server.log").open("w") as log:
            process = subprocess.Popen(
                [clients.executable("codex"), "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
            )

            def rpc(number, method, parameters):
                process.stdin.write(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": number, "method": method, "params": parameters}
                    )
                    + "\n"
                )
                process.stdin.flush()
                while True:
                    line = process.stdout.readline()
                    if not line:
                        raise RuntimeError("Codex app-server exited")
                    response = json.loads(line)
                    if response.get("id") == number:
                        assert "error" not in response, response
                        return response["result"]

            try:
                rpc(
                    1,
                    "initialize",
                    {
                        "clientInfo": {"name": "pts-verification", "version": "0.9.1"},
                        "capabilities": {"experimentalApi": True},
                    },
                )
                process.stdin.write('{"jsonrpc":"2.0","method":"initialized"}\n')
                process.stdin.flush()
                thread = rpc(2, "thread/start", {"cwd": str(root), "ephemeral": True})["thread"][
                    "id"
                ]
                catalog = rpc(3, "mcpServerStatus/list", {"threadId": thread})["data"]
                server = next(s for s in catalog if s["name"] == "prompt_to_scene")
                assert len(server["tools"]) == 65
                result = rpc(
                    4,
                    "mcpServer/tool/call",
                    {
                        "threadId": thread,
                        "server": server["name"],
                        "tool": "list_projects",
                        "arguments": {},
                    },
                )
                assert not result.get("isError"), result
                assert "crate" in json.loads(result["content"][0]["text"])["recipes"]
                print("PASS: native Codex plugin discovery and app-server tool call")
            finally:
                process.terminate()
                process.wait(timeout=20)


if __name__ == "__main__":
    main()
