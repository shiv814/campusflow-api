import json
import threading
from urllib.request import Request, urlopen

from campusflow.api import create_server


def request_json(url, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_http_workflow(tmp_path):
    server = create_server("127.0.0.1", 0, str(tmp_path / "api.db"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, health = request_json(base + "/health")
        assert status == 200 and health["status"] == "ok"
        status, course = request_json(
            base + "/courses",
            "POST",
            {"code": "ENGG2410", "title": "Digital Systems", "credits": 0.5, "term": "Fall"},
        )
        assert status == 201 and course["code"] == "ENGG2410"
        status, plan = request_json(base + "/plans", "POST", {"name": "Fall Plan", "target_credits": 0.5})
        assert status == 201
        status, updated = request_json(
            base + f"/plans/{plan['id']}/courses", "POST", {"code": "ENGG2410"}
        )
        assert status == 200 and updated["remaining_credits"] == 0.0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
