from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Import models so metadata is registered."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


COLUMN_MIGRATIONS = [
    ("entries", "difference_note", "TEXT"),
    ("users", "country", "VARCHAR(8) DEFAULT 'BE'"),
    ("teams", "lead_user_id", "INTEGER REFERENCES users(id)"),
    ("team_memberships", "role", "VARCHAR(64) NOT NULL DEFAULT 'Member'"),
    ("entry_versions", "source_pr_id", "INTEGER REFERENCES pull_requests(id)"),
    ("pull_requests", "base_version_number", "INTEGER"),
]


def _ensure_columns(eng=None) -> None:
    """Add columns introduced after the first release (create_all never alters tables)."""
    eng = eng or engine
    insp = inspect(eng)
    for table, column, ddl in COLUMN_MIGRATIONS:
        if not insp.has_table(table):
            continue
        if column in {c["name"] for c in insp.get_columns(table)}:
            continue
        with eng.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
