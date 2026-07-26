from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Any

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from packages.shared.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def psycopg_connect(
    *, autocommit: bool = False
) -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(
        get_settings().psycopg_url,
        autocommit=autocommit,
        row_factory=dict_row,
    )


def check_database() -> dict[str, str]:
    with get_engine().connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    current_database() AS database,
                    current_setting('server_version') AS version,
                    EXISTS (
                        SELECT 1 FROM pg_extension WHERE extname = 'vector'
                    ) AS vector_enabled
                """
            )
        ).mappings().one()
    return {
        "database": str(row["database"]),
        "version": str(row["version"]),
        "vector_enabled": str(bool(row["vector_enabled"])).lower(),
    }
