from __future__ import annotations

import hashlib
import os
import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from .paths import safe_join, sanitize_filename, unique_filename


class StorageError(Exception):
    pass


class StorageAdapter(ABC):
    @abstractmethod
    def user_root(self, user_id: str) -> Path: ...

    @abstractmethod
    def save(self, user_id: str, original_name: str, stream: BinaryIO, max_bytes: int) -> tuple[str, int, str]: ...

    @abstractmethod
    def move(self, user_id: str, from_relative: str, to_relative: str) -> None: ...

    @abstractmethod
    def read_path(self, user_id: str, relative: str) -> Path: ...

    @abstractmethod
    def exists(self, user_id: str, relative: str) -> bool: ...

    @abstractmethod
    def delete(self, user_id: str, relative: str) -> None: ...


class LocalStorageAdapter(StorageAdapter):
    """Local, per-user storage rooted at data/users/<user_id>.

    Physical paths mirror the logical folder tree. Every path is resolved and
    checked against the user root before use.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def user_root(self, user_id: str) -> Path:
        if not user_id or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", user_id):
            raise StorageError("Invalid user id")
        root = (self.root / user_id).resolve()
        if root.parent != self.root:
            raise StorageError("Invalid user root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def save(self, user_id: str, original_name: str, stream: BinaryIO, max_bytes: int) -> tuple[str, int, str]:
        root = self.user_root(user_id)
        inbox = root / "Inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_filename(original_name)
        name = unique_filename(inbox, safe_name)
        destination = safe_join(root, f"Inbox/{name}")
        temp = destination.with_name(destination.name + ".part")
        digest = hashlib.sha256()
        total = 0
        try:
            with temp.open("wb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise StorageError("File exceeds the upload size limit")
                    digest.update(chunk)
                    handle.write(chunk)
            if total == 0:
                raise StorageError("File is empty")
            os.replace(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        return f"Inbox/{name}", total, digest.hexdigest()

    def move(self, user_id: str, from_relative: str, to_relative: str) -> None:
        root = self.user_root(user_id)
        source = safe_join(root, from_relative)
        destination = safe_join(root, to_relative)
        if not source.exists():
            raise StorageError("Source file is missing")
        if destination.exists():
            raise StorageError("Destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

    def read_path(self, user_id: str, relative: str) -> Path:
        path = safe_join(self.user_root(user_id), relative)
        if not path.is_file():
            raise StorageError("File is missing")
        return path

    def exists(self, user_id: str, relative: str) -> bool:
        try:
            return safe_join(self.user_root(user_id), relative).is_file()
        except ValueError:
            return False

    def delete(self, user_id: str, relative: str) -> None:
        path = safe_join(self.user_root(user_id), relative)
        path.unlink(missing_ok=True)
