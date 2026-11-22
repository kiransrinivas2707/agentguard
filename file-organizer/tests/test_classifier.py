from __future__ import annotations

import json

import pytest

from app.classifier import (
    ClassificationContext,
    ClassificationProposal,
    ClassifierError,
    MockClassifier,
    OpenCodeClassifier,
    parse_proposal,
)
from app.config import Settings


def test_parse_proposal_accepts_fenced_json():
    output = """Here you go:
```json
{"documentType": "invoice", "category": "Finance", "subcategory": "Invoices",
 "tags": ["invoice", "invoice"], "suggestedName": "Invoice.pdf",
 "suggestedPath": ["Finance", "Invoices"], "dateCandidates": [], "entities": [],
 "confidence": 0.9, "rationale": "Invoice keywords", "requiresReview": false}
```
"""
    proposal = parse_proposal(output)
    assert proposal.document_type == "invoice"
    assert proposal.tags == ["invoice"]
    assert proposal.suggested_path == ["Finance", "Invoices"]


def test_parse_proposal_rejects_non_json():
    with pytest.raises(ClassifierError):
        parse_proposal("I cannot classify this.")
    with pytest.raises(ClassifierError):
        parse_proposal('{"documentType": "invoice"')


@pytest.mark.parametrize(
    "payload",
    [
        {"suggestedName": "../../evil.txt"},
        {"suggestedName": "folder/evil.txt"},
        {"suggestedPath": ["..", "etc"]},
        {"suggestedPath": ["a/b"]},
        {"suggestedPath": ["a", "b", "c", "d", "e"]},
        {"confidence": 1.5},
        {"category": ".."},
    ],
)
def test_invalid_proposals_are_rejected(payload):
    base = {
        "documentType": "other",
        "category": "Unsorted",
        "suggestedName": "file.txt",
        "suggestedPath": [],
        "confidence": 0.5,
    }
    with pytest.raises(ValueError):
        ClassificationProposal.model_validate({**base, **payload})


def test_unknown_document_type_normalizes_to_other():
    proposal = ClassificationProposal(document_type="spreadsheet", suggested_name="x.txt")
    assert proposal.document_type == "other"


def test_low_confidence_forces_review():
    proposal = ClassificationProposal(
        document_type="invoice", category="Finance", suggested_name="x.pdf", confidence=0.2
    ).normalized()
    assert proposal.requires_review is True
    high = ClassificationProposal(
        document_type="invoice", category="Finance", suggested_name="x.pdf", confidence=0.9
    ).normalized()
    assert high.requires_review is False


def test_unknown_type_always_requires_review():
    proposal = ClassificationProposal(
        document_type="other", category="Unsorted", suggested_name="x.bin", confidence=0.99
    ).normalized()
    assert proposal.requires_review is True


def test_mock_classifier_rules():
    classifier = MockClassifier()
    context = ClassificationContext(
        filename="aws certificate.txt",
        mime_type="text/plain",
        size=10,
        text="AWS Certified Cloud Practitioner",
    )
    proposal = classifier.classify(context)
    assert proposal.document_type == "certificate"
    assert proposal.suggested_path == ["Career", "Certifications"]
    assert proposal.requires_review is False


def test_mock_education_and_photo_taxonomy():
    classifier = MockClassifier()
    study = classifier.classify(
        ClassificationContext(
            filename="semester-notes.txt",
            mime_type="text/plain",
            size=10,
            text="Lecture notes, syllabus, exam revision",
        )
    )
    assert study.suggested_path[:2] == ["Education", "Study Materials"]

    trip = classifier.classify(
        ClassificationContext(filename="goa-trip.jpg", mime_type="image/jpeg", size=10, kind="image")
    )
    assert trip.suggested_path[:2] == ["Photos & Memories", "Trips"]

    generic = classifier.classify(
        ClassificationContext(filename="random.jpg", mime_type="image/jpeg", size=10, kind="image")
    )
    assert generic.suggested_path[:2] == ["Photos & Memories", "Memories"]

    signature = classifier.classify(
        ClassificationContext(
            filename="signature.jpg", mime_type="image/jpeg", size=10, kind="image", text="handwritten signature"
        )
    )
    assert signature.suggested_path == ["Personal", "Signatures"]


def test_mock_identity_document_subfolders():
    classifier = MockClassifier()
    cases = {
        "PAN-Card.pdf": "PAN",
        "aadhaar-card.pdf": "Aadhaar",
        "passport-scan.pdf": "Passport",
        "student-id.pdf": "Student ID",
    }
    for filename, subfolder in cases.items():
        proposal = classifier.classify(
            ClassificationContext(filename=filename, mime_type="application/pdf", size=10, text=filename)
        )
        assert proposal.document_type == "identity_document"
        assert proposal.suggested_path == ["Identity Documents", subfolder]


def test_opencode_classifier_uses_validated_output(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path, secret="secret", classifier="opencode")
    classifier = OpenCodeClassifier(settings)
    captured = {}

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "documentType": "invoice",
                "category": "Finance",
                "subcategory": "Invoices",
                "tags": ["invoice"],
                "suggestedName": "Invoice.txt",
                "suggestedPath": ["Finance", "Invoices"],
                "confidence": 0.88,
                "rationale": "Invoice content",
            }
        )
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("app.classifier.subprocess.run", fake_run)
    proposal = classifier.classify(
        ClassificationContext(filename="invoice.txt", mime_type="text/plain", size=5, text="invoice")
    )
    assert proposal.suggested_path == ["Finance", "Invoices"]
    assert "--agent" in captured["command"]
    assert "file-classifier" in captured["command"]
    assert captured["kwargs"]["timeout"] == settings.classify_timeout


def test_opencode_failure_is_generic(monkeypatch, tmp_path):
    settings = Settings(data_dir=tmp_path, secret="secret", classifier="opencode")
    classifier = OpenCodeClassifier(settings)

    class Failed:
        returncode = 1
        stdout = ""
        stderr = "secret token and file contents"

    monkeypatch.setattr("app.classifier.subprocess.run", lambda *args, **kwargs: Failed())
    with pytest.raises(ClassifierError) as excinfo:
        classifier.classify(ClassificationContext(filename="x.txt", mime_type="text/plain", size=1, text="x"))
    assert "secret token" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("Free usage limit reached.", "free classifier quota is exhausted"),
        ("Insufficient balance.", "no credits"),
        ("Error: 429 Too Many Requests", "rate-limited"),
        ("Missing API key.", "not authenticated"),
        ("Model unavailable: opencode/x", "model is unavailable"),
        ("something unexpected", "classifier process failed"),
    ],
)
def test_classifier_failure_messages_are_actionable(monkeypatch, tmp_path, stderr, expected):
    settings = Settings(data_dir=tmp_path, secret="secret", classifier="opencode")
    classifier = OpenCodeClassifier(settings)

    class Failed:
        returncode = 1
        stdout = ""

    Failed.stderr = stderr

    monkeypatch.setattr("app.classifier.subprocess.run", lambda *args, **kwargs: Failed())
    with pytest.raises(ClassifierError) as excinfo:
        classifier.classify(ClassificationContext(filename="x.txt", mime_type="text/plain", size=1, text="x"))
    message = str(excinfo.value)
    assert expected in message
    assert stderr not in message
