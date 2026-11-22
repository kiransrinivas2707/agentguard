from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_storage
from ..feedback import record_feedback
from ..files import latest_classification, serialize_file
from ..models import FILE_CLASSIFIED, FILE_NEEDS_REVIEW, File, User
from ..organizer import OrganizeError, approve_file, reject_file
from ..schemas import (
    ApproveBatchRequest,
    ApproveItem,
    ApproveResponse,
    ApproveResult,
    BatchApproveResponse,
    FileOut,
)
from ..storage import LocalStorageAdapter

router = APIRouter(prefix="/api/review", tags=["review"])


@router.get("", response_model=list[FileOut])
def review_queue(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FileOut]:
    limit = max(1, min(limit, 200))
    files = db.scalars(
        select(File)
        .where(
            File.user_id == user.id,
            File.status.in_([FILE_CLASSIFIED, FILE_NEEDS_REVIEW]),
        )
        .order_by(File.updated_at.desc())
        .limit(limit)
    ).all()
    return [serialize_file(db, file) for file in files]


@router.post("/{file_id}/approve", response_model=ApproveResponse)
def approve(
    file_id: str,
    payload: ApproveItem | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> ApproveResponse:
    item = payload or ApproveItem(file_id=file_id)
    item.file_id = file_id
    try:
        operation, file = approve_file(db, storage, user.id, item)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    record_feedback(db, file, latest_classification(db, file.id), "approved")
    db.commit()
    return ApproveResponse(file=serialize_file(db, file), operation_id=operation.id)


@router.post("/{file_id}/reject", response_model=FileOut)
def reject(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    try:
        classification = latest_classification(db, file_id)
        file = reject_file(db, user.id, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    record_feedback(db, file, classification, "rejected")
    db.commit()
    return serialize_file(db, file)


@router.post("/approve-batch", response_model=BatchApproveResponse)
def approve_batch(
    payload: ApproveBatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> BatchApproveResponse:
    results: list[ApproveResult] = []
    for item in payload.items:
        try:
            operation, file = approve_file(db, storage, user.id, item)
            record_feedback(db, file, latest_classification(db, file.id), "approved")
            db.commit()
            results.append(ApproveResult(file_id=item.file_id, ok=True, operation_id=operation.id))
        except LookupError:
            db.rollback()
            results.append(ApproveResult(file_id=item.file_id, ok=False, error="File not found"))
        except Exception as exc:
            db.rollback()
            message = str(exc) if isinstance(exc, OrganizeError) else "Could not organize this file"
            results.append(ApproveResult(file_id=item.file_id, ok=False, error=message))
    return BatchApproveResponse(results=results)
