
"""Database session / engine setup."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from ..core.config import settings


class Base(DeclarativeBase):
    pass


_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Importing models here guarantees registration."""
    from ..models import orm  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """create_all 不会给已有表加新列，这里手工补齐（SQLite 支持 ADD COLUMN）。"""
    is_sqlite = settings.DATABASE_URL.startswith("sqlite")
    if not is_sqlite:
        # 其他数据库（Postgres/MySQL）用正式迁移工具（Alembic），这里不冒险
        return
    with engine.begin() as conn:
        try:
            rows = conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
        except Exception:  # noqa: BLE001
            return
        cols = {r[1] for r in rows}  # 列名在 index=1
        if "cancelled" not in cols:
            conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN cancelled BOOLEAN NOT NULL DEFAULT 0"
            ))

