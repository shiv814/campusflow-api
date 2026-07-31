import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from campusflow.api import create_server


def request(url, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=3) as response:
            body = response.read().decode("utf-8")
            return response.status, response.headers, json.loads(body) if body else None
    except HTTPError as error:
        return error.code, error.headers, json.loads(error.read().decode("utf-8"))


def test_full_http_workflow(tmp_path):
    server = create_server("127.0.0.1", 0, str(tmp_path / "api.db"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, headers, health = request(base + "/health")
        assert status == 200 and health["version"] == "2.0"
        assert headers["X-Request-ID"]
        status, _, course = request(
            base + "/courses", "POST",
            {"code": "CIS1500", "title": "Intro Programming", "credits": 0.5, "term": "Fall", "department": "Computing"},
        )
        assert status == 201 and course["department"] == "Computing"
        status, _, _ = request(
            base + "/courses", "POST",
            {"code": "CIS2500", "title": "Intermediate Programming", "credits": 0.5, "term": "Winter", "prerequisites": ["CIS1500"]},
        )
        assert status == 201
        status, _, listing = request(base + "/courses?q=program&department=Computing")
        assert status == 200 and listing["count"] == 1
        status, _, plan = request(base + "/plans", "POST", {"name": "Degree Plan", "target_credits": 1.0, "student_id": "1001"})
        assert status == 201
        request(base + f"/plans/{plan['id']}/courses", "POST", {"code": "CIS1500", "completed": True, "grade": 92})
        status, _, updated = request(base + f"/plans/{plan['id']}/courses", "POST", {"code": "CIS2500"})
        assert status == 200 and updated["remaining_credits"] == 0.0
        status, _, validation = request(base + f"/plans/{plan['id']}/validate")
        assert status == 200 and validation["valid"] is True
        status, _, analytics = request(base + "/analytics")
        assert analytics["course_count"] == 2 and analytics["plan_count"] == 1
        status, _, updated_course = request(base + "/courses/CIS2500", "PATCH", {"delivery": "Hybrid"})
        assert status == 200 and updated_course["delivery"] == "Hybrid"
        status, _, removed = request(base + f"/plans/{plan['id']}/courses/CIS2500", "DELETE")
        assert status == 200 and len(removed["courses"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_errors_are_structured(tmp_path):
    server = create_server("127.0.0.1", 0, str(tmp_path / "api.db"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, _, error = request(base + "/courses", "POST", {"code": "bad"})
        assert status == 400 and error["request_id"]
        status, _, error = request(base + "/plans/999")
        assert status == 404 and error["error"] == "resource not found"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
