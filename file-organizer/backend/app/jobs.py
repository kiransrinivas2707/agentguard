from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from .auto import maybe_auto_organize
from .classifier import Classifier
from .config import Settings
from .files import classify_file, latest_classification
from .models import File
from .storage import LocalStorageAdapter


def classify_job(
    session_factory: sessionmaker,
    storage: LocalStorageAdapter,
    classifier: Classifier,
    settings: Settings,
    user_id: str,
    file_id: str,
) -> None:
    """Run classification outside the request transaction.

    Failures are contained: the file remains in the Inbox and the user can retry.
    No file content or filenames are written to logs.
    """
    db = session_factory()
    try:
        file = db.get(File, file_id)
        if not file or file.user_id != user_id:
            return
        classify_file(db, storage, classifier, settings, file)
        db.commit()
        classification = latest_classification(db, file.id)
        if classification:
            maybe_auto_organize(db, storage, settings, file, classification)
    except Exception:
        db.rollback()
    finally:
        db.close()
