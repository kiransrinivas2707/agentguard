from __future__ import annotations

from conftest import login, register, upload_ok


def test_cross_user_access_is_denied(client):
    register(client, "alice@example.com")
    file = upload_ok(client, "invoice.txt", b"Invoice total amount due 500")
    approve = client.post(f"/api/review/{file['id']}/approve", json={"file_id": file["id"]})
    operation_id = approve.json()["operation_id"]
    alice_folder = client.get("/api/folders").json()[1]

    client.post("/api/auth/logout")
    register(client, "bob@example.com")

    assert client.get(f"/api/files/{file['id']}").status_code == 404
    assert client.get(f"/api/files/{file['id']}/content").status_code == 404
    assert client.get(f"/api/files/{file['id']}/text").status_code == 404
    assert client.post(f"/api/review/{file['id']}/approve", json={"file_id": file["id"]}).status_code == 404
    assert client.post(f"/api/review/{file['id']}/reject").status_code == 404
    assert client.get(f"/api/operations/{operation_id}").status_code == 404
    assert client.post(f"/api/operations/{operation_id}/undo").status_code == 404
    assert client.post("/api/folders", json={"name": "Hijack", "parent_id": alice_folder["id"]}).status_code == 404

    assert client.get("/api/files").json() == []
    assert client.get("/api/review").json() == []
    assert client.get("/api/operations").json() == []
    assert client.get("/api/search?q=invoice").json()["total"] == 0
    folders = client.get("/api/folders").json()
    assert [folder["name"] for folder in folders] == ["Inbox"]

    client.post("/api/auth/logout")
    login(client, "alice@example.com")
    assert client.get(f"/api/files/{file['id']}").status_code == 200
    assert client.get("/api/search?q=invoice").json()["total"] == 1
