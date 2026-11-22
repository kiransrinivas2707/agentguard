from __future__ import annotations

import pytest

from conftest import login, register, upload_ok


def test_trash_restore_and_purge(client, app):
    register(client)
    file = upload_ok(client, "trash-me.txt", b"Invoice amount due 42")
    user_id = client.get("/api/auth/me").json()["id"]
    root = app.state.storage.user_root(user_id)

    deleted = client.delete(f"/api/files/{file['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["status"] == "trashed"
    assert (root / "Trash" / file["id"]).is_dir()
    assert client.get("/api/files").json() == []
    assert [entry["id"] for entry in client.get("/api/trash").json()] == [file["id"]]
    assert client.get("/api/search?q=invoice").json()["total"] == 0
    assert client.get("/api/files/stats/summary").json()["trashed"] == 1
    assert client.get(f"/api/files/{file['id']}/content").status_code == 200

    restore = client.post(f"/api/trash/{file['id']}/restore")
    assert restore.status_code == 200, restore.text
    restored = restore.json()
    assert restored["status"] == "classified"
    assert restored["folder_path"] == ["Inbox"]
    assert client.get("/api/trash").json() == []
    assert client.get(f"/api/files/{file['id']}").status_code == 200
    assert client.get("/api/search?q=invoice").json()["total"] == 1
    assert not (root / "Trash" / file["id"]).exists()

    assert client.delete(f"/api/files/{file['id']}").status_code == 200
    purge = client.delete(f"/api/trash/{file['id']}")
    assert purge.status_code == 200, purge.text
    assert client.get(f"/api/files/{file['id']}").status_code == 404
    assert client.get(f"/api/files/{file['id']}/content").status_code == 404
    assert client.get("/api/trash").json() == []
    assert not (root / "Trash" / file["id"]).exists()


def test_trash_validation_and_isolation(client):
    register(client, "alice@example.com")
    file = upload_ok(client, "private.txt", b"private invoice")
    client.post("/api/auth/logout")
    register(client, "bob@example.com")

    assert client.delete(f"/api/files/{file['id']}").status_code == 404
    assert client.get("/api/trash").json() == []

    client.post("/api/auth/logout")
    login(client, "alice@example.com")
    assert client.delete(f"/api/files/{file['id']}").status_code == 200
    assert client.delete(f"/api/files/{file['id']}").status_code == 400
    assert client.post(f"/api/trash/{file['id']}/restore").status_code == 200
    assert client.delete(f"/api/trash/{file['id']}").status_code == 400
