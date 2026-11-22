from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import (
    LoginThrottle,
    clear_session_cookie,
    create_token,
    hash_password,
    set_session_cookie,
    verify_password,
)
from ..config import Settings
from ..deps import get_current_user, get_db, get_settings
from ..models import User
from ..schemas import LoginRequest, MessageOut, RegisterRequest, UserOut
from ..tree import ensure_inbox

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _throttle(request: Request) -> LoginThrottle:
    return request.app.state.login_throttle


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    email = str(payload.email).strip().lower()
    existing = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        auto_organize_enabled=settings.auto_organize_default,
    )
    db.add(user)
    db.flush()
    ensure_inbox(db, user.id)
    db.commit()
    set_session_cookie(response, create_token(user.id, settings), settings)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    email = str(payload.email).strip().lower()
    throttle = _throttle(request)
    if throttle.is_blocked(email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts. Try again later.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not verify_password(payload.password, user.password_hash):
        throttle.record_failure(email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    throttle.reset(email)
    set_session_cookie(response, create_token(user.id, settings), settings)
    return UserOut.model_validate(user)


@router.post("/logout", response_model=MessageOut)
def logout(response: Response) -> MessageOut:
    clear_session_cookie(response)
    return MessageOut(message="Logged out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
