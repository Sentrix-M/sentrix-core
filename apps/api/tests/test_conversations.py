"""End-to-end tests for the conversation module.

Uses the FastAPI TestClient as a context manager so the application lifespan
runs and ``app.state.conversation_service`` is initialized.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app

ADMIN_EMAIL = "admin@sentrix.io"
ADMIN_PASSWORD = "ChangeMe_123!"


def _parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing ``Z`` designator."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the lifespan executed."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    """Log in as the seeded admin and return the access token."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _valid_payload() -> dict[str, str]:
    return {
        "conversation_id": f"conv-{uuid.uuid4().hex[:8]}",
        "message": "Investigate the beacon pattern on LAB-07",
    }


def test_send_message_returns_response(client: TestClient, admin_token: str) -> None:
    payload = _valid_payload()
    headers = _auth_headers(admin_token)
    response = client.post("/api/v1/conversations/message", json=payload, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == payload["conversation_id"]
    assert body["response"]
    assert body["timestamp"]
    _parse_iso_timestamp(body["timestamp"])


def test_send_message_includes_mock_metadata(client: TestClient, admin_token: str) -> None:
    payload = _valid_payload()
    headers = _auth_headers(admin_token)
    response = client.post("/api/v1/conversations/message", json=payload, headers=headers)

    body = response.json()
    metadata = body["metadata"]
    assert metadata["model"] == "sentrix-mock-0.1"
    # The REST /message path is now kernel-backed, so the mock provider
    # surfaces its reasoning trace and the response reflects the pipeline.
    assert metadata["reasoning"]
    assert metadata["evidence"] is None
    assert metadata["sources"] is None
    assert metadata["execution_time_ms"] is not None


def test_send_message_empty_rejected(client: TestClient, admin_token: str) -> None:
    payload = _valid_payload()
    payload["message"] = ""
    headers = _auth_headers(admin_token)
    response = client.post("/api/v1/conversations/message", json=payload, headers=headers)
    assert response.status_code == 422


def test_send_message_missing_conversation_id_rejected(client: TestClient, admin_token: str) -> None:
    payload = _valid_payload()
    del payload["conversation_id"]
    headers = _auth_headers(admin_token)
    response = client.post("/api/v1/conversations/message", json=payload, headers=headers)
    assert response.status_code == 422

