"""Relational storage for user accounts and saved context packages (SQLAlchemy 2.0).

Production uses PostgreSQL (``DATABASE_URL``, e.g. Render Postgres). Locally and in tests
a SQLite file is used when ``DATABASE_URL`` is not set. Tables are created on startup;
there are no migrations yet (the schema is small and additive).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored values as UTC everywhere."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Email/password accounts. NULL for GitHub-only accounts.
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # GitHub accounts are linked by GitHub's numeric user id, never by email.
    github_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    github_login: Mapped[str | None] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    packages: Mapped[list[SavedPackage]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SavedPackage(Base):
    __tablename__ = "saved_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    task: Mapped[str] = mapped_column(Text)
    repository_name: Mapped[str] = mapped_column(String(200))
    item_count: Mapped[int] = mapped_column(Integer)
    rendered_tokens: Mapped[int] = mapped_column(Integer)
    package: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="packages")


def normalize_database_url(url: str) -> str:
    """Use the psycopg 3 driver for PostgreSQL URLs (Render gives ``postgresql://...``)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


class Database:
    def __init__(self, url: str) -> None:
        url = normalize_database_url(url)
        self.dialect = url.split(":", 1)[0].split("+", 1)[0]
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            path = url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self.session = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @property
    def description(self) -> str:
        if self.dialect == "postgresql":
            return "postgresql"
        return "sqlite (local file; not persistent on free hosting)"


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
