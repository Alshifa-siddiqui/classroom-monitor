from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# columns added after the first release; applied additively to existing DBs
_COLUMN_MIGRATIONS = {
    "students": {
        "student_code": "VARCHAR(20)",
        "email": "VARCHAR(120)",
        "user_id": "INTEGER",
        "created_at": "TIMESTAMP",
    },
}


def _existing_columns(conn, table: str) -> set:
    from sqlalchemy import text
    if engine.dialect.name == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})"))
        return {r[1] for r in rows}
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = :t"), {"t": table})
    return {r[0] for r in rows}


def _migrate_columns() -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        for table, cols in _COLUMN_MIGRATIONS.items():
            existing = _existing_columns(conn, table)
            for col, col_type in cols.items():
                if col not in existing:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
        conn.commit()


def _backfill_student_codes() -> None:
    from datetime import datetime, timezone

    from .models import Student
    db = SessionLocal()
    try:
        year = datetime.now(timezone.utc).year
        for student in db.query(Student).filter(Student.student_code.is_(None)).all():
            student.student_code = f"STU-{year}-{student.id:03d}"
        db.commit()
    finally:
        db.close()


def init_db(retries: int = 3, delay: float = 2.0) -> None:
    """Create tables and apply additive migrations, retrying so a briefly
    unavailable database (e.g. a PostgreSQL container still starting) does
    not kill the app."""
    import logging
    import time

    from . import models  # noqa: F401  (register tables)

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            _migrate_columns()
            _backfill_student_codes()
            return
        except Exception as exc:  # OperationalError and friends
            last_exc = exc
            logging.getLogger(__name__).warning(
                "Database init failed (attempt %d/%d): %s", attempt, retries, exc)
            time.sleep(delay)
    raise last_exc
