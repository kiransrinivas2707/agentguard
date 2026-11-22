from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_storage
from ..models import Folder, User
from ..paths import MAX_DEPTH, PathValidationError, safe_join, sanitize_segment
from ..schemas import FolderCleanupOut, FolderCreate, FolderOut
from ..storage import LocalStorageAdapter
from ..tree import (
    delete_folder_if_empty,
    find_child,
    folder_path,
    folder_relative_path,
    list_folders,
)

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
def get_folders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FolderOut]:
    return [
        FolderOut(
            id=folder.id,
            name=folder.name,
            parent_id=folder.parent_id,
            is_system=folder.is_system,
            path=path,
            file_count=count,
        )
        for folder, path, count in list_folders(db, user.id)
    ]


@router.post("/cleanup-empty", response_model=FolderCleanupOut)
def cleanup_empty_folders(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> FolderCleanupOut:
    folders = db.scalars(
        select(Folder).where(Folder.user_id == user.id, Folder.is_system.is_(False))
    ).all()
    folders.sort(key=lambda folder: len(folder_path(db, folder)), reverse=True)
    removed = 0
    for folder in folders:
        relative = folder_relative_path(db, folder)
        if delete_folder_if_empty(db, user.id, folder.id):
            try:
                safe_join(storage.user_root(user.id), relative).rmdir()
            except OSError:
                pass
            removed += 1
    db.commit()
    return FolderCleanupOut(removed=removed)


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: FolderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FolderOut:
    try:
        if any(token in payload.name for token in ("/", "\\", ":", "\x00")) or payload.name.strip() in {".", ".."}:
            raise PathValidationError("Folder name must be a single safe name")
        name = sanitize_segment(payload.name)
    except PathValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    parent: Folder | None = None
    if payload.parent_id:
        parent = db.get(Folder, payload.parent_id)
        if not parent or parent.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent folder not found")
    depth = len(folder_path(db, parent)) + 1 if parent else 1
    if depth > MAX_DEPTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Folders can be at most {MAX_DEPTH} levels deep")
    if find_child(db, user.id, parent.id if parent else None, name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder with this name already exists here")

    folder = Folder(user_id=user.id, parent_id=parent.id if parent else None, name=name, is_system=False)
    db.add(folder)
    db.commit()
    return FolderOut(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        is_system=folder.is_system,
        path=folder_path(db, folder),
        file_count=0,
    )
