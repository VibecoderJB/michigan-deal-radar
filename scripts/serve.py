"""Local dev server: serves app/, maps /data/* to data/ and /reports/* to _site/reports/ (built by pipeline.reporting.build).

    python scripts/serve.py            # http://localhost:8000
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("MDR_DATA_DIR", ROOT / "data"))
REPORTS = Path(os.environ.get("MDR_REPORTS_DIR", ROOT / "_site" / "reports"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/data/"):
            return str(DATA / clean[len("/data/"):])
        if clean.startswith("/reports/"):
            return str(REPORTS / clean[len("/reports/"):])
        return super().translate_path(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    handler = functools.partial(Handler, directory=str(ROOT / "app"))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Serving Michigan Deal Radar at http://localhost:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
