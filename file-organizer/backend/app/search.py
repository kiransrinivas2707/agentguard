from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .files import latest_classification, serialize_file
from .models import FILE_TRASHED, File
from .schemas import SearchHit, SearchResponse

_STOPWORDS = {
    "a",
    "an",
    "and",
    "any",
    "are",
    "at",
    "be",
    "by",
    "for",
    "from",
    "find",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "show",
    "that",
    "the",
    "to",
    "where",
    "with",
}


def build_fts_query(query: str) -> str | None:
    tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    cleaned = [token for token in tokens if len(token) > 1 and token.casefold() not in _STOPWORDS][:8]
    if not cleaned:
        return None
    return " AND ".join(f'"{token}"*' for token in cleaned)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_files(
    db: Session,
    user_id: str,
    query: str = "",
    *,
    document_type: str | None = None,
    category: str | None = None,
    year: int | None = None,
    limit: int = 50,
) -> SearchResponse:
    query = (query or "").strip()
    effective_year = year
    if effective_year is None and "last year" in query.casefold():
        effective_year = datetime.now(timezone.utc).year - 1

    ids: list[str] = []
    snippets: dict[str, str] = {}
    fts_query = build_fts_query(query) if query else None
    if fts_query:
        try:
            rows = db.execute(
                text(
                    """
                    SELECT file_id, snippet(file_search, 3, '[', ']', '…', 16) AS snip
                    FROM file_search
                    WHERE file_search MATCH :match AND user_id = :user_id
                    ORDER BY rank
                    LIMIT 200
                    """
                ),
                {"match": fts_query, "user_id": user_id},
            ).all()
            ids = [row[0] for row in rows]
            snippets = {row[0]: row[1] for row in rows}
        except OperationalError:
            ids = []

    if query and not ids:
        like = f"%{_escape_like(query.casefold())}%"
        fallback = db.scalars(
            select(File)
            .where(
                File.user_id == user_id,
                File.status != FILE_TRASHED,
                func.lower(File.current_name).like(like, escape="\\")
                | func.lower(File.extracted_text).like(like, escape="\\"),
            )
            .order_by(File.created_at.desc())
            .limit(200)
        ).all()
        ids = [file.id for file in fallback]
        snippets = {file.id: "" for file in fallback}

    stmt = select(File).where(File.user_id == user_id, File.status != FILE_TRASHED)
    if ids:
        stmt = stmt.where(File.id.in_(ids))
    elif query:
        return SearchResponse(query=query, total=0, hits=[])
    else:
        stmt = stmt.order_by(File.created_at.desc()).limit(200)

    files = db.scalars(stmt).all()
    order = {file_id: index for index, file_id in enumerate(ids)}
    if ids:
        files = sorted(files, key=lambda file: order.get(file.id, 10_000))

    hits: list[SearchHit] = []
    for file in files:
        classification = latest_classification(db, file.id)
        if document_type and (not classification or classification.document_type != document_type):
            continue
        if category and (not classification or classification.category.casefold() != category.casefold()):
            continue
        if effective_year is not None:
            candidates = json.loads(classification.date_candidates_json) if classification else []
            in_year = any(str(year) in candidate for candidate in candidates)
            if not in_year and file.created_at.year != effective_year:
                continue
        hits.append(SearchHit(file=serialize_file(db, file), snippet=snippets.get(file.id, "")))
        if len(hits) >= limit:
            break

    return SearchResponse(query=query, total=len(hits), hits=hits)
