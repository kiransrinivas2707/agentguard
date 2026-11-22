from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_current_user, get_db, get_settings
from ..models import User
from ..schemas import PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def _google_status(settings: Settings) -> str:
    return "oauth_ready" if settings.google_client_id and settings.google_client_secret else "setup_required"


def _serialize(settings: Settings, user: User) -> PreferencesOut:
    return PreferencesOut(
        auto_organize_enabled=user.auto_organize_enabled,
        auto_organize_threshold=user.auto_organize_threshold,
        scan_roots=[str(path) for path in settings.scan_roots],
        google_drive=_google_status(settings),
        google_photos=_google_status(settings),
    )


@router.get("", response_model=PreferencesOut)
def get_preferences(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> PreferencesOut:
    return _serialize(settings, user)


@router.patch("", response_model=PreferencesOut)
def update_preferences(
    payload: PreferencesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> PreferencesOut:
    if payload.auto_organize_enabled is not None:
        user.auto_organize_enabled = payload.auto_organize_enabled
    if payload.auto_organize_threshold is not None:
        user.auto_organize_threshold = payload.auto_organize_threshold
    db.commit()
    db.refresh(user)
    return _serialize(settings, user)
