"""Local MCP Apps protocol fixture for browser QA; not a Codex/Harness UI certification."""

import argparse
import json
from pathlib import Path

from prompt_to_scene import setup, workbench

HOST = Path(__file__).with_name("ui_host_smoke.html").read_text(encoding="utf-8")


class Handler(setup.Handler):
    def do_GET(self):
        if self.path == "/app-host" and self.headers.get("Host") == "127.0.0.1:" + str(
            self.server.server_port
        ):
            page = HOST.replace("PAGE", json.dumps(workbench.page()).replace("</", "<\\/"))
            page = page.replace("TOKEN", json.dumps(self.server.token)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        else:
            super().do_GET()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url-file", type=Path, required=True)
    args = parser.parse_args()
    with setup.Server() as server:
        server.RequestHandlerClass = Handler
        args.url_file.write_text(server.origin + "/app-host")
        server.serve_forever()


if __name__ == "__main__":
    main()
