from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .models import EXTRACTION_FAILED, EXTRACTION_READY, EXTRACTION_UNSUPPORTED

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".yaml", ".yml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS

MIME_BY_EXT = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".log": "text/plain",
    ".json": "application/json",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
}

PREVIEWABLE = {"application/pdf", "application/json", "text/plain", "text/markdown", "text/csv", "text/yaml"} | {
    MIME_BY_EXT[ext] for ext in IMAGE_EXTENSIONS
}


class ExtractionError(ValueError):
    pass


@dataclass
class Extraction:
    kind: str
    mime_type: str
    status: str
    text: str = ""
    meta: dict = field(default_factory=dict)


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def declared_mime(filename: str) -> str:
    return MIME_BY_EXT.get(extension_of(filename), "application/octet-stream")


def _head(path: Path, count: int = 16) -> bytes:
    with path.open("rb") as handle:
        return handle.read(count)


def _decode_text(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise ExtractionError("Binary content is not valid text")
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("Text encoding is not supported")


def _read_text(path: Path, max_chars: int) -> str:
    data = path.read_bytes()
    return _decode_text(data)[:max_chars]


def _read_pdf(path: Path, max_chars: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # pragma: no cover - provider specific
            raise ExtractionError("PDF is encrypted") from exc
    chunks: list[str] = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        if not text:
            continue
        chunks.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return "\n".join(chunks)[:max_chars]


def _read_docx(path: Path, max_chars: int) -> str:
    import docx

    document = docx.Document(str(path))
    chunks = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                chunks.append(" | ".join(cells))
    return "\n".join(chunks)[:max_chars]


def _read_image(path: Path) -> dict:
    from PIL import Image

    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        return {"width": image.width, "height": image.height, "format": image.format}


def extract(path: Path, original_name: str, max_chars: int = 20_000) -> Extraction:
    """Extract searchable text/metadata and verify the bytes match the extension."""
    ext = extension_of(original_name)
    mime = declared_mime(original_name)
    head = _head(path, 32)

    try:
        if ext in TEXT_EXTENSIONS:
            if b"\x00" in head:
                raise ExtractionError("File content does not match its extension")
            return Extraction("text", mime, EXTRACTION_READY, _read_text(path, max_chars))

        if ext == ".pdf":
            if not head.startswith(b"%PDF-"):
                raise ExtractionError("File content does not match its extension")
            return Extraction("pdf", mime, EXTRACTION_READY, _read_pdf(path, max_chars))

        if ext == ".docx":
            if not head.startswith(b"PK\x03\x04"):
                raise ExtractionError("File content does not match its extension")
            try:
                with zipfile.ZipFile(path) as archive:
                    if "word/document.xml" not in archive.namelist():
                        raise ExtractionError("File content does not match its extension")
            except zipfile.BadZipFile as exc:
                raise ExtractionError("Invalid DOCX archive") from exc
            return Extraction("docx", mime, EXTRACTION_READY, _read_docx(path, max_chars))

        if ext in IMAGE_EXTENSIONS:
            expected = {
                ".png": (b"\x89PNG\r\n\x1a\n",),
                ".jpg": (b"\xff\xd8\xff",),
                ".jpeg": (b"\xff\xd8\xff",),
                ".gif": (b"GIF87a", b"GIF89a"),
                ".webp": (b"RIFF",),
                ".bmp": (b"BM",),
                ".tiff": (b"II*\x00", b"MM\x00*"),
            }[ext]
            if not any(head.startswith(signature) for signature in expected):
                raise ExtractionError("File content does not match its extension")
            if ext == ".webp" and head[8:12] != b"WEBP":
                raise ExtractionError("File content does not match its extension")
            return Extraction("image", mime, EXTRACTION_READY, "", _read_image(path))

        return Extraction("unsupported", "application/octet-stream", EXTRACTION_UNSUPPORTED)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("Could not read this file") from exc


def looks_like_text(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
        if b"\x00" in sample:
            return False
        sample.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def stream_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_bytes()[:limit].decode("utf-8", errors="replace")
    except OSError:
        return ""
