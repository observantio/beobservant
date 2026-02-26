"""
Database initialization and session management using SQLAlchemy, providing functions to create the database engine, manage sessions, and perform connectivity checks. This module includes logic to handle database connection pooling, to provide context-managed sessions for use in route handlers and services, and to ensure proper cleanup of database resources on application shutdown. It also includes a function to initialize the database schema based on defined SQLAlchemy models.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator, Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from db_models import Base

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_database(
    database_url: str,
    echo: bool = False,
    pool_size: Optional[int] = None,
) -> None:
    global _engine, _SessionLocal

    if _engine is not None:
        logger.debug("Database already initialized; skipping re-init.")
        return

    resolved_pool_size = pool_size or int(os.environ.get("DB_POOL_SIZE") or "10")
    resolved_max_overflow = int(os.environ.get("DB_MAX_OVERFLOW") or "20")
    resolved_pool_timeout = int(os.environ.get("DB_POOL_TIMEOUT") or "30")
    resolved_pool_recycle = int(os.environ.get("DB_POOL_RECYCLE") or "1800")

    _engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=resolved_pool_size,
        max_overflow=resolved_max_overflow,
        pool_timeout=resolved_pool_timeout,
        pool_recycle=resolved_pool_recycle,
        echo=echo,
    )

    _SessionLocal = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def _require_session_factory() -> sessionmaker:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _SessionLocal


@contextmanager
def get_db_session() -> Iterator[Session]:
    session: Session = _require_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    session: Session = _require_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def connection_test() -> bool:
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.debug("DB connection test failed: %s", exc)
        return False


def dispose_database() -> None:
    global _engine, _SessionLocal
    _SessionLocal = None
    if _engine is not None:
        try:
            _engine.dispose()
        finally:
            _engine = None


def init_db() -> None:
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=_engine)
    logger.info("Database tables created successfully.")
