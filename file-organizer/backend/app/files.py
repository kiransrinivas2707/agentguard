from __future__ import annotations

import json
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .classifier import (
    ClassificationContext,
    ClassificationProposal,
    Classifier,
    ClassifierError,
)
from .config import Settings
from .extraction import ExtractionError, extract
from .feedback import apply_learning, feedback_examples
from .models import (
    EXTRACTION_FAILED,
    EXTRACTION_READY,
    EXTRACTION_UNSUPPORTED,
    FILE_CLASSIFIED,
    FILE_FAILED,
    FILE_INBOX,
    FILE_NEEDS_REVIEW,
    FILE_ORGANIZED,
    FILE_UNSUPPORTED,
    Classification,
    File,
    Folder,
    User,
    utcnow,
)
from .schemas import ClassificationOut, FileOut
from .storage import LocalStorageAdapter, StorageError
from .tree import ensure_inbox, existing_paths, folder_path


def latest_classification(db: Session, file_id: str) -> Classification | None:
    return db.scalar(
        select(Classification)
        .where(Classification.file_id == file_id)
        .order_by(Classification.created_at.desc())
        .limit(1)
    )


def reindex_file(db: Session, file: File, classification: Classification | None = None) -> None:
    db.execute(
        text("DELETE FROM file_search WHERE file_id = :file_id"),
        {"file_id": file.id},
    )
    folder = db.get(Folder, file.folder_id)
    path = "/".join(folder_path(db, folder)) if folder else ""
    cls = classification if classification is not None else latest_classification(db, file.id)
    tags = json.loads(cls.tags_json or "[]") if cls else []
    category = cls.category if cls else ""
    document_type = cls.document_type if cls else ""
    db.execute(
        text(
            """
        INSERT INTO file_search(file_id, user_id, name, text, tags, category, path, document_type)
        VALUES (:file_id, :user_id, :name, :text, :tags, :category, :path, :document_type)
        """
        ),
        {
            "file_id": file.id,
            "user_id": file.user_id,
            "name": file.current_name,
            "text": file.extracted_text or "",
            "tags": " ".join(tags),
            "category": category,
            "path": path,
            "document_type": document_type,
        },
    )


def store_upload(
    db: Session,
    storage: LocalStorageAdapter,
    settings: Settings,
    user_id: str,
    filename: str,
    stream: BinaryIO,
) -> File:
    relative, size, digest = storage.save(user_id, filename, stream, settings.max_upload_bytes)
    path = storage.read_path(user_id, relative)
    try:
        extraction = extract(path, filename, settings.max_text_chars)
    except ExtractionError:
        storage.delete(user_id, relative)
        raise

    duplicate = db.scalar(
        select(File)
        .where(File.user_id == user_id, File.sha256 == digest)
        .order_by(File.created_at.asc())
        .limit(1)
    )
    status = FILE_UNSUPPORTED if extraction.status == EXTRACTION_UNSUPPORTED else FILE_INBOX
    inbox = ensure_inbox(db, user_id)
    file = File(
        user_id=user_id,
        folder_id=inbox.id,
        original_name=filename[:255],
        current_name=Path(relative.replace("\\", "/")).name,
        mime_type=extraction.mime_type,
        size=size,
        sha256=digest,
        storage_path=relative,
        status=status,
        extraction_status=extraction.status,
        extracted_text=extraction.text,
        duplicate_of_id=duplicate.id if duplicate else None,
    )
    db.add(file)
    db.flush()
    reindex_file(db, file)
    return file


def classify_file(
    db: Session,
    storage: LocalStorageAdapter,
    classifier: Classifier,
    settings: Settings,
    file: File,
) -> Classification:
    if file.status == FILE_UNSUPPORTED or file.extraction_status == EXTRACTION_UNSUPPORTED:
        raise ValueError("Unsupported file type")

    for old in db.scalars(
        select(Classification).where(
            Classification.file_id == file.id,
            Classification.applied.is_(False),
        )
    ).all():
        old.rejected = True

    image_path = storage.read_path(file.user_id, file.storage_path) if file.extraction_status == EXTRACTION_READY else None
    kind = _kind_for(file)
    user = db.get(User, file.user_id)
    threshold = user.auto_organize_threshold if user else 0.8
    context = ClassificationContext(
        filename=file.current_name,
        mime_type=file.mime_type,
        size=file.size,
        text=file.extracted_text,
        kind=kind,
        image_path=image_path if kind == "image" else None,
        existing_folders=existing_paths(db, file.user_id),
        examples=feedback_examples(db, file.user_id),
    )

    try:
        proposal = classifier.classify(context)
        proposal = apply_learning(db, file.user_id, proposal, threshold)
    except ClassifierError as exc:
        classification = Classification(
            file_id=file.id,
            document_type="other",
            category="Unsorted",
            subcategory=None,
            tags_json="[]",
            suggested_name=file.current_name,
            suggested_path_json="[]",
            date_candidates_json="[]",
            entities_json="[]",
            confidence=0.0,
            rationale="The classifier could not produce a proposal. Review the file manually or retry.",
            requires_review=True,
            provider=classifier.name,
            model=classifier.model,
            error=str(exc),
        )
        db.add(classification)
        file.status = FILE_NEEDS_REVIEW
        file.updated_at = utcnow()
        db.flush()
        reindex_file(db, file, classification)
        return classification

    classification = save_proposal(db, file, proposal, classifier)
    return classification


def save_proposal(
    db: Session,
    file: File,
    proposal: ClassificationProposal,
    classifier: Classifier,
    *,
    status_override: str | None = None,
) -> Classification:
    classification = Classification(
        file_id=file.id,
        document_type=proposal.document_type,
        category=proposal.category,
        subcategory=proposal.subcategory,
        tags_json=json.dumps(proposal.tags),
        suggested_name=proposal.suggested_name,
        suggested_path_json=json.dumps(proposal.suggested_path),
        date_candidates_json=json.dumps(proposal.date_candidates),
        entities_json=json.dumps(proposal.entities),
        confidence=proposal.confidence,
        rationale=proposal.rationale,
        requires_review=proposal.requires_review,
        provider=classifier.name,
        model=classifier.model,
    )
    db.add(classification)
    file.status = status_override or (FILE_NEEDS_REVIEW if proposal.requires_review else FILE_CLASSIFIED)
    file.updated_at = utcnow()
    db.flush()
    reindex_file(db, file, classification)
    return classification


def _kind_for(file: File) -> str:
    mime = file.mime_type
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf":
        return "pdf"
    if mime.endswith("wordprocessingml.document"):
        return "docx"
    if file.extraction_status == EXTRACTION_UNSUPPORTED:
        return "unsupported"
    return "text"


def serialize_file(db: Session, file: File) -> FileOut:
    folder = db.get(Folder, file.folder_id)
    cls = latest_classification(db, file.id)
    return FileOut(
        id=file.id,
        original_name=file.original_name,
        current_name=file.current_name,
        mime_type=file.mime_type,
        size=file.size,
        sha256=file.sha256,
        status=file.status,
        extraction_status=file.extraction_status,
        folder_id=file.folder_id,
        folder_path=folder_path(db, folder) if folder else [],
        duplicate_of_id=file.duplicate_of_id,
        created_at=file.created_at,
        updated_at=file.updated_at,
        classification=ClassificationOut.from_row(cls) if cls else None,
    )
