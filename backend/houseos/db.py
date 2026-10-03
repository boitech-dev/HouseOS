import os
from datetime import datetime, UTC
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


def new_id():
    return str(uuid4())


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


url = settings.database_url or os.environ.get("DATABASE_URL", "")
if url.startswith("mysql://"):
    url = url.replace("mysql://", "mysql+pymysql://", 1)
# 40 request threads share this pool: room for all of them, and a short wait so a stall shows up as
# a quick error rather than 30 s of spinning (MariaDB allows 200 connections).
engine = (
    create_engine(
        url, pool_pre_ping=True, hide_parameters=True, pool_size=20, max_overflow=20, pool_timeout=10
    )
    if url
    else None
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    if engine is None:
        from fastapi import HTTPException

        raise HTTPException(503, "Database is not configured")
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise
