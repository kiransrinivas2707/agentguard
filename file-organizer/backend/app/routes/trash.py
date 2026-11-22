from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_storage
from ..files import serialize_file
from ..models import User
from ..schemas import FileOut, MessageOut
from ..storage import LocalStorageAdapter
from ..trash import TrashError, list_trash, purge_file, restore_file

router = APIRouter(prefix="/api/trash", tags=["trash"])


@router.get("", response_model=list[FileOut])
def get_trash(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FileOut]:
    return [serialize_file(db, file) for file in list_trash(db, user.id)]


@router.post("/{file_id}/restore", response_model=FileOut)
def restore(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> FileOut:
    try:
        file = restore_file(db, storage, user.id, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrashError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return serialize_file(db, file)


@router.delete("/{file_id}", response_model=MessageOut)
def purge(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> MessageOut:
    try:
        purge_file(db, storage, user.id, file_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TrashError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageOut(message="File permanently deleted")
