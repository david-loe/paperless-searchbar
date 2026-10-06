import time

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    rules: Mapped[dict] = mapped_column(JSON)


class SearchConfiguration(Base):
    __tablename__ = "search_configuration"
    id: Mapped[int] = mapped_column(primary_key=True)
    custom_field_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(120), unique=True)
    local_code_digest: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    issuer: Mapped[str | None] = mapped_column(String)
    subject: Mapped[str | None] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))


class GuestCode(Base):
    __tablename__ = "guest_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="RESTRICT"))
    expires_at: Mapped[int] = mapped_column(Integer)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class BrowserSession(Base):
    __tablename__ = "sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code_id: Mapped[int | None] = mapped_column(ForeignKey("guest_codes.id", ondelete="CASCADE"))
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    oauth: Mapped[dict] = mapped_column(JSON, default=dict)
    local_code_digest: Mapped[str | None] = mapped_column(String(64))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    until: Mapped[int] = mapped_column(Integer)


def now() -> int:
    return int(time.time())


def database(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def pragmas(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")

    return engine, sessionmaker(engine, expire_on_commit=False)
