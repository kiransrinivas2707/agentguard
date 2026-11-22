from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    parent_id: str | None
    is_system: bool
    path: list[str] = Field(default_factory=list)
    file_count: int = 0


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


class ClassificationOut(BaseModel):
    id: str
    document_type: str
    category: str
    subcategory: str | None
    tags: list[str]
    suggested_name: str
    suggested_path: list[str]
    date_candidates: list[str]
    entities: list[str]
    confidence: float
    rationale: str
    requires_review: bool
    provider: str
    model: str
    error: str | None = None
    applied: bool
    rejected: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row) -> "ClassificationOut":  # type: ignore[no-untyped-def]
        return cls(
            id=row.id,
            document_type=row.document_type,
            category=row.category,
            subcategory=row.subcategory,
            tags=json.loads(row.tags_json or "[]"),
            suggested_name=row.suggested_name,
            suggested_path=json.loads(row.suggested_path_json or "[]"),
            date_candidates=json.loads(row.date_candidates_json or "[]"),
            entities=json.loads(row.entities_json or "[]"),
            confidence=row.confidence,
            rationale=row.rationale,
            requires_review=row.requires_review,
            provider=row.provider,
            model=row.model,
            error=row.error,
            applied=row.applied,
            rejected=row.rejected,
            created_at=row.created_at,
        )


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    current_name: str
    mime_type: str
    size: int
    sha256: str
    status: str
    extraction_status: str
    folder_id: str
    folder_path: list[str] = Field(default_factory=list)
    duplicate_of_id: str | None = None
    created_at: datetime
    updated_at: datetime
    classification: ClassificationOut | None = None


class ApproveItem(BaseModel):
    file_id: str
    name: str | None = Field(default=None, max_length=255)
    path: list[str] | None = None
    tags: list[str] | None = None
    document_type: str | None = None
    category: str | None = None
    subcategory: str | None = None

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return clean_tag_list(value)


class ApproveBatchRequest(BaseModel):
    items: list[ApproveItem] = Field(min_length=1, max_length=100)


class ApproveResult(BaseModel):
    file_id: str
    ok: bool
    operation_id: str | None = None
    error: str | None = None


class ApproveResponse(BaseModel):
    file: FileOut
    operation_id: str


class BatchApproveResponse(BaseModel):
    results: list[ApproveResult]


class OperationItemOut(BaseModel):
    id: str
    file_id: str
    from_path: str
    to_path: str
    from_name: str
    to_name: str
    status: str


class OperationOut(BaseModel):
    id: str
    kind: str
    status: str
    created_at: datetime
    undone_at: datetime | None
    items: list[OperationItemOut] = Field(default_factory=list)


class SearchHit(BaseModel):
    file: FileOut
    snippet: str = ""


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]


class StatsOut(BaseModel):
    inbox: int
    needs_review: int
    organized: int
    unsupported: int
    trashed: int = 0
    total: int


class MessageOut(BaseModel):
    message: str


class TagUpdate(BaseModel):
    tags: list[str] = Field(max_length=20)


class ClassificationOverride(BaseModel):
    document_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    tags: list[str] | None = None


class ErrorOut(BaseModel):
    detail: str


class HealthOut(BaseModel):
    status: str = "ok"
    classifier: str
    model: str


class UploadErrorOut(BaseModel):
    filename: str
    error: str


class UploadResponse(BaseModel):
    uploaded: list[FileOut] = Field(default_factory=list)
    errors: list[UploadErrorOut] = Field(default_factory=list)


class UndoResponse(BaseModel):
    operation: OperationOut
    errors: list[str] = Field(default_factory=list)


class PreferencesOut(BaseModel):
    auto_organize_enabled: bool
    auto_organize_threshold: float
    scan_roots: list[str] = Field(default_factory=list)
    google_drive: str = "not_configured"
    google_photos: str = "not_configured"


class PreferencesUpdate(BaseModel):
    auto_organize_enabled: bool | None = None
    auto_organize_threshold: float | None = Field(default=None, ge=0.5, le=1.0)


class ImportSourcesOut(BaseModel):
    local_roots: list[str] = Field(default_factory=list)
    google_drive: str = "not_configured"
    google_photos: str = "not_configured"


class LocalImportRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    recursive: bool = True
    classify: bool = True


class LocalImportResponse(BaseModel):
    path: str
    uploaded: list[FileOut] = Field(default_factory=list)
    errors: list[UploadErrorOut] = Field(default_factory=list)
    skipped: int = 0


class AutomationRunOut(BaseModel):
    organized: int
    skipped: int
    failed: int


class FolderCleanupOut(BaseModel):
    removed: int


def clean_tag_list(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        value = " ".join(str(tag).split()).strip()[:40]
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result[:12]



