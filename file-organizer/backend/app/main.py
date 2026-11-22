from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import LoginThrottle
from .classifier import Classifier, build_classifier
from .config import BASE_DIR, Settings
from .db import build_engine, build_sessionmaker, init_db
from .routes import auth, automation, files, folders, imports, operations, preferences, review, search, trash
from .schemas import HealthOut
from .storage import LocalStorageAdapter

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_app(settings: Settings | None = None, classifier: Classifier | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = build_engine(settings.database_url)
    init_db(engine)
    session_factory = build_sessionmaker(engine)
    storage = LocalStorageAdapter(settings.data_dir / "users")
    active_classifier = classifier or build_classifier(settings)

    app = FastAPI(
        title="AI File Organizer",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = session_factory
    app.state.storage = storage
    app.state.classifier = active_classifier
    app.state.login_throttle = LoginThrottle()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin:
                same_origin = origin.rstrip("/") == str(request.base_url).rstrip("/")
                if origin not in settings.allowed_origins and not same_origin:
                    return JSONResponse(status_code=403, content={"detail": "Cross-origin request rejected"})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'",
        )
        return response

    app.include_router(auth.router)
    app.include_router(files.router)
    app.include_router(folders.router)
    app.include_router(review.router)
    app.include_router(search.router)
    app.include_router(operations.router)
    app.include_router(preferences.router)
    app.include_router(imports.router)
    app.include_router(automation.router)
    app.include_router(trash.router)

    @app.get("/api/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(classifier=active_classifier.name, model=active_classifier.model)

    dist = Path(BASE_DIR) / "frontend" / "dist"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):  # type: ignore[no-untyped-def]
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (dist / full_path).resolve()
            if dist.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
