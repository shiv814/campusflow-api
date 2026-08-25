"""Tiny dependency-free client for the CampusFlow HTTP API."""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class CampusFlowClientError(RuntimeError):
    pass


class CampusFlowClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", *, timeout: float = 5.0, retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def _request(self, method: str, path: str, body: dict | None = None, query: dict | None = None):
        url = self.base_url + path
        if query:
            url += "?" + urlencode({key: value for key, value in query.items() if value is not None})
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, method=method, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else None
            except HTTPError as exc:
                payload = exc.read().decode("utf-8", "replace")
                raise CampusFlowClientError(f"HTTP {exc.code}: {payload}") from exc
            except URLError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.1 * (2**attempt))
        raise CampusFlowClientError(f"request failed: {last_error}")

    def health(self): return self._request("GET", "/health")
    def courses(self, **filters): return self._request("GET", "/courses", query=filters)
    def course(self, code: str): return self._request("GET", f"/courses/{code}")
    def plans(self): return self._request("GET", "/plans")
    def validate_plan(self, plan_id: int): return self._request("GET", f"/plans/{plan_id}/validate")
