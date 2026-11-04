from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal: sessionmaker[Session] = sessionmaker(expire_on_commit=False)


def init_db(url: str | None = None):
    global _engine
    url = url or config.DATABASE_URL
    if url.startswith("sqlite:///"):
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        kwargs = {"connect_args": {"check_same_thread": False}}
    else:
        kwargs = {"pool_pre_ping": True}
    _engine = create_engine(url, **kwargs)
    SessionLocal.configure(bind=_engine)
    from . import models  # noqa: F401

    Base.metadata.create_all(_engine)
    return _engine


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
