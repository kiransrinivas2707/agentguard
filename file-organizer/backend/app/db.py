from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


def build_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS file_search USING fts5(
    file_id UNINDEXED,
    user_id UNINDEXED,
    name,
    text,
    tags,
    category,
    path,
    document_type,
    tokenize='unicode61 remove_diacritics 2'
)
"""


def _migrate_sqlite(engine: Engine) -> None:
    """Add columns introduced after the first local database was created."""

    def columns(connection, table: str) -> set[str]:  # type: ignore[no-untyped-def]
        return {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}

    with engine.begin() as connection:
        user_columns = columns(connection, "users")
        if "auto_organize_enabled" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN auto_organize_enabled BOOLEAN DEFAULT 1")
        if "auto_organize_threshold" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN auto_organize_threshold FLOAT DEFAULT 0.8")

        operation_columns = columns(connection, "operation_items")
        if "previous_classification_id" not in operation_columns:
            connection.exec_driver_sql(
                "ALTER TABLE operation_items ADD COLUMN previous_classification_id VARCHAR(36)"
            )

        file_columns = columns(connection, "files")
        if "previous_status" not in file_columns:
            connection.exec_driver_sql("ALTER TABLE files ADD COLUMN previous_status VARCHAR(24)")


def init_db(engine: Engine) -> None:
    from . import models  # noqa: F401  (register mappings)

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(FTS_SQL)
    if engine.url.get_backend_name() == "sqlite":
        _migrate_sqlite(engine)
