"""End-to-end tests for the authentication module.

These tests use FastAPI's TestClient as a context manager so the application
lifespan runs (seeding admin + initializing repositories on ``app.state``).
The full dependency-injection stack exercises in-memory repositories.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Matches the seed admin configured in app.config.settings.
ADMIN_EMAIL = "admin@sentrix.io"
ADMIN_PASSWORD = "ChangeMe_123!"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the lifespan executed."""
    with TestClient(app) as c:
        yield c


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _valid_register_payload() -> dict[str, str]:
    return {
        "email": f"analyst_{uuid.uuid4().hex[:8]}@sentrix.io",
        "password": "StrongPass_123!",
        "full_name": "Test Analyst",
    }


def test_register_returns_token_pair(client: TestClient) -> None:
    payload = _valid_register_payload()
    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_register_duplicate_email_conflicts(client: TestClient) -> None:
    payload = _valid_register_payload()
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "user_already_exists"


def test_register_short_password_rejected(client: TestClient) -> None:
    payload = _valid_register_payload()
    payload["password"] = "short"
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_register_mixed_case_email_then_login_case_insensitive(
    client: TestClient,
) -> None:
    """Regression: register with a mixed-case email must be resolved at login.

    `register()` normalizes the email to lowercase before storing. Login must
    then succeed regardless of the case used in the login request.
    """
    payload = _valid_register_payload()
    payload["email"] = f"MiXeD_{uuid.uuid4().hex[:8]}@Sentrix.io"
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201

    # Login with a different case (lowercase) than the one used to register.
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"].lower(),
            "password": payload["password"],
        },
    )
    assert login.status_code == 200
    assert "access_token" in login.json()

    # Confirm the stored user email is normalized to lowercase.
    me = client.get(
        "/api/v1/auth/me",
        headers=_auth_headers(login.json()["access_token"]),
    )
    assert me.status_code == 200
    assert me.json()["email"] == payload["email"].lower()


def test_login_with_seeded_admin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_with_wrong_password_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@sentrix.io", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_me_returns_current_user(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = login.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"
    assert "password" not in body


def test_me_without_token_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_refresh_rotates_token(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert "access_token" in body
    assert "refresh_token" in body
    # Rotation means the new refresh token is different from the old one.
    assert body["refresh_token"] != refresh_token


def test_refresh_token_replay_detection(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]

    # First rotation succeeds.
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200

    # Replaying the same refresh token must be detected and rejected.
    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_revoked"


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout.status_code == 204

    # Using the revoked refresh token must now fail.
    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert replay.status_code == 401


def test_refresh_with_access_token_rejected(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    access_token = login.json()["access_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_users_list_requires_users_read(client: TestClient) -> None:
    # Register a non-admin (default SOC analyst role has no users:read).
    payload = _valid_register_payload()
    registered = client.post("/api/v1/auth/register", json=payload)
    token = registered.json()["access_token"]

    response = client.get("/api/v1/users", headers=_auth_headers(token))
    assert response.status_code == 403


def test_users_list_admin_allowed(client: TestClient) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = login.json()["access_token"]

    response = client.get("/api/v1/users", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1

