from __future__ import annotations

from conftest import PASSWORD, login, register


def test_register_login_logout_flow(client):
    response = register(client)
    body = response.json()
    assert body["email"] == "alice@example.com"
    assert "password" not in body and "password_hash" not in body

    cookie = response.headers.get("set-cookie", "")
    assert "fo_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    login(client)
    assert client.get("/api/auth/me").status_code == 200


def test_duplicate_email_is_case_insensitive(client):
    register(client, "Alice@Example.com")
    client.post("/api/auth/logout")
    response = client.post("/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD})
    assert response.status_code == 409


def test_wrong_password_and_unknown_user_are_generic(client):
    register(client)
    client.post("/api/auth/logout")
    wrong = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_weak_password_rejected(client):
    response = client.post("/api/auth/register", json={"email": "weak@example.com", "password": "short"})
    assert response.status_code == 422


def test_protected_routes_require_auth(client):
    for path in ("/api/files", "/api/folders", "/api/review", "/api/operations", "/api/search"):
        assert client.get(path).status_code == 401, path


def test_logout_cookie_is_cleared(client):
    register(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "")
    assert "fo_session=" in cookie
