from __future__ import annotations

from io import BytesIO

from PIL import Image
from sqlalchemy import func, select

from conftest import register, upload_ok

from app.models import Feedback


def _image_bytes(color: tuple[int, int, int] = (50, 80, 180)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _enable_auto(client, threshold: float = 0.8):
    response = client.patch(
        "/api/preferences",
        json={"auto_organize_enabled": True, "auto_organize_threshold": threshold},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_preferences_default_and_validation(client):
    register(client)
    preferences = client.get("/api/preferences").json()
    assert preferences["auto_organize_enabled"] is False
    assert preferences["auto_organize_threshold"] == 0.8
    assert preferences["scan_roots"]
    assert preferences["google_drive"] == "setup_required"

    invalid = client.patch("/api/preferences", json={"auto_organize_threshold": 1.5})
    assert invalid.status_code == 422
    invalid_low = client.patch("/api/preferences", json={"auto_organize_threshold": 0.1})
    assert invalid_low.status_code == 422


def test_high_confidence_auto_organizes_and_is_undoable(client):
    register(client)
    _enable_auto(client)
    file = upload_ok(client, "auto-resume.txt", b"resume python developer curriculum vitae")
    assert file["status"] == "organized"
    assert file["folder_path"] == ["Career", "Resumes"]
    assert file["classification"]["applied"] is True

    operations = client.get("/api/operations").json()
    assert operations[0]["kind"] == "auto"
    undo = client.post(f"/api/operations/{operations[0]['id']}/undo")
    assert undo.status_code == 200
    restored = client.get(f"/api/files/{file['id']}").json()
    assert restored["folder_path"] == ["Inbox"]


def test_low_confidence_review_then_learning_auto_organizes(client, app):
    register(client)
    _enable_auto(client)

    first = upload_ok(client, "scan-one.jpg", _image_bytes((40, 80, 160)), "image/jpeg")
    assert first["status"] in {"classified", "needs_review"}
    assert first["classification"]["document_type"] == "photo"
    assert first["classification"]["confidence"] < 0.8

    approved = client.post(
        f"/api/review/{first['id']}/approve",
        json={
            "file_id": first["id"],
            "name": "signature-scan.jpg",
            "path": ["Personal", "Signatures"],
            "tags": ["signature", "scan"],
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["file"]["folder_path"] == ["Personal", "Signatures"]

    session = app.state.sessionmaker()
    try:
        approved_feedback = session.scalar(
            select(func.count(Feedback.id)).where(Feedback.decision == "approved")
        )
        assert approved_feedback == 1
    finally:
        session.close()

    second = upload_ok(client, "scan-two.jpg", _image_bytes((160, 40, 80)), "image/jpeg")
    assert second["status"] == "organized", second
    assert second["folder_path"] == ["Personal", "Signatures"]
    assert second["classification"]["confidence"] >= 0.8


def test_auto_organize_disabled_keeps_file_in_review(client):
    register(client)
    file = upload_ok(client, "manual-resume.txt", b"resume python developer")
    assert file["status"] == "classified"
    assert file["folder_path"] == ["Inbox"]
    assert client.get("/api/review").json()[0]["id"] == file["id"]


def test_rejected_decision_is_tracked(client, app):
    register(client)
    file = upload_ok(client, "mystery.txt", b"unstructured content with no signal")
    assert file["status"] == "needs_review"
    assert client.post(f"/api/review/{file['id']}/reject").status_code == 200

    session = app.state.sessionmaker()
    try:
        rejected = session.scalar(select(func.count(Feedback.id)).where(Feedback.decision == "rejected"))
        assert rejected == 1
    finally:
        session.close()


def test_run_now_organizes_existing_high_confidence(client, app):
    register(client)
    file = upload_ok(client, "existing-resume.txt", b"resume python developer")
    assert file["status"] == "classified"

    from app.files import latest_classification
    from app.models import File

    session = app.state.sessionmaker()
    try:
        row = session.get(File, file["id"])
        classification = latest_classification(session, file["id"])
        classification.requires_review = True
        classification.error = "Automatic organization failed. Review the proposal and place the file manually."
        row.status = "needs_review"
        session.commit()
    finally:
        session.close()

    _enable_auto(client)
    response = client.post("/api/automation/run")
    assert response.status_code == 200, response.text
    assert response.json()["organized"] >= 1
    moved = client.get(f"/api/files/{file['id']}").json()
    assert moved["status"] == "organized"
    assert moved["folder_path"] == ["Career", "Resumes"]


def test_cleanup_removes_only_empty_folders(client):
    register(client)
    created = client.post("/api/folders", json={"name": "Empty Folder"})
    assert created.status_code == 201
    response = client.post("/api/folders/cleanup-empty")
    assert response.status_code == 200
    assert response.json()["removed"] == 1
    names = [folder["name"] for folder in client.get("/api/folders").json()]
    assert names == ["Inbox"]


def test_local_import_reads_only_configured_roots(client, app, tmp_path):
    register(client)
    root = app.state.settings.scan_roots[0]
    (root / "one.txt").write_bytes(b"Invoice amount due 10")
    nested = root / "nested"
    nested.mkdir()
    (nested / "two.txt").write_bytes(b"Invoice amount due 20")

    sources = client.get("/api/import/sources").json()
    assert str(root) in sources["local_roots"]

    response = client.post("/api/import/local", json={"path": str(root), "recursive": True})
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["uploaded"]) == 2
    assert body["errors"] == []
    assert (root / "one.txt").exists() and (nested / "two.txt").exists()
    assert client.get("/api/files").json()[0]["folder_path"] == ["Inbox"]

    outside = client.post("/api/import/local", json={"path": str(tmp_path), "recursive": True})
    assert outside.status_code == 400
    relative = client.post("/api/import/local", json={"path": "relative", "recursive": True})
    assert relative.status_code == 400


def test_local_import_requires_auth_and_root_configuration(client):
    assert client.get("/api/import/sources").status_code == 401
    assert client.post("/api/import/local", json={"path": "C:\\"}).status_code == 401
