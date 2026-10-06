"""HTTP API and Static File Server for Scheme Board.
Stdlib only, ThreadingHTTPServer on port 8902, bound to 0.0.0.0.
"""

from __future__ import annotations
import json
import mimetypes
import os
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

import db

BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR / "site"
HOST = "0.0.0.0"
PORT = 8902


class SchemeBoardHandler(BaseHTTPRequestHandler):
    server_version = "SchemeBoard/1.0"

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With"
        )

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status=status)

    def _parse_json_body(self) -> Optional[dict]:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body)
        except Exception as e:
            return None

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    # --- Routing Helpers ---

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed_url.query)

        # Root redirect to console
        if parsed_url.path in ("/", "/index.html") or path in ("", "/index.html"):
            host = self.headers.get("Host", "localhost:8902").split(":")[0]
            self.send_response(302)
            self.send_header("Location", f"http://{host}:8903/#/ideas")
            self.end_headers()
            return

        # Health check
        if path == "/api/health":
            self._send_json({"ok": True, "db": str(db.DB_PATH)})
            return

        # Stats
        if path == "/api/stats":
            stats = db.get_stats()
            self._send_json(stats)
            return

        # Connections
        if path == "/api/connections":
            conns = db.list_connections()
            self._send_json(conns)
            return

        # Themes
        if path == "/api/themes":
            themes = db.list_themes()
            self._send_json(themes)
            return

        # Analysis runs
        if path == "/api/analysis":
            limit = 20
            if "limit" in query:
                try:
                    limit = int(query["limit"][0])
                except Exception:
                    pass
            runs = db.list_analysis_runs(limit=limit)
            self._send_json(runs)
            return

        # Single idea: /api/ideas/{id}
        if path.startswith("/api/ideas/"):
            idea_id_str = path[len("/api/ideas/") :]
            try:
                idea_id = int(idea_id_str)
            except ValueError:
                self._send_error("Invalid idea ID", status=400)
                return

            idea = db.get_idea(idea_id)
            if not idea:
                self._send_error("Idea not found", status=404)
                return
            self._send_json(idea)
            return

        # List ideas: /api/ideas
        if path == "/api/ideas":
            status_param = query.get("status", [None])[0]
            category_param = query.get("category", [None])[0]
            tag_param = query.get("tag", [None])[0]
            q_param = query.get("q", [None])[0]

            hide_seeded = False
            if "hide_seeded" in query:
                val = query["hide_seeded"][0].lower()
                hide_seeded = val in ("1", "true", "yes")

            limit_param = None
            if "limit" in query:
                try:
                    limit_param = int(query["limit"][0])
                except Exception:
                    pass

            offset_param = None
            if "offset" in query:
                try:
                    offset_param = int(query["offset"][0])
                except Exception:
                    pass

            ideas, total = db.list_ideas(
                status=status_param,
                category=category_param,
                tag=tag_param,
                q=q_param,
                hide_seeded=hide_seeded,
                limit=limit_param,
                offset=offset_param,
            )
            self._send_json({"ideas": ideas, "items": ideas, "total": total})
            return

        # Static file serving
        self._serve_static(parsed_url.path)

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if path == "/api/ideas":
            body = self._parse_json_body()
            if body is None:
                self._send_error("Invalid JSON body", status=400)
                return

            title = body.get("title")
            raw = body.get("raw")
            if not title or not isinstance(title, str) or not title.strip():
                self._send_error("Field 'title' is required", status=400)
                return
            if not raw or not isinstance(raw, str) or not raw.strip():
                self._send_error("Field 'raw' is required", status=400)
                return

            created = db.create_idea(
                title=title.strip(),
                raw=raw.strip(),
                owner=body.get("owner", "C6"),
                status=body.get("status", "raw"),
                category=body.get("category"),
                tags=body.get("tags"),
                scores=body.get("scores"),
                seeded=body.get("seeded", 0),
                summary=body.get("summary"),
                create_run=True,  # Inserts analysis_runs (status='pending')
            )
            self._send_json(created, status=201)
            return

        self._send_error("Endpoint not found", status=404)

    def do_PATCH(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if path.startswith("/api/ideas/"):
            idea_id_str = path[len("/api/ideas/") :]
            try:
                idea_id = int(idea_id_str)
            except ValueError:
                self._send_error("Invalid idea ID", status=400)
                return

            body = self._parse_json_body()
            if body is None:
                self._send_error("Invalid JSON body", status=400)
                return

            # Check if idea exists
            existing = db.get_idea(idea_id)
            if not existing:
                self._send_error("Idea not found", status=404)
                return

            updated = db.update_idea(idea_id, **body)
            self._send_json(updated, status=200)
            return

        self._send_error("Endpoint not found", status=404)

    def do_DELETE(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if path.startswith("/api/ideas/"):
            idea_id_str = path[len("/api/ideas/") :]
            try:
                idea_id = int(idea_id_str)
            except ValueError:
                self._send_error("Invalid idea ID", status=400)
                return

            existing = db.get_idea(idea_id)
            if not existing:
                self._send_error("Idea not found", status=404)
                return

            deleted = db.delete_idea(idea_id)
            if deleted:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_cors_headers()
                self.end_headers()
            else:
                self._send_error("Failed to delete idea", status=500)
            return

        self._send_error("Endpoint not found", status=404)

    def _serve_static(self, req_path: str) -> None:
        clean_path = req_path.lstrip("/")
        if not clean_path or clean_path == "":
            target_file = SITE_DIR / "index.html"
        elif clean_path.startswith("static/"):
            rel_sub = clean_path[len("static/") :]
            target_file = (SITE_DIR / rel_sub).resolve()
        else:
            target_file = (SITE_DIR / clean_path).resolve()

        # Security check: must remain inside SITE_DIR
        try:
            target_file.relative_to(SITE_DIR.resolve())
        except ValueError:
            self._send_error("Forbidden", status=403)
            return

        if not target_file.is_file():
            self._send_error("Not found", status=404)
            return

        mime_type, _ = mimetypes.guess_type(str(target_file))
        if mime_type is None:
            if target_file.suffix == ".js":
                mime_type = "application/javascript"
            elif target_file.suffix == ".css":
                mime_type = "text/css"
            elif target_file.suffix == ".html":
                mime_type = "text/html"
            else:
                mime_type = "application/octet-stream"

        if "text" in mime_type or mime_type in (
            "application/javascript",
            "application/json",
        ):
            mime_type += "; charset=utf-8"

        try:
            content = target_file.read_bytes()
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(f"Error reading file: {e}", status=500)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}\n"
        )


def run_server(host: str = HOST, port: int = PORT) -> None:
    db.init_db()
    server_address = (host, port)
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(server_address, SchemeBoardHandler)
    print(f"Scheme Board server running at http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
