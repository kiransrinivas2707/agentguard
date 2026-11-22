from __future__ import annotations

import os
from pathlib import Path


class LocalScanError(ValueError):
    pass


def _is_allowed(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    for root in roots:
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            return True
    return False


def list_local_files(
    target: str,
    roots: tuple[Path, ...],
    recursive: bool = True,
    max_files: int = 200,
    max_bytes: int = 25 * 1024 * 1024,
) -> tuple[list[Path], int]:
    """List files under an explicitly allowed local root.

    Never follows directory symlinks and never deletes or moves source files.
    """
    raw = Path(target).expanduser()
    if not raw.is_absolute():
        raise LocalScanError("Enter an absolute folder path")
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise LocalScanError("Folder does not exist") from exc
    if raw.is_symlink():
        raise LocalScanError("Symbolic links are not allowed")
    if not _is_allowed(resolved, roots):
        raise LocalScanError("Folder is outside the configured scan roots")
    if not resolved.is_dir():
        raise LocalScanError("Path is not a folder")

    files: list[Path] = []
    skipped = 0
    for dirpath, dirnames, filenames in os.walk(resolved, followlinks=False):
        dirnames[:] = [name for name in dirnames if not (Path(dirpath) / name).is_symlink()]
        if not recursive:
            dirnames.clear()
        for name in filenames:
            candidate = Path(dirpath) / name
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    skipped += 1
                    continue
                size = candidate.stat().st_size
            except OSError:
                skipped += 1
                continue
            if size == 0 or size > max_bytes:
                skipped += 1
                continue
            files.append(candidate)
            if len(files) >= max_files:
                return files, skipped
    return files, skipped
