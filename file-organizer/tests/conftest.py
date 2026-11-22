from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.classifier import MockClassifier  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

PASSWORD = "password123"


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    scan_root = tmp_path / "scan-root"
    scan_root.mkdir()
    return Settings(
        data_dir=tmp_path / "data",
        secret="test-secret-value-0123456789-abcdefghij",
        classifier="mock",
        max_upload_bytes=2 * 1024 * 1024,
        allowed_origins=("http://localhost:5173",),
        auto_organize_default=False,
        scan_roots=(scan_root,),
    )


@pytest.fixture()
def app(settings: Settings):
    return create_app(settings, MockClassifier())


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def register(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD):
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return response


def login(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


def upload(client: TestClient, name: str, content: bytes, mime: str = "text/plain"):
    return client.post("/api/files", files=[("files", (name, content, mime))])


def upload_ok(client: TestClient, name: str, content: bytes, mime: str = "text/plain") -> dict:
    response = upload(client, name, content, mime)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert not payload["errors"], payload
    assert payload["uploaded"], payload
    file_id = payload["uploaded"][0]["id"]
    fresh = client.get(f"/api/files/{file_id}")
    assert fresh.status_code == 200, fresh.text
    return fresh.json()
