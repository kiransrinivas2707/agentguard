from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .files import reindex_file
from .models import (
    FILE_TRASHED,
    File,
    Folder,
    utcnow,
)
from .paths import safe_join, unique_filename
from .storage import LocalStorageAdapter, StorageError
from .tree import ensure_inbox, folder_relative_path


class TrashError(ValueError):
    pass


def _remove_from_index(db: Session, file_id: str) -> None:
    db.execute(text("DELETE FROM file_search WHERE file_id = :file_id"), {"file_id": file_id})


def _remove_empty_trash_dir(storage: LocalStorageAdapter, user_id: str, file_id: str) -> None:
    try:
        safe_join(storage.user_root(user_id), f"Trash/{file_id}").rmdir()
    except OSError:
        pass


def trash_file(db: Session, storage: LocalStorageAdapter, user_id: str, file_id: str) -> File:
    file = db.get(File, file_id)
    if not file or file.user_id != user_id:
        raise LookupError("File not found")
    if file.status == FILE_TRASHED:
        raise TrashError("File is already in Trash")
    try:
        source = storage.read_path(user_id, file.storage_path)
    except StorageError as exc:
        raise TrashError("File content is missing") from exc
    destination = f"Trash/{file.id}/{file.current_name}"
    storage.move(user_id, file.storage_path, destination)
    file.previous_status = file.status
    file.status = FILE_TRASHED
    file.storage_path = destination
    file.updated_at = utcnow()
    _remove_from_index(db, file.id)
    db.commit()
    return file


def restore_file(db: Session, storage: LocalStorageAdapter, user_id: str, file_id: str) -> File:
    file = db.get(File, file_id)
    if not file or file.user_id != user_id:
        raise LookupError("File not found")
    if file.status != FILE_TRASHED:
        raise TrashError("File is not in Trash")
    folder = db.get(Folder, file.folder_id)
    if not folder or folder.user_id != user_id:
        folder = ensure_inbox(db, user_id)
    relative_dir = folder_relative_path(db, folder)
    root = storage.user_root(user_id)
    destination_dir = safe_join(root, relative_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    taken = {
        name
        for (name,) in db.execute(
            select(File.current_name).where(
                File.user_id == user_id,
                File.folder_id == folder.id,
                File.id != file.id,
                File.status != FILE_TRASHED,
            )
        ).all()
    }
    name = unique_filename(destination_dir, file.current_name, taken=taken)
    destination = f"{relative_dir}/{name}"
    storage.move(user_id, file.storage_path, destination)
    _remove_empty_trash_dir(storage, user_id, file.id)
    file.folder_id = folder.id
    file.current_name = name
    file.storage_path = destination
    previous = file.previous_status
    file.status = previous if previous and previous != FILE_TRASHED else ("organized" if relative_dir != "Inbox" else "inbox")
    file.previous_status = None
    file.updated_at = utcnow()
    reindex_file(db, file)
    db.commit()
    return file


def list_trash(db: Session, user_id: str, limit: int = 200) -> list[File]:
    return list(
        db.scalars(
            select(File)
            .where(File.user_id == user_id, File.status == FILE_TRASHED)
            .order_by(File.updated_at.desc())
            .limit(limit)
        ).all()
    )


def purge_file(db: Session, storage: LocalStorageAdapter, user_id: str, file_id: str) -> None:
    file = db.get(File, file_id)
    if not file or file.user_id != user_id:
        raise LookupError("File not found")
    if file.status != FILE_TRASHED:
        raise TrashError("Move the file to Trash before deleting it permanently")
    try:
        storage.delete(user_id, file.storage_path)
    except StorageError:
        pass
    _remove_empty_trash_dir(storage, user_id, file.id)
    _remove_from_index(db, file.id)
    db.delete(file)
    db.commit()
