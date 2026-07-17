from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# check_same_thread is only needed for SQLite when used across threads.
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Safe to call repeatedly (idempotent)."""
    # Import models so they are registered on the metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Additive migration for existing local SQLite databases.

    ``create_all`` never ALTERs existing tables, so a newly added column would be
    missing on databases created by earlier versions. Add them here so existing
    local data (accounts, uploads) keeps working without a manual migration.
    """
    if engine.dialect.name != "sqlite":
        return

    added_columns = {
        "documents": {"kind": "VARCHAR(16) DEFAULT 'upload'"},
    }
    with engine.begin() as conn:
        for table, columns in added_columns.items():
            existing = {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for name, coldef in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {coldef}"
                    )
