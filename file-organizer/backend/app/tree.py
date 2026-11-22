from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import FILE_TRASHED, File, Folder
from .paths import MAX_DEPTH, PathValidationError, sanitize_segment


def ensure_inbox(db: Session, user_id: str) -> Folder:
    folder = db.scalar(
        select(Folder).where(Folder.user_id == user_id, Folder.parent_id.is_(None), Folder.name == "Inbox")
    )
    if folder:
        return folder
    folder = Folder(user_id=user_id, name="Inbox", parent_id=None, is_system=True)
    db.add(folder)
    db.flush()
    return folder


def folder_path(db: Session, folder: Folder) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    current: Folder | None = folder
    while current is not None:
        if current.id in seen:
            raise PathValidationError("Folder cycle detected")
        seen.add(current.id)
        names.append(current.name)
        current = db.get(Folder, current.parent_id) if current.parent_id else None
    names.reverse()
    return names


def folder_relative_path(db: Session, folder: Folder) -> str:
    return "/".join(folder_path(db, folder))


def find_child(db: Session, user_id: str, parent_id: str | None, name: str) -> Folder | None:
    stmt = select(Folder).where(
        Folder.user_id == user_id,
        func.lower(Folder.name) == name.casefold(),
    )
    stmt = stmt.where(Folder.parent_id == parent_id) if parent_id else stmt.where(Folder.parent_id.is_(None))
    return db.scalar(stmt)


def resolve_or_create_path(
    db: Session, user_id: str, segments: list[str], created_ids: list[str] | None = None
) -> Folder:
    if len(segments) > MAX_DEPTH:
        raise PathValidationError(f"Folder path exceeds {MAX_DEPTH} levels")
    parent: Folder | None = None
    for raw in segments:
        name = sanitize_segment(raw)
        existing = find_child(db, user_id, parent.id if parent else None, name)
        if existing:
            parent = existing
            continue
        if parent is None and name.casefold() == "inbox":
            parent = ensure_inbox(db, user_id)
            continue
        folder = Folder(user_id=user_id, name=name, parent_id=parent.id if parent else None, is_system=False)
        db.add(folder)
        db.flush()
        if created_ids is not None:
            created_ids.append(folder.id)
        parent = folder
    if parent is None:
        parent = ensure_inbox(db, user_id)
    return parent


def existing_paths(db: Session, user_id: str, limit: int = 200) -> list[str]:
    folders = db.scalars(
        select(Folder).where(Folder.user_id == user_id).order_by(Folder.created_at.asc()).limit(limit)
    ).all()
    paths = []
    for folder in folders:
        path = folder_path(db, folder)
        if path == ["Inbox"]:
            continue
        paths.append("/".join(path))
    return paths


def list_folders(db: Session, user_id: str) -> list[tuple[Folder, list[str], int]]:
    folders = db.scalars(select(Folder).where(Folder.user_id == user_id).order_by(Folder.name.asc())).all()
    counts = dict(
        db.execute(
            select(File.folder_id, func.count(File.id))
            .where(File.user_id == user_id, File.status != FILE_TRASHED)
            .group_by(File.folder_id)
        ).all()
    )
    return [(folder, folder_path(db, folder), int(counts.get(folder.id, 0))) for folder in folders]


def delete_folder_if_empty(db: Session, user_id: str, folder_id: str) -> bool:
    folder = db.get(Folder, folder_id)
    if not folder or folder.user_id != user_id or folder.is_system:
        return False
    has_child = db.scalar(select(func.count(Folder.id)).where(Folder.parent_id == folder.id))
    has_files = db.scalar(
        select(func.count(File.id)).where(File.folder_id == folder.id, File.status != FILE_TRASHED)
    )
    if has_child or has_files:
        return False
    db.delete(folder)
    db.flush()
    return True
