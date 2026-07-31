from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import ConflictError, CoursePlanner, ValidationError


class CampusFlowHandler(BaseHTTPRequestHandler):
    planner = CoursePlanner()
    server_version = "CampusFlow/2.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: object, *, headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.send_header("Access-Control-Allow-Origin", "*")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _csv(self, status: int, text: str, filename: str) -> None:
        encoded = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValidationError("invalid Content-Length") from error
        if length > 1_000_000:
            raise ValidationError("request body is too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValidationError("request body must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValidationError("request body must be a JSON object")
        return payload

    @staticmethod
    def _bool_query(value: str | None, default: bool | None = None) -> bool | None:
        if value is None:
            return default
        lowered = value.lower()
        if lowered in {"1", "true", "yes"}:
            return True
        if lowered in {"0", "false", "no"}:
            return False
        raise ValidationError("boolean query value must be true or false")

    def _dispatch(self) -> None:
        self.request_id = self.headers.get("X-Request-ID") or str(uuid.uuid4())
        parsed = urlparse(self.path)
        parts = [part for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)
        method = self.command

        if method == "OPTIONS":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Request-ID")
            self.end_headers()
            return

        if method == "GET" and parts == ["health"]:
            self._json(HTTPStatus.OK, {"status": "ok", "service": "campusflow", "version": "2.0"})
            return
        if method == "GET" and parts == ["analytics"]:
            self._json(HTTPStatus.OK, self.planner.analytics())
            return
        if method == "GET" and parts == ["courses"]:
            courses = self.planner.list_courses(
                query.get("term", [None])[0],
                department=query.get("department", [None])[0],
                query=query.get("q", [None])[0],
                active=self._bool_query(query.get("active", [None])[0], True),
                min_credits=float(query["min_credits"][0]) if "min_credits" in query else None,
                max_credits=float(query["max_credits"][0]) if "max_credits" in query else None,
                limit=int(query.get("limit", [100])[0]),
                offset=int(query.get("offset", [0])[0]),
            )
            self._json(HTTPStatus.OK, {"count": len(courses), "courses": courses})
            return
        if method == "POST" and parts == ["courses"]:
            payload = self._body()
            created = self.planner.add_course(
                str(payload.get("code", "")),
                str(payload.get("title", "")),
                float(payload.get("credits", 0)),
                str(payload.get("term", "")),
                [str(value) for value in payload.get("prerequisites", [])],
                department=str(payload.get("department", "")),
                description=str(payload.get("description", "")),
                capacity=int(payload.get("capacity", 0)),
                delivery=str(payload.get("delivery", "In Person")),
                meetings=payload.get("meetings", []),
            )
            self._json(HTTPStatus.CREATED, created, headers={"Location": f"/courses/{created['code']}"})
            return
        if len(parts) == 2 and parts[0] == "courses":
            code = parts[1]
            if method == "GET":
                self._json(HTTPStatus.OK, self.planner.get_course(code))
                return
            if method == "PATCH":
                self._json(HTTPStatus.OK, self.planner.update_course(code, **self._body()))
                return
            if method == "DELETE":
                self.planner.delete_course(code)
                self._json(HTTPStatus.OK, {"deleted": code.upper()})
                return
        if method == "GET" and parts == ["plans"]:
            plans = self.planner.list_plans(query.get("status", [None])[0])
            self._json(HTTPStatus.OK, {"count": len(plans), "plans": plans})
            return
        if method == "POST" and parts == ["plans"]:
            payload = self._body()
            created = self.planner.create_plan(
                str(payload.get("name", "")),
                float(payload.get("target_credits", 5.0)),
                student_id=str(payload.get("student_id", "")),
                start_term=str(payload.get("start_term", "")),
                status=str(payload.get("status", "Draft")),
            )
            self._json(HTTPStatus.CREATED, created, headers={"Location": f"/plans/{created['id']}"})
            return
        if len(parts) >= 2 and parts[0] == "plans":
            plan_id = int(parts[1])
            if len(parts) == 2:
                if method == "GET":
                    self._json(HTTPStatus.OK, self.planner.get_plan(plan_id))
                    return
                if method == "PATCH":
                    self._json(HTTPStatus.OK, self.planner.update_plan(plan_id, **self._body()))
                    return
                if method == "DELETE":
                    self.planner.delete_plan(plan_id)
                    self._json(HTTPStatus.OK, {"deleted": plan_id})
                    return
            if len(parts) == 3 and parts[2] == "validate" and method == "GET":
                self._json(HTTPStatus.OK, self.planner.validate_plan(plan_id))
                return
            if len(parts) == 3 and parts[2] == "recommendations" and method == "GET":
                items = self.planner.recommend_courses(
                    plan_id,
                    term=query.get("term", [None])[0],
                    limit=int(query.get("limit", [5])[0]),
                )
                self._json(HTTPStatus.OK, {"plan_id": plan_id, "recommendations": items})
                return
            if len(parts) == 3 and parts[2] == "export.csv" and method == "GET":
                self._csv(HTTPStatus.OK, self.planner.export_plan_csv(plan_id), f"campusflow-plan-{plan_id}.csv")
                return
            if len(parts) == 3 and parts[2] == "courses" and method == "POST":
                payload = self._body()
                updated = self.planner.add_course_to_plan(
                    plan_id,
                    str(payload.get("code", "")),
                    completed=bool(payload.get("completed", False)),
                    grade=float(payload["grade"]) if payload.get("grade") is not None else None,
                    notes=str(payload.get("notes", "")),
                )
                self._json(HTTPStatus.OK, updated)
                return
            if len(parts) == 4 and parts[2] == "courses":
                code = parts[3]
                if method == "PATCH":
                    self._json(HTTPStatus.OK, self.planner.update_plan_course(plan_id, code, **self._body()))
                    return
                if method == "DELETE":
                    self._json(HTTPStatus.OK, self.planner.remove_course_from_plan(plan_id, code))
                    return
        self._json(HTTPStatus.NOT_FOUND, {"error": "route not found", "request_id": self.request_id})

    def _safe_dispatch(self) -> None:
        try:
            self._dispatch()
        except ValidationError as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error), "request_id": getattr(self, "request_id", "")})
        except ConflictError as error:
            self._json(HTTPStatus.CONFLICT, {"error": str(error), "request_id": getattr(self, "request_id", "")})
        except sqlite3.IntegrityError as error:
            message = "resource already exists" if "UNIQUE" in str(error).upper() else "database constraint failed"
            self._json(HTTPStatus.CONFLICT, {"error": message, "request_id": getattr(self, "request_id", "")})
        except (KeyError, ValueError):
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource not found", "request_id": getattr(self, "request_id", "")})

    do_GET = _safe_dispatch
    do_POST = _safe_dispatch
    do_PATCH = _safe_dispatch
    do_DELETE = _safe_dispatch
    do_OPTIONS = _safe_dispatch


def create_server(host: str = "127.0.0.1", port: int = 8080, database: str = "campusflow.db") -> ThreadingHTTPServer:
    handler = type("ConfiguredCampusFlowHandler", (CampusFlowHandler,), {"planner": CoursePlanner(database)})
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the CampusFlow academic planning API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", default="campusflow.db")
    args = parser.parse_args()
    server = create_server(args.host, args.port, args.database)
    print(f"CampusFlow API listening on http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
