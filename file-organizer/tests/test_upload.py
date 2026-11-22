from __future__ import annotations

from conftest import register, upload, upload_ok


def test_upload_text_extracts_and_classifies(client):
    register(client)
    file = upload_ok(client, "my resume.txt", b"My resume. Experience: python developer. Curriculum vitae.")
    assert file["original_name"] == "my resume.txt"
    assert file["status"] in {"classified", "needs_review"}
    assert file["extraction_status"] == "ready"
    assert len(file["sha256"]) == 64
    assert file["classification"] is not None
    assert file["classification"]["document_type"] == "resume"
    assert file["classification"]["suggested_path"][:2] == ["Career", "Resumes"]


def test_duplicate_hash_is_flagged_not_deleted(client):
    register(client)
    first = upload_ok(client, "invoice.txt", b"Invoice total amount due 100")
    second = upload_ok(client, "invoice-copy.txt", b"Invoice total amount due 100")
    assert first["duplicate_of_id"] is None
    assert second["duplicate_of_id"] == first["id"]
    listing = client.get("/api/files").json()
    assert len(listing) == 2


def test_unsupported_file_is_stored_and_flagged(client):
    register(client)
    file = upload_ok(client, "program.exe", b"MZ\x90\x00binary", "application/octet-stream")
    assert file["status"] == "unsupported"
    assert file["extraction_status"] == "unsupported"
    assert file["classification"] is None
    review = client.get("/api/review").json()
    assert review == []
    approve = client.post(f"/api/review/{file['id']}/approve", json={"file_id": file["id"]})
    assert approve.status_code == 400


def test_empty_file_is_rejected(client):
    register(client)
    response = upload(client, "empty.txt", b"")
    assert response.status_code == 201
    payload = response.json()
    assert payload["uploaded"] == []
    assert payload["errors"][0]["error"] == "File is empty"


def test_magic_bytes_mismatch_is_rejected(client):
    register(client)
    response = upload(client, "fake.pdf", b"this is not a pdf", "application/pdf")
    payload = response.json()
    assert payload["uploaded"] == []
    assert "does not match" in payload["errors"][0]["error"]
    assert client.get("/api/files").json() == []


def test_size_limit_is_enforced(client):
    register(client)
    big = b"a" * (2 * 1024 * 1024 + 1)
    response = upload(client, "big.txt", big)
    payload = response.json()
    assert payload["uploaded"] == []
    assert "size limit" in payload["errors"][0]["error"]


def test_multi_file_upload_reports_partial_failures(client):
    register(client)
    response = client.post(
        "/api/files",
        files=[
            ("files", ("ok.txt", b"Invoice amount due 10", "text/plain")),
            ("files", ("bad.txt", b"", "text/plain")),
        ],
    )
    payload = response.json()
    assert len(payload["uploaded"]) == 1
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["filename"] == "bad.txt"


def test_upload_without_classification_stays_in_inbox(client):
    register(client)
    response = client.post(
        "/api/files?classify=false",
        files=[("files", ("note.txt", b"some notes", "text/plain"))],
    )
    file = response.json()["uploaded"][0]
    assert file["status"] == "inbox"
    assert file["classification"] is None
    retry = client.post(f"/api/files/{file['id']}/classify")
    assert retry.status_code == 202
    assert client.get(f"/api/files/{file['id']}").json()["status"] in {"classified", "needs_review"}


def test_content_and_text_endpoints(client):
    register(client)
    file = upload_ok(client, "notes.txt", b"hello world")
    content = client.get(f"/api/files/{file['id']}/content")
    assert content.status_code == 200
    assert content.text == "hello world"
    assert content.headers["x-content-type-options"] == "nosniff"
    text = client.get(f"/api/files/{file['id']}/text")
    assert text.json()["text"] == "hello world"


def test_json_content_is_previewable(client):
    register(client)
    file = upload_ok(client, "probe.json", b'{"alpha": 42}', "application/json")
    assert file["mime_type"] == "application/json"
    assert file["extraction_status"] == "ready"
    content = client.get(f"/api/files/{file['id']}/content")
    assert content.status_code == 200, content.text
    assert content.text == '{"alpha": 42}'
    assert content.headers["content-type"].startswith("application/json")


def _blank_pdf() -> bytes:
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_pdf_content_allows_same_origin_preview(client):
    register(client)
    file = upload_ok(client, "preview.pdf", _blank_pdf(), "application/pdf")
    content = client.get(f"/api/files/{file['id']}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "application/pdf"
    assert content.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in content.headers["content-security-policy"]
    assert content.headers["x-content-type-options"] == "nosniff"
