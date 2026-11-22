from __future__ import annotations

from datetime import datetime, timezone

from conftest import register, upload_ok


def test_keyword_and_metadata_search(client):
    register(client)
    invoice = upload_ok(client, "march-invoice.txt", b"Invoice total amount due 500 from Acme")
    upload_ok(client, "holiday-photo.txt", b"Notes about a holiday in Goa")

    by_name = client.get("/api/search?q=march").json()
    assert by_name["total"] == 1
    assert by_name["hits"][0]["file"]["id"] == invoice["id"]

    by_text = client.get("/api/search?q=amount").json()
    assert by_text["total"] == 1
    assert "amount" in by_text["hits"][0]["snippet"].lower()

    by_type = client.get("/api/search?q=&document_type=invoice").json()
    assert by_type["total"] == 1

    by_category = client.get("/api/search?q=&category=Finance").json()
    assert by_category["total"] == 1

    by_tag = client.get("/api/search?q=finance").json()
    assert by_tag["total"] == 1


def test_search_empty_and_unknown(client):
    register(client)
    upload_ok(client, "invoice.txt", b"Invoice amount due 1")
    assert client.get("/api/search?q=zzzznotfound").json()["total"] == 0
    assert client.get("/api/search?q=").json()["total"] == 1


def test_search_treats_wildcards_literally(client):
    register(client)
    upload_ok(client, "invoice.txt", b"Invoice amount due 100")
    assert client.get("/api/search?q=%25").json()["total"] == 0
    assert client.get("/api/search?q=_").json()["total"] == 0
    # Surrounded wildcards are tokenized away; the useful word still matches.
    assert client.get("/api/search?q=%25invoice%25").json()["total"] == 1
    assert client.get("/api/search?q=invoice").json()["total"] == 1


def test_search_year_filter(client):
    register(client)
    file = upload_ok(client, "invoice.txt", b"Invoice amount due 1")
    year = datetime.now(timezone.utc).year
    assert client.get(f"/api/search?q=invoice&year={year}").json()["total"] == 1
    assert client.get(f"/api/search?q=invoice&year={year - 5}").json()["total"] == 0
    assert file["id"]


def test_search_does_not_leak_between_users(client):
    register(client, "alice@example.com")
    upload_ok(client, "invoice.txt", b"Invoice amount due 1")
    client.post("/api/auth/logout")
    register(client, "bob@example.com")
    assert client.get("/api/search?q=invoice").json()["total"] == 0
    assert client.get("/api/search?q=amount").json()["total"] == 0
