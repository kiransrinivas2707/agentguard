from __future__ import annotations

from conftest import PASSWORD, register, upload, upload_ok


def test_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_cross_origin_mutation_is_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    allowed = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert allowed.status_code == 401


def test_login_throttle_blocks_after_repeated_failures(client):
    register(client, "throttle@example.com")
    client.post("/api/auth/logout")
    for _ in range(10):
        response = client.post(
            "/api/auth/login",
            json={"email": "throttle@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/api/auth/login",
        json={"email": "throttle@example.com", "password": PASSWORD},
    )
    assert blocked.status_code == 429


def test_uploaded_filename_is_sanitized(client):
    register(client)
    file = upload_ok(client, "<script>alert.txt", b"plain notes")
    assert "<" not in file["current_name"]
    assert ">" not in file["current_name"]
    assert file["current_name"].endswith(".txt")


def test_unpreviewable_type_returns_415(client):
    register(client)
    file = upload_ok(client, "program.exe", b"MZbinary", "application/octet-stream")
    response = client.get(f"/api/files/{file['id']}/content")
    assert response.status_code == 415


def test_upload_errors_do_not_leak_internal_details(client):
    register(client)
    response = upload(client, "fake.pdf", b"not a pdf", "application/pdf")
    error = response.json()["errors"][0]["error"]
    assert "Traceback" not in error
    assert "C:\\" not in error
