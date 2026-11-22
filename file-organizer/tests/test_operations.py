from __future__ import annotations

from conftest import register, upload_ok

from app.models import File


def test_operation_history_and_partial_undo(client, app):
    register(client)
    file = upload_ok(client, "resume.txt", b"resume python developer")
    approve = client.post(f"/api/review/{file['id']}/approve", json={"file_id": file["id"]})
    assert approve.status_code == 200
    operation_id = approve.json()["operation_id"]

    operations = client.get("/api/operations").json()
    assert len(operations) == 1
    assert operations[0]["items"][0]["status"] == "applied"

    session = app.state.sessionmaker()
    try:
        row = session.get(File, file["id"])
        row.storage_path = "Inbox/moved-by-someone-else.txt"
        session.commit()
    finally:
        session.close()

    undo = client.post(f"/api/operations/{operation_id}/undo")
    assert undo.status_code == 200
    payload = undo.json()
    assert payload["operation"]["status"] == "partial_undo"
    assert payload["errors"]
    assert "changed" in payload["errors"][0]
    assert payload["operation"]["items"][0]["status"] == "failed"

    again = client.post(f"/api/operations/{operation_id}/undo")
    assert again.status_code == 409


def test_reorganizing_an_organized_file_is_reversible(client):
    register(client)
    file = upload_ok(client, "resume.txt", b"resume python developer")
    first = client.post(f"/api/review/{file['id']}/approve", json={"file_id": file["id"]})
    assert first.status_code == 200
    second = client.post(
        f"/api/review/{file['id']}/approve",
        json={"file_id": file["id"], "path": ["Archive"], "name": "old-resume.txt"},
    )
    assert second.status_code == 200, second.text
    moved = second.json()["file"]
    assert moved["folder_path"] == ["Archive"]
    assert moved["current_name"] == "old-resume.txt"
    undo = client.post(f"/api/operations/{second.json()['operation_id']}/undo")
    assert undo.status_code == 200
    restored = client.get(f"/api/files/{file['id']}").json()
    assert restored["folder_path"] == ["Career", "Resumes"]
    assert restored["status"] == "organized"
