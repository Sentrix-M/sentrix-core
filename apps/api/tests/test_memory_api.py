"""Tests for the /api/v1/memory HTTP endpoints (Phase 15A).

Builds a minimal FastAPI app that mounts the memory router and sets
``app.state.memory_service`` so the ``get_memory_service`` dependency
resolves to a deterministic in-memory service.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.memory import router
from app.memory.service import MemoryService


@pytest.fixture
def app() -> FastAPI:
    """A FastAPI app with the memory router on a fresh in-memory service."""
    app = FastAPI()
    app.state.memory_service = MemoryService()
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """A TestClient bound to the fixture app."""
    return TestClient(app)


def test_list_reports_empty(client: TestClient) -> None:
    """Reports endpoint returns an empty list initially."""
    resp = client.get("/memory/reports")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_health_of_memory_routes(client: TestClient) -> None:
    """All memory read endpoints respond 200."""
    for path in (
        "/memory/reports",
        "/memory/preferences",
        "/memory/findings",
        "/memory/investigations",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"


def test_recall_requires_query(client: TestClient) -> None:
    """The recall endpoint requires a non-empty query string."""
    resp = client.get("/memory/recall")
    assert resp.status_code == 422


def test_recall_empty_result(client: TestClient) -> None:
    """Recall with no matching data returns an empty result."""
    resp = client.get("/memory/recall", params={"q": "8.8.8.8"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == []


def test_memory_service_wired_on_state(app: FastAPI, client: TestClient) -> None:
    """The dependency resolves the service stored on app state."""
    service = app.state.memory_service
    service.record_report(title="Incident A", report_format="json")
    resp = client.get("/memory/reports")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Incident A"
