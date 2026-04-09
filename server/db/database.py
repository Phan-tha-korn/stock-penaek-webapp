from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine.url import make_url

from server.config.settings import settings


class Base(DeclarativeBase):
    pass


_db_url = settings.resolved_database_url()
_connect_args: dict = {}
_is_pg = False
try:
    _is_pg = make_url(_db_url).drivername.startswith("postgresql")
    if _is_pg:
        _connect_args = {"ssl": True}
except Exception:
    _connect_args = {}

_pool_kwargs: dict = {}
if _is_pg:
    _pool_kwargs = {"pool_size": 20, "max_overflow": 40, "pool_pre_ping": True}

engine: AsyncEngine = create_async_engine(
    _db_url,
    future=True,
    echo=False,
    connect_args=_connect_args,
    **_pool_kwargs,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

