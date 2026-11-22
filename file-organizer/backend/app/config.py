from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _persisted_secret(data_dir: Path) -> str:
    env_secret = os.getenv("FILE_ORGANIZER_SECRET")
    if env_secret:
        return env_secret
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = data_dir / ".secret"
    if secret_file.exists():
        value = secret_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    secret_file.write_text(value, encoding="utf-8")
    try:
        secret_file.chmod(0o600)
    except OSError:
        pass
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("FILE_ORGANIZER_DATA", BASE_DIR / "data")))
    database_url: str = ""
    secret: str = ""
    max_upload_bytes: int = 25 * 1024 * 1024
    max_text_chars: int = 20_000
    classifier: str = "opencode"
    model: str = "opencode/deepseek-v4.1-flash-free"
    opencode_bin: str = "opencode"
    opencode_agent: str = "file-classifier"
    classify_timeout: float = 120.0
    cookie_secure: bool = False
    allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    token_ttl_hours: int = 24
    auto_organize_default: bool = True
    scan_roots: tuple[Path, ...] = ()
    google_client_id: str = ""
    google_client_secret: str = ""

    def __post_init__(self) -> None:
        data_dir = Path(self.data_dir).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "data_dir", data_dir)
        object.__setattr__(self, "scan_roots", tuple(Path(root).expanduser().resolve() for root in self.scan_roots))
        if not self.database_url:
            object.__setattr__(self, "database_url", f"sqlite+pysqlite:///{data_dir / 'app.db'}")
        if not self.secret:
            object.__setattr__(self, "secret", _persisted_secret(data_dir))

    @classmethod
    def from_env(cls) -> "Settings":
        origins = os.getenv("FILE_ORGANIZER_ORIGINS")
        allowed = tuple(o.strip() for o in origins.split(",") if o.strip()) if origins else cls.allowed_origins
        raw_roots = os.getenv("FILE_ORGANIZER_SCAN_ROOTS", "")
        roots = tuple(Path(part.strip()) for part in raw_roots.replace("\n", ";").split(";") if part.strip())
        return cls(
            data_dir=Path(os.getenv("FILE_ORGANIZER_DATA", BASE_DIR / "data")),
            database_url=os.getenv("FILE_ORGANIZER_DATABASE_URL", ""),
            max_upload_bytes=int(os.getenv("FILE_ORGANIZER_MAX_UPLOAD", str(25 * 1024 * 1024))),
            max_text_chars=int(os.getenv("FILE_ORGANIZER_MAX_TEXT", "20000")),
            classifier=os.getenv("FILE_ORGANIZER_CLASSIFIER", "opencode"),
            model=os.getenv("FILE_ORGANIZER_MODEL", "opencode/deepseek-v4.1-flash-free"),
            opencode_bin=os.getenv("FILE_ORGANIZER_OPENCODE_BIN", "opencode"),
            opencode_agent=os.getenv("FILE_ORGANIZER_OPENCODE_AGENT", "file-classifier"),
            classify_timeout=float(os.getenv("FILE_ORGANIZER_CLASSIFY_TIMEOUT", "120")),
            cookie_secure=_env_bool("FILE_ORGANIZER_COOKIE_SECURE", False),
            allowed_origins=allowed,
            auto_organize_default=_env_bool("FILE_ORGANIZER_AUTO_ORGANIZE_DEFAULT", True),
            scan_roots=roots,
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        )
