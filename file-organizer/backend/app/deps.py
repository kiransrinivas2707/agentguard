from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .auth import COOKIE_NAME, decode_token
from .classifier import Classifier
from .config import Settings
from .models import User
from .storage import LocalStorageAdapter


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> LocalStorageAdapter:
    return request.app.state.storage


def get_classifier(request: Request) -> Classifier:
    return request.app.state.classifier


def get_sessionmaker(request: Request):
    return request.app.state.sessionmaker


def get_db(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


def _token_from_request(request: Request) -> str | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = decode_token(token, settings)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user
