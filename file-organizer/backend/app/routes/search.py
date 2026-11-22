from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import User
from ..schemas import SearchResponse
from ..search import search_files

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(default="", max_length=300),
    document_type: str | None = Query(default=None, max_length=40),
    category: str | None = Query(default=None, max_length=120),
    year: int | None = Query(default=None, ge=1900, le=2100),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchResponse:
    return search_files(
        db,
        user.id,
        q,
        document_type=document_type,
        category=category,
        year=year,
        limit=limit,
    )
