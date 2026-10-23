"""
Local HTTP server for the Meta Ads Dashboard.

Serves the meta-automation directory as static files and exposes a
POST /api/export endpoint that saves the dashboard config to output/.

Usage:
    python -m scripts.serve
    python -m scripts.serve --port 8765
"""

import argparse
import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_PATH = OUTPUT_DIR / "meta_upload_config.json"


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/api/export":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                OUTPUT_DIR.mkdir(exist_ok=True)
                with open(CONFIG_PATH, "w") as f:
                    json.dump(data, f, indent=2)
                self._respond(200, {"ok": True, "path": str(CONFIG_PATH)})
                print(f"[export] Saved {len(data.get('ads', []))} ads to {CONFIG_PATH}")
            except Exception as e:
                self._respond(500, {"ok": False, "error": str(e)})
        else:
            self._respond(404, {"error": "Not found"})

    def _respond(self, status: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Suppress static file noise, only show API calls
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description="Serve Meta Ads Dashboard")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    os.chdir(BASE_DIR)
    server = HTTPServer(("localhost", args.port), DashboardHandler)
    url = f"http://localhost:{args.port}/dashboard/meta-ads-dashboard.html"
    print(f"Dashboard: {url}")
    print(f"Export endpoint: http://localhost:{args.port}/api/export")
    print("Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
