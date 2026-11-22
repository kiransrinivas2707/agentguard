from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_storage
from ..models import Operation, OperationItem, User
from ..organizer import OrganizeError, undo_operation
from ..schemas import OperationItemOut, OperationOut, UndoResponse
from ..storage import LocalStorageAdapter

router = APIRouter(prefix="/api/operations", tags=["operations"])


def _serialize(db: Session, operation: Operation) -> OperationOut:
    items = db.scalars(
        select(OperationItem)
        .where(OperationItem.operation_id == operation.id)
        .order_by(OperationItem.id.asc())
    ).all()
    return OperationOut(
        id=operation.id,
        kind=operation.kind,
        status=operation.status,
        created_at=operation.created_at,
        undone_at=operation.undone_at,
        items=[
            OperationItemOut(
                id=item.id,
                file_id=item.file_id,
                from_path=item.from_path,
                to_path=item.to_path,
                from_name=item.from_name,
                to_name=item.to_name,
                status=item.status,
            )
            for item in items
        ],
    )


@router.get("", response_model=list[OperationOut])
def list_operations(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[OperationOut]:
    operations = db.scalars(
        select(Operation)
        .where(Operation.user_id == user.id)
        .order_by(Operation.created_at.desc())
        .limit(limit)
    ).all()
    return [_serialize(db, operation) for operation in operations]


@router.get("/{operation_id}", response_model=OperationOut)
def get_operation(
    operation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OperationOut:
    operation = db.get(Operation, operation_id)
    if not operation or operation.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found")
    return _serialize(db, operation)


@router.post("/{operation_id}/undo", response_model=UndoResponse)
def undo(
    operation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> UndoResponse:
    try:
        operation, errors = undo_operation(db, storage, user.id, operation_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UndoResponse(operation=_serialize(db, operation), errors=errors)
