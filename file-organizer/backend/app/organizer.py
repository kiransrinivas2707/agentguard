from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .files import latest_classification, reindex_file
from .models import (
    EXTRACTION_UNSUPPORTED,
    FILE_INBOX,
    FILE_ORGANIZED,
    FILE_TRASHED,
    Classification,
    File,
    Folder,
    Operation,
    OperationItem,
    utcnow,
)
from .paths import PathValidationError, safe_join, sanitize_filename, sanitize_path, unique_filename
from .schemas import ApproveItem
from .storage import LocalStorageAdapter, StorageError
from .tree import (
    delete_folder_if_empty,
    ensure_inbox,
    folder_relative_path,
    resolve_or_create_path,
)


class OrganizeError(ValueError):
    pass


def _effective_classification(
    db: Session, file: File, item: ApproveItem
) -> Classification | None:
    base = latest_classification(db, file.id)
    has_override = any(
        value is not None
        for value in (item.document_type, item.category, item.subcategory, item.tags)
    )
    if base is not None and not base.applied and not has_override:
        return base

    classification = Classification(
        file_id=file.id,
        document_type=item.document_type or (base.document_type if base else "other"),
        category=item.category or (base.category if base else "Unsorted"),
        subcategory=item.subcategory if item.subcategory is not None else (base.subcategory if base else None),
        tags_json=json.dumps(item.tags if item.tags is not None else json.loads(base.tags_json if base else "[]")),
        suggested_name=item.name or (base.suggested_name if base else file.current_name),
        suggested_path_json=json.dumps(
            item.path if item.path is not None else json.loads(base.suggested_path_json if base else "[]")
        ),
        date_candidates_json=base.date_candidates_json if base else "[]",
        entities_json=base.entities_json if base else "[]",
        confidence=base.confidence if base else 1.0,
        rationale=base.rationale if base else "Manually organized by the user.",
        requires_review=False,
        provider="manual" if has_override else "reorganize",
        model="",
    )
    if base and not base.applied:
        base.rejected = True
    db.add(classification)
    db.flush()
    return classification


def approve_file(
    db: Session,
    storage: LocalStorageAdapter,
    user_id: str,
    item: ApproveItem,
    *,
    kind: str = "organize",
) -> tuple[Operation, File]:
    file = db.get(File, item.file_id)
    if not file or file.user_id != user_id:
        raise LookupError("File not found")
    if file.extraction_status == EXTRACTION_UNSUPPORTED:
        raise OrganizeError("Unsupported files cannot be organized")

    previous = latest_classification(db, file.id)
    previous_id = previous.id if previous and previous.applied else None
    classification = _effective_classification(db, file, item)
    name_source = item.name or (classification.suggested_name if classification else file.current_name)
    path_source = (
        item.path
        if item.path is not None
        else (json.loads(classification.suggested_path_json) if classification else [])
    )

    try:
        final_name = sanitize_filename(name_source, strict=True)
        segments = sanitize_path(path_source, strict=True)
    except PathValidationError as exc:
        raise OrganizeError(str(exc)) from exc

    created_ids: list[str] = []
    try:
        destination = (
            resolve_or_create_path(db, user_id, segments, created_ids)
            if segments
            else ensure_inbox(db, user_id)
        )
        destination_rel = folder_relative_path(db, destination)
        root = storage.user_root(user_id)
        destination_dir = safe_join(root, destination_rel)
        destination_dir.mkdir(parents=True, exist_ok=True)

        taken = set(
            db.scalars(
                select(File.current_name).where(
                    File.user_id == user_id,
                    File.folder_id == destination.id,
                    File.id != file.id,
                    File.status != FILE_TRASHED,
                )
            ).all()
        )
        final_name = unique_filename(destination_dir, final_name, taken=taken)
        to_rel = f"{destination_rel}/{final_name}"

        from_folder_id = file.folder_id
        from_name = file.current_name
        from_path = file.storage_path
        from_status = file.status

        operation = Operation(
            user_id=user_id,
            kind=kind,
            status="applied",
            created_folder_ids_json=json.dumps(created_ids),
        )
        db.add(operation)
        db.flush()

        moved = False
        if to_rel != file.storage_path:
            storage.move(user_id, file.storage_path, to_rel)
            moved = True

        try:
            file.folder_id = destination.id
            file.current_name = final_name
            file.storage_path = to_rel
            file.status = FILE_ORGANIZED
            file.updated_at = utcnow()

            if classification:
                classification.applied = True
                classification.rejected = False
                classification.suggested_name = final_name
                classification.suggested_path_json = json.dumps(segments)

            db.add(
                OperationItem(
                    operation_id=operation.id,
                    file_id=file.id,
                    from_folder_id=from_folder_id,
                    to_folder_id=destination.id,
                    from_name=from_name,
                    to_name=final_name,
                    from_path=from_path,
                    to_path=to_rel,
                    from_status=from_status,
                    classification_id=classification.id if classification else None,
                    previous_classification_id=previous_id,
                )
            )
            reindex_file(db, file, classification)
            db.commit()
        except Exception:
            if moved:
                try:
                    storage.move(user_id, to_rel, from_path)
                except StorageError:
                    pass
            raise
    except Exception:
        db.rollback()
        for folder_id in reversed(created_ids):
            try:
                delete_folder_if_empty(db, user_id, folder_id)
            except Exception:
                pass
        db.commit()
        raise

    return operation, file


def reject_file(db: Session, user_id: str, file_id: str) -> File:
    file = db.get(File, file_id)
    if not file or file.user_id != user_id:
        raise LookupError("File not found")
    classification = latest_classification(db, file.id)
    if classification and not classification.applied:
        classification.rejected = True
    if file.status in {"classified", "needs_review"}:
        file.status = FILE_INBOX
    file.updated_at = utcnow()
    reindex_file(db, file, classification)
    db.commit()
    return file


def undo_operation(
    db: Session,
    storage: LocalStorageAdapter,
    user_id: str,
    operation_id: str,
) -> tuple[Operation, list[str]]:
    operation = db.get(Operation, operation_id)
    if not operation or operation.user_id != user_id:
        raise LookupError("Operation not found")
    if operation.status != "applied":
        raise OrganizeError("This operation has already been undone")

    items = db.scalars(
        select(OperationItem)
        .where(OperationItem.operation_id == operation.id)
        .order_by(OperationItem.id.asc())
    ).all()
    errors: list[str] = []

    for entry in reversed(items):
        file = db.get(File, entry.file_id)
        if not file or file.user_id != user_id:
            errors.append("A file from this action no longer exists")
            entry.status = "failed"
            continue
        if file.storage_path != entry.to_path or file.folder_id != entry.to_folder_id:
            errors.append(f"{file.current_name} changed after this action")
            entry.status = "failed"
            continue

        try:
            from_dir_rel = str(Path(entry.from_path.replace("\\", "/")).parent).replace("\\", "/")
            if from_dir_rel in {".", ""}:
                from_dir_rel = ""
            root = storage.user_root(user_id)
            from_dir = safe_join(root, from_dir_rel) if from_dir_rel else root
            from_dir.mkdir(parents=True, exist_ok=True)
            taken = set(
                db.scalars(
                    select(File.current_name).where(
                        File.user_id == user_id,
                        File.folder_id == entry.from_folder_id,
                        File.id != file.id,
                        File.status != FILE_TRASHED,
                    )
                ).all()
            )
            restore_name = unique_filename(from_dir, entry.from_name, taken=taken)
            from_rel = f"{from_dir_rel}/{restore_name}" if from_dir_rel else restore_name

            if file.storage_path != from_rel:
                storage.move(user_id, file.storage_path, from_rel)

            folder = db.get(Folder, entry.from_folder_id)
            if not folder or folder.user_id != user_id:
                folder = ensure_inbox(db, user_id)
            file.folder_id = folder.id
            file.current_name = restore_name
            file.storage_path = from_rel
            file.status = entry.from_status or FILE_INBOX
            file.updated_at = utcnow()

            if entry.classification_id:
                classification = db.get(Classification, entry.classification_id)
                if classification and classification.file_id == file.id:
                    classification.applied = False
            if entry.previous_classification_id:
                previous = db.get(Classification, entry.previous_classification_id)
                if previous and previous.file_id == file.id:
                    previous.applied = True
                    previous.rejected = False

            entry.status = "undone"
            reindex_file(db, file, latest_classification(db, file.id))
        except (StorageError, PathValidationError, OSError):
            errors.append(f"Could not restore {file.current_name}")
            entry.status = "failed"

    created_ids = json.loads(operation.created_folder_ids_json or "[]")
    db.flush()
    for folder_id in reversed(created_ids):
        try:
            folder = db.get(Folder, folder_id)
            if not folder:
                continue
            relative = folder_relative_path(db, folder)
            if delete_folder_if_empty(db, user_id, folder_id):
                try:
                    safe_join(storage.user_root(user_id), relative).rmdir()
                except OSError:
                    pass
        except Exception:
            pass

    operation.status = "undone" if not errors else "partial_undo"
    operation.undone_at = utcnow()
    db.commit()
    return operation, errors
