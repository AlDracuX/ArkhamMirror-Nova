"""HTTP client for the SHATTERED REST API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class ServerUnreachableError(Exception):
    """Raised when the SHATTERED server cannot be reached."""

    def __init__(self, url: str, reason: str = "") -> None:
        self.url = url
        self.reason = reason
        detail = f" ({reason})" if reason else ""
        super().__init__(f"Cannot reach SHATTERED server at {url}{detail}")


class APIError(Exception):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str, url: str) -> None:
        self.status_code = status_code
        self.body = body
        self.url = url
        excerpt = body[:200] if len(body) > 200 else body
        super().__init__(f"HTTP {status_code} from {url}: {excerpt}")


class ShatteredClient:
    """Pure HTTP client for the SHATTERED litigation analysis platform API."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # -- internal helpers --

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = self._url(path)
        kwargs.setdefault("timeout", self.timeout)
        try:
            resp = self._session.request(method, url, **kwargs)
        except requests.ConnectionError as exc:
            raise ServerUnreachableError(url, reason="connection refused") from exc
        except requests.Timeout as exc:
            raise ServerUnreachableError(url, reason=f"timeout after {self.timeout}s") from exc

        if not resp.ok:
            raise APIError(resp.status_code, resp.text, url)

        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params)

    def _post(self, path: str, json: dict | None = None, **kwargs: Any) -> dict:
        return self._request("POST", path, json=json, **kwargs)

    # -- status endpoints --

    def health(self) -> dict:
        """GET /api/health"""
        return self._get("/api/health")

    def status(self) -> dict:
        """GET /api/status"""
        return self._get("/api/status")

    # -- document endpoints --

    def documents(
        self,
        status: str | None = None,
        doc_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """GET /api/documents"""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if doc_type:
            params["type"] = doc_type
        return self._get("/api/documents", params=params)

    def document_stats(self) -> dict:
        """GET /api/documents/stats"""
        return self._get("/api/documents/stats")

    # -- ingest --

    def upload(self, file_path: Path) -> dict:
        """POST /api/ingest/upload (multipart file upload)."""
        with open(file_path, "rb") as f:
            return self._request(
                "POST",
                "/api/ingest/upload",
                files={"file": (file_path.name, f)},
            )

    # -- rules --

    def rules_seed(self) -> dict:
        """POST /api/rules/seed"""
        return self._post("/api/rules/seed")

    # -- burden map --

    def burden_populate(self, case_id: str, claim_type: str) -> dict:
        """POST /api/burden-map/populate"""
        return self._post("/api/burden-map/populate", json={"case_id": case_id, "claim_type": claim_type})

    # -- disclosure --

    def disclosure_gaps(self, case_id: str) -> dict:
        """POST /api/disclosure/gaps/detect"""
        return self._post("/api/disclosure/gaps/detect", json={"case_id": case_id})

    def disclosure_evasion(self, respondent_id: str, case_id: str) -> dict:
        """POST /api/disclosure/evasion/score"""
        return self._post("/api/disclosure/evasion/score", json={"respondent_id": respondent_id, "case_id": case_id})

    # -- costs --

    def costs_conduct_score(self, project_id: str) -> dict:
        """POST /api/costs/conduct/score"""
        return self._post("/api/costs/conduct/score", json={"project_id": project_id})

    # -- respondent intel --

    def respondent_profiles(self, case_id: str) -> dict:
        """POST /api/respondent-intel/profiles/build"""
        return self._post("/api/respondent-intel/profiles/build", json={"case_id": case_id})

    # -- comms --

    def comms_gaps(self, case_id: str) -> dict:
        """GET /api/comms/gaps"""
        return self._get("/api/comms/gaps", params={"case_id": case_id})

    # -- comparator --

    def comparator_s13(self, case_id: str) -> dict:
        """GET /api/comparator/elements/s13/{case_id}"""
        return self._get(f"/api/comparator/elements/s13/{case_id}")

    def comparator_s26(self, case_id: str) -> dict:
        """GET /api/comparator/elements/s26/{case_id}"""
        return self._get(f"/api/comparator/elements/s26/{case_id}")

    # -- crossexam --

    def crossexam_generate(self, case_id: str, witness_name: str, topics: list[str]) -> dict:
        """POST /api/crossexam/generate"""
        return self._post(
            "/api/crossexam/generate",
            json={"case_id": case_id, "witness_name": witness_name, "topics": topics},
        )

    # -- skeleton --

    def skeleton_build(self, claim_id: str) -> dict:
        """POST /api/skeleton/tree/build"""
        return self._post("/api/skeleton/tree/build", json={"claim_id": claim_id})

    # -- timeline --

    def timeline_events(self, case_id: str) -> dict:
        """GET /api/timeline/events"""
        return self._get("/api/timeline/events", params={"case_id": case_id})
