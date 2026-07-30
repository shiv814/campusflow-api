from __future__ import annotations

import argparse
import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import CoursePlanner, ValidationError


class CampusFlowHandler(BaseHTTPRequestHandler):
    planner = CoursePlanner()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        try:
            if parsed.path == "/health":
                self._json(HTTPStatus.OK, {"status": "ok", "service": "campusflow"})
                return
            if parts == ["courses"]:
                term = parse_qs(parsed.query).get("term", [None])[0]
                self._json(HTTPStatus.OK, {"courses": self.planner.list_courses(term)})
                return
            if len(parts) == 2 and parts[0] == "plans":
                self._json(HTTPStatus.OK, self.planner.get_plan(int(parts[1])))
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except (KeyError, ValueError):
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource not found"})

    def do_POST(self) -> None:
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        try:
            payload = self._body()
            if parts == ["courses"]:
                created = self.planner.add_course(
                    str(payload.get("code", "")),
                    str(payload.get("title", "")),
                    float(payload.get("credits", 0)),
                    str(payload.get("term", "")),
                    [str(value) for value in payload.get("prerequisites", [])],
                )
                self._json(HTTPStatus.CREATED, created)
                return
            if parts == ["plans"]:
                created = self.planner.create_plan(
                    str(payload.get("name", "")), float(payload.get("target_credits", 5.0))
                )
                self._json(HTTPStatus.CREATED, created)
                return
            if len(parts) == 3 and parts[0] == "plans" and parts[2] == "courses":
                updated = self.planner.add_course_to_plan(int(parts[1]), str(payload.get("code", "")))
                self._json(HTTPStatus.OK, updated)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
        except ValidationError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except sqlite3.IntegrityError:
            self._json(HTTPStatus.CONFLICT, {"error": "resource already exists"})
        except (KeyError, ValueError, TypeError):
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource not found or invalid request"})


def create_server(host: str, port: int, database: str) -> ThreadingHTTPServer:
    CampusFlowHandler.planner = CoursePlanner(database)
    return ThreadingHTTPServer((host, port), CampusFlowHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CampusFlow API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", default="campusflow.db")
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.database)
    print(f"CampusFlow listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
