from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.db import build_engine, init_db


def test_migration_adds_missing_operation_item_column(tmp_path: Path):
    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, secret="test-secret-0123456789-abcdefghij")
    engine = build_engine(settings.database_url)
    init_db(engine)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE operation_items DROP COLUMN previous_classification_id"
        )
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(operation_items)")}
        assert "previous_classification_id" not in columns

    init_db(engine)
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(operation_items)")}
        assert "previous_classification_id" in columns
        user_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)")}
        assert "auto_organize_enabled" in user_columns
        assert "auto_organize_threshold" in user_columns
        file_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(files)")}
        assert "previous_status" in file_columns


def test_migration_is_idempotent(tmp_path: Path):
    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, secret="test-secret-0123456789-abcdefghij")
    engine = build_engine(settings.database_url)
    init_db(engine)
    init_db(engine)
    init_db(engine)
