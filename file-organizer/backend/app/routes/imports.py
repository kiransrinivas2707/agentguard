from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..classifier import Classifier
from ..config import Settings
from ..deps import get_classifier, get_current_user, get_db, get_sessionmaker, get_settings, get_storage
from ..extraction import ExtractionError
from ..files import serialize_file, store_upload
from ..jobs import classify_job
from ..models import User
from ..scan import LocalScanError, list_local_files
from ..schemas import (
    FileOut,
    ImportSourcesOut,
    LocalImportRequest,
    LocalImportResponse,
    UploadErrorOut,
)
from ..storage import LocalStorageAdapter, StorageError

router = APIRouter(prefix="/api/import", tags=["import"])


def _google_status(settings: Settings) -> str:
    return "oauth_ready" if settings.google_client_id and settings.google_client_secret else "setup_required"


@router.get("/sources", response_model=ImportSourcesOut)
def sources(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ImportSourcesOut:
    return ImportSourcesOut(
        local_roots=[str(path) for path in settings.scan_roots],
        google_drive=_google_status(settings),
        google_photos=_google_status(settings),
    )


@router.post("/local", response_model=LocalImportResponse, status_code=status.HTTP_201_CREATED)
def import_local(
    payload: LocalImportRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    classifier: Classifier = Depends(get_classifier),
    session_factory=Depends(get_sessionmaker),
) -> LocalImportResponse:
    if not settings.scan_roots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No local scan roots are configured. Set FILE_ORGANIZER_SCAN_ROOTS and restart the backend.",
        )
    try:
        files, skipped = list_local_files(
            payload.path,
            settings.scan_roots,
            recursive=payload.recursive,
            max_bytes=settings.max_upload_bytes,
        )
    except LocalScanError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    uploaded: list[FileOut] = []
    errors: list[UploadErrorOut] = []
    for source in files:
        try:
            with source.open("rb") as stream:
                file = store_upload(db, storage, settings, user.id, source.name, stream)
            db.commit()
            uploaded.append(serialize_file(db, file))
            if payload.classify:
                background.add_task(
                    classify_job,
                    session_factory,
                    storage,
                    classifier,
                    settings,
                    user.id,
                    file.id,
                )
        except (StorageError, ExtractionError, OSError) as exc:
            db.rollback()
            errors.append(UploadErrorOut(filename=source.name, error=str(exc)))
        except Exception:
            db.rollback()
            errors.append(UploadErrorOut(filename=source.name, error="Could not import this file"))

    return LocalImportResponse(
        path=str(payload.path),
        uploaded=uploaded,
        errors=errors,
        skipped=skipped,
    )
