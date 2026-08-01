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


def _parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, tolerating a trailing ``Z`` designator.

    Python 3.10's ``datetime.fromisoformat`` does not accept ``Z`` (added in
    3.11); Pydantic emits ``...Z`` for UTC datetimes. Normalize to ``+00:00``.
    """
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the lifespan executed."""
    with TestClient(app) as c:
        yield c


def _valid_payload() -> dict[str, str]:
    return {
        "conversation_id": f"conv-{uuid.uuid4().hex[:8]}",
        "message": "Investigate the beacon pattern on LAB-07",
    }


def test_send_message_returns_response(client: TestClient) -> None:
    payload = _valid_payload()
    response = client.post("/api/v1/conversations/message", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == payload["conversation_id"]
    assert body["response"]
    assert body["timestamp"]
    # The timestamp must serialize as an ISO 8601 datetime.
    _parse_iso_timestamp(body["timestamp"])


def test_send_message_includes_mock_metadata(client: TestClient) -> None:
    payload = _valid_payload()
    response = client.post("/api/v1/conversations/message", json=payload)

    body = response.json()
    metadata = body["metadata"]
    assert metadata["model"] == "sentrix-mock-0.1"
    # Reserved AI-engine fields are present but unpopulated in mock mode.
    assert metadata["reasoning"] is None
    assert metadata["evidence"] is None
    assert metadata["sources"] is None
    assert metadata["tools_used"] is None
    assert metadata["execution_time_ms"] is not None


def test_send_message_empty_rejected(client: TestClient) -> None:
    payload = _valid_payload()
    payload["message"] = ""
    response = client.post("/api/v1/conversations/message", json=payload)
    assert response.status_code == 422


def test_send_message_missing_conversation_id_rejected(client: TestClient) -> None:
    payload = _valid_payload()
    del payload["conversation_id"]
    response = client.post("/api/v1/conversations/message", json=payload)
    assert response.status_code == 422

