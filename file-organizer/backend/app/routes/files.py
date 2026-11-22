from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File as UploadFileParam, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..classifier import Classifier
from ..config import Settings
from ..deps import (
    get_classifier,
    get_current_user,
    get_db,
    get_sessionmaker,
    get_settings,
    get_storage,
)
from ..extraction import ExtractionError, PREVIEWABLE, stream_text
from ..files import classify_file, serialize_file, store_upload
from ..jobs import classify_job
from ..models import FILE_STATUSES, FILE_TRASHED, FILE_UNSUPPORTED, File, User
from ..schemas import FileOut, MessageOut, StatsOut, UploadErrorOut, UploadResponse
from ..storage import LocalStorageAdapter, StorageError
from ..trash import TrashError, trash_file

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_files(
    background: BackgroundTasks,
    files: list[UploadFile] = UploadFileParam(...),
    classify: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    classifier: Classifier = Depends(get_classifier),
    session_factory=Depends(get_sessionmaker),
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files were provided")
    if len(files) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload at most 50 files at a time")

    uploaded: list[FileOut] = []
    errors: list[UploadErrorOut] = []
    for upload in files:
        filename = upload.filename or "upload"
        try:
            if upload.size is not None and upload.size > settings.max_upload_bytes:
                raise StorageError("File exceeds the upload size limit")
            file = store_upload(db, storage, settings, user.id, filename, upload.file)
            db.commit()
            uploaded.append(serialize_file(db, file))
            if classify and file.status != FILE_UNSUPPORTED:
                background.add_task(
                    classify_job,
                    session_factory,
                    storage,
                    classifier,
                    settings,
                    user.id,
                    file.id,
                )
        except (StorageError, ExtractionError) as exc:
            db.rollback()
            errors.append(UploadErrorOut(filename=filename, error=str(exc)))
        except Exception:
            db.rollback()
            errors.append(UploadErrorOut(filename=filename, error="Could not store this file"))
        finally:
            upload.file.close()

    return UploadResponse(uploaded=uploaded, errors=errors)


@router.get("", response_model=list[FileOut])
def list_files(
    folder_id: str | None = Query(default=None),
    file_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FileOut]:
    if file_status and file_status not in FILE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown file status")
    stmt = select(File).where(File.user_id == user.id)
    if folder_id:
        stmt = stmt.where(File.folder_id == folder_id)
    if file_status:
        stmt = stmt.where(File.status == file_status)
    else:
        stmt = stmt.where(File.status != FILE_TRASHED)
    stmt = stmt.order_by(File.updated_at.desc()).offset(offset).limit(limit)
    return [serialize_file(db, file) for file in db.scalars(stmt).all()]


@router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    file = db.get(File, file_id)
    if not file or file.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return serialize_file(db, file)


@router.delete("/{file_id}", response_model=FileOut)
def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> FileOut:
    try:
        file = trash_file(db, storage, user.id, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrashError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return serialize_file(db, file)


@router.get("/{file_id}/content")
def get_content(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
):
    file = db.get(File, file_id)
    if not file or file.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if file.mime_type not in PREVIEWABLE:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Preview is not available")
    try:
        path = storage.read_path(user.id, file.storage_path)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File content is missing") from exc

    if file.mime_type.startswith("text/") or file.mime_type == "application/json":
        text = stream_text(path)
        return PlainTextResponse(
            text,
            media_type=file.mime_type,
            headers={"Content-Disposition": f'inline; filename="{file.current_name}"'},
        )
    return FileResponse(
        path,
        media_type=file.mime_type,
        filename=file.current_name,
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "frame-ancestors 'self'",
        },
    )


@router.get("/{file_id}/text")
def get_text(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    file = db.get(File, file_id)
    if not file or file.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return {"text": file.extracted_text[:50_000]}


@router.post("/{file_id}/classify", response_model=MessageOut, status_code=status.HTTP_202_ACCEPTED)
def reclassify(
    file_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
    settings: Settings = Depends(get_settings),
    classifier: Classifier = Depends(get_classifier),
    session_factory=Depends(get_sessionmaker),
) -> MessageOut:
    file = db.get(File, file_id)
    if not file or file.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if file.status == "organized":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organized files cannot be reclassified")
    if file.status == FILE_UNSUPPORTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    background.add_task(
        classify_job,
        session_factory,
        storage,
        classifier,
        settings,
        user.id,
        file.id,
    )
    return MessageOut(message="Classification queued")


@router.get("/stats/summary", response_model=StatsOut)
def stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StatsOut:
    rows = dict(
        db.execute(
            select(File.status, func.count(File.id)).where(File.user_id == user.id).group_by(File.status)
        ).all()
    )
    trashed = int(rows.get(FILE_TRASHED, 0))
    return StatsOut(
        inbox=int(rows.get("inbox", 0)),
        needs_review=int(rows.get("needs_review", 0)),
        organized=int(rows.get("organized", 0)),
        unsupported=int(rows.get("unsupported", 0)),
        trashed=trashed,
        total=int(sum(value for status, value in rows.items() if status != FILE_TRASHED)),
    )
