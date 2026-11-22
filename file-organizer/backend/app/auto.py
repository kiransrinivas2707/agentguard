from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .files import latest_classification
from .models import (
    FILE_CLASSIFIED,
    FILE_NEEDS_REVIEW,
    Classification,
    File,
    User,
)
from .organizer import approve_file
from .schemas import ApproveItem
from .storage import LocalStorageAdapter


def is_auto_eligible(user: User | None, file: File, classification: Classification | None) -> bool:
    if not user.auto_organize_enabled or classification is None:
        return False
    if classification.error and not classification.error.startswith("Automatic organization failed"):
        return False
    if classification.document_type == "other":
        return False
    if classification.category.casefold() == "unsorted":
        return False
    if classification.confidence < user.auto_organize_threshold:
        return False
    if not json.loads(classification.suggested_path_json or "[]"):
        return False
    return file.status in {FILE_CLASSIFIED, FILE_NEEDS_REVIEW}


def maybe_auto_organize(
    db: Session,
    storage: LocalStorageAdapter,
    settings: Settings,
    file: File,
    classification: Classification,
) -> str | None:
    """Move a high-confidence, known-type file without user approval.

    Confidence is authoritative per the user's setting; requires_review does not
    block a move when confidence still meets the threshold.
    """
    user = db.get(User, file.user_id)
    if not is_auto_eligible(user, file, classification):
        return None
    try:
        operation, _ = approve_file(db, storage, user.id, ApproveItem(file_id=file.id), kind="auto")
        return operation.id
    except Exception:
        db.rollback()
        current = db.get(File, file.id)
        if current:
            current.status = FILE_NEEDS_REVIEW
            current_classification = latest_classification(db, current.id)
            if current_classification:
                current_classification.requires_review = True
                current_classification.error = (
                    "Automatic organization failed. Review the proposal and place the file manually."
                )
            db.commit()
        return None


def run_eligible(
    db: Session,
    storage: LocalStorageAdapter,
    user: User,
) -> tuple[int, int, int]:
    """Organize all currently eligible files for a user. Returns organized/skipped/failed."""
    organized = skipped = failed = 0
    files = db.scalars(
        select(File)
        .where(
            File.user_id == user.id,
            File.status.in_([FILE_CLASSIFIED, FILE_NEEDS_REVIEW]),
        )
        .order_by(File.created_at.asc())
    ).all()
    for file in files:
        classification = latest_classification(db, file.id)
        if not is_auto_eligible(user, file, classification):
            skipped += 1
            continue
        try:
            approve_file(db, storage, user.id, ApproveItem(file_id=file.id), kind="auto")
            organized += 1
        except Exception:
            db.rollback()
            failed += 1
    return organized, skipped, failed
