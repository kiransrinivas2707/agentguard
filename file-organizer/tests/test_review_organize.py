from __future__ import annotations

from conftest import register, upload_ok


def _resume(client, name: str = "my resume.txt", text: bytes = b"My resume. Curriculum vitae. Python developer."):
    return upload_ok(client, name, text)


def test_approve_organizes_and_undo_restores(client, app):
    register(client)
    file = _resume(client)
    assert file["classification"]["suggested_path"] == ["Career", "Resumes"]

    review = client.get("/api/review").json()
    assert [item["id"] for item in review] == [file["id"]]

    response = client.post(f"/api/review/{file['id']}/approve", json={"file_id": file["id"]})
    assert response.status_code == 200, response.text
    payload = response.json()
    organized = payload["file"]
    assert organized["status"] == "organized"
    assert organized["folder_path"] == ["Career", "Resumes"]
    assert organized["current_name"] == "Resume.txt"
    assert organized["classification"]["applied"] is True

    user_id = client.get("/api/auth/me").json()["id"]
    root = app.state.storage.user_root(user_id)
    assert (root / "Career" / "Resumes" / "Resume.txt").is_file()
    assert not (root / "Inbox" / "my resume.txt").exists()

    operations = client.get("/api/operations").json()
    assert len(operations) == 1
    operation = operations[0]
    assert operation["status"] == "applied"
    assert operation["items"][0]["from_path"].startswith("Inbox/")
    assert operation["items"][0]["to_path"] == "Career/Resumes/Resume.txt"

    undo = client.post(f"/api/operations/{payload['operation_id']}/undo")
    assert undo.status_code == 200, undo.text
    assert undo.json()["errors"] == []
    restored = client.get(f"/api/files/{file['id']}").json()
    assert restored["folder_path"] == ["Inbox"]
    assert restored["status"] == "classified"
    assert restored["current_name"] == "my resume.txt"
    assert (root / "Inbox" / "my resume.txt").is_file()
    assert not (root / "Career").exists()
    assert client.get("/api/folders").json()[0]["name"] == "Inbox"

    second_undo = client.post(f"/api/operations/{payload['operation_id']}/undo")
    assert second_undo.status_code == 409


def test_approve_accepts_user_edits(client):
    register(client)
    file = _resume(client)
    response = client.post(
        f"/api/review/{file['id']}/approve",
        json={
            "file_id": file["id"],
            "name": "Platform Engineer Resume.txt",
            "path": ["Work", "Applications"],
            "tags": ["resume", "platform"],
            "document_type": "resume",
            "category": "Work",
            "subcategory": "Applications",
        },
    )
    assert response.status_code == 200, response.text
    organized = response.json()["file"]
    assert organized["folder_path"] == ["Work", "Applications"]
    assert organized["current_name"] == "Platform Engineer Resume.txt"
    assert "platform" in organized["classification"]["tags"]
    assert organized["classification"]["provider"] == "manual"


def test_reject_keeps_file_in_inbox(client):
    register(client)
    file = upload_ok(client, "mystery.txt", b"unstructured content with no strong signal")
    assert file["status"] == "needs_review"
    response = client.post(f"/api/review/{file['id']}/reject")
    assert response.status_code == 200
    rejected = response.json()
    assert rejected["status"] == "inbox"
    assert rejected["folder_path"] == ["Inbox"]
    assert client.get("/api/review").json() == []
    assert client.get(f"/api/files/{file['id']}").status_code == 200


def test_collision_safe_filenames(client):
    register(client)
    first = _resume(client, "resume.txt", b"resume one python")
    second = _resume(client, "resume.txt", b"resume two golang")
    assert first["id"] != second["id"]
    r1 = client.post(f"/api/review/{first['id']}/approve", json={"file_id": first["id"]})
    r2 = client.post(f"/api/review/{second['id']}/approve", json={"file_id": second["id"]})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["file"]["current_name"] == "Resume.txt"
    assert r2.json()["file"]["current_name"] == "Resume (2).txt"


def test_unsafe_paths_are_rejected(client):
    register(client)
    file = _resume(client)
    attempts = [
        {"path": ["..", "etc"]},
        {"path": ["C:\\Windows"]},
        {"path": ["a", "b", "c", "d", "e"]},
        {"name": "..\\..\\evil.txt"},
        {"name": "C:\\evil.txt"},
        {"name": "folder/evil.txt"},
    ]
    for attempt in attempts:
        response = client.post(
            f"/api/review/{file['id']}/approve",
            json={"file_id": file["id"], **attempt},
        )
        assert response.status_code == 400, (attempt, response.text)
    still = client.get(f"/api/files/{file['id']}").json()
    assert still["status"] == "classified"
    assert still["folder_path"] == ["Inbox"]


def test_batch_approval_reports_partial_failures(client):
    register(client)
    first = _resume(client, "one.txt", b"resume alpha")
    second = _resume(client, "two.txt", b"resume beta")
    response = client.post(
        "/api/review/approve-batch",
        json={"items": [{"file_id": first["id"]}, {"file_id": "missing-id"}]},
    )
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert results[0]["ok"] is True and results[0]["operation_id"]
    assert results[1]["ok"] is False and results[1]["error"] == "File not found"
    assert client.get(f"/api/files/{first['id']}").json()["status"] == "organized"
    assert client.get(f"/api/files/{second['id']}").json()["status"] in {"classified", "needs_review"}


def test_folder_creation_and_depth_limit(client):
    register(client)
    created = client.post("/api/folders", json={"name": "Career"})
    assert created.status_code == 201
    career = created.json()
    child = client.post("/api/folders", json={"name": "Certs", "parent_id": career["id"]})
    assert child.status_code == 201
    duplicate = client.post("/api/folders", json={"name": "career"})
    assert duplicate.status_code == 409
    traversal = client.post("/api/folders", json={"name": ".."})
    assert traversal.status_code == 400
    absolute = client.post("/api/folders", json={"name": "C:\\Windows"})
    assert absolute.status_code == 400

    parent_id = child.json()["id"]
    for index in range(3):
        response = client.post("/api/folders", json={"name": f"Level{index}", "parent_id": parent_id})
        if index < 2:
            assert response.status_code == 201
            parent_id = response.json()["id"]
        else:
            assert response.status_code == 400
