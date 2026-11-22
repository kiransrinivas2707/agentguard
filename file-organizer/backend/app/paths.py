from __future__ import annotations

import re
import unicodedata
from pathlib import Path

MAX_DEPTH = 4
MAX_SEGMENT = 60
MAX_FILENAME = 120

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_EXT = re.compile(r"^\.[A-Za-z0-9]{1,10}$")
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class PathValidationError(ValueError):
    """Raised when a user/model supplied name or path is unsafe."""


def sanitize_segment(raw: str, *, max_length: int = MAX_SEGMENT) -> str:
    if not isinstance(raw, str):
        raise PathValidationError("Path segment must be text")
    value = unicodedata.normalize("NFKC", raw)
    value = _INVALID.sub("_", value)
    value = " ".join(value.split())
    value = value.strip(" .")
    if value in {"", ".", ".."}:
        raise PathValidationError("Path segment is empty or unsafe")
    if value.split(".")[0].upper() in _RESERVED:
        value = f"_{value}"
    if value.startswith("."):
        value = value.lstrip(".") or "_"
    value = value[:max_length].rstrip(" .")
    if not value:
        raise PathValidationError("Path segment is empty or unsafe")
    return value


def sanitize_filename(raw: str, *, fallback: str = "file", strict: bool = False) -> str:
    if not isinstance(raw, str):
        raise PathValidationError("Filename must be text")
    if strict:
        stripped = raw.strip()
        if stripped in {"", ".", ".."} or any(token in raw for token in ("/", "\\", "\x00")):
            raise PathValidationError("Filename must be a single safe filename")
        if re.match(r"^[A-Za-z]:", stripped):
            raise PathValidationError("Absolute paths are not allowed")
    # Only the final component is ever used; directory components are discarded.
    base = Path(raw.replace("\\", "/")).name.strip()
    if base in {"", ".", ".."}:
        base = fallback
    stem, ext = _split_extension(base)
    safe_stem = sanitize_segment(stem or fallback, max_length=MAX_FILENAME - len(ext))
    safe_ext = ext if _EXT.match(ext) else ""
    result = f"{safe_stem}{safe_ext}"
    return result[:MAX_FILENAME].rstrip(" .") or fallback


def _split_extension(name: str) -> tuple[str, str]:
    if "." not in name:
        return name, ""
    stem, ext = name.rsplit(".", 1)
    ext = f".{ext}"
    if not stem or not _EXT.match(ext):
        return name, ""
    return stem, ext


def sanitize_path(segments: list[str] | tuple[str, ...], *, strict: bool = False) -> list[str]:
    if segments is None:
        return []
    if not isinstance(segments, (list, tuple)):
        raise PathValidationError("Folder path must be a list")
    cleaned: list[str] = []
    for raw in segments:
        if not isinstance(raw, str):
            raise PathValidationError("Folder path entries must be text")
        if strict:
            stripped = raw.strip()
            if stripped in {"", ".", ".."} or any(token in raw for token in ("/", "\\", "\x00")):
                raise PathValidationError("Folder path entries must be single folder names")
            if re.match(r"^[A-Za-z]:", stripped):
                raise PathValidationError("Absolute paths are not allowed")
        value = sanitize_segment(raw)
        # Collapse accidental duplicates such as Career/Career.
        if cleaned and cleaned[-1].casefold() == value.casefold():
            continue
        cleaned.append(value)
    if len(cleaned) > MAX_DEPTH:
        raise PathValidationError(f"Folder path exceeds {MAX_DEPTH} levels")
    return cleaned


def safe_join(root: Path, relative: str | Path) -> Path:
    root = Path(root).resolve()
    rel = Path(str(relative).replace("\\", "/"))
    if rel.is_absolute():
        raise PathValidationError("Absolute paths are not allowed")
    if any(part in {"..", ""} for part in rel.parts):
        raise PathValidationError("Path traversal is not allowed")
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise PathValidationError("Path escapes the storage root")
    return candidate


def relative_path(segments: list[str], filename: str) -> str:
    return "/".join([*segments, filename])


def unique_filename(directory: Path, filename: str, *, taken: set[str] | None = None) -> str:
    taken = {name.casefold() for name in (taken or set())}
    stem, ext = _split_extension(filename)
    candidate = filename
    counter = 2
    while candidate.casefold() in taken or (directory / candidate).exists():
        candidate = f"{stem} ({counter}){ext}"
        counter += 1
        if counter > 999:
            raise PathValidationError("Could not find a free filename")
    return candidate
