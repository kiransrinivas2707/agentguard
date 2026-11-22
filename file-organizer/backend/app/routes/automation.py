from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auto import run_eligible
from ..deps import get_current_user, get_db, get_storage
from ..models import User
from ..schemas import AutomationRunOut
from ..storage import LocalStorageAdapter

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.post("/run", response_model=AutomationRunOut)
def run_now(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    storage: LocalStorageAdapter = Depends(get_storage),
) -> AutomationRunOut:
    organized, skipped, failed = run_eligible(db, storage, user)
    return AutomationRunOut(organized=organized, skipped=skipped, failed=failed)
