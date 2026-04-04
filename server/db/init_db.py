from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config.settings import settings
from server.db.models import Role, StockStatus, User
from server.services.security import hash_password


def calc_status(qty: float, min_stock: float, max_stock: float, is_test: bool) -> StockStatus:
    if is_test:
        return StockStatus.TEST
    if qty <= 0:
        return StockStatus.OUT
    if max_stock > 0 and qty >= max_stock:
        return StockStatus.FULL
    if qty <= min_stock:
        return StockStatus.CRITICAL
    if qty <= min_stock * 1.5:
        return StockStatus.LOW
    return StockStatus.NORMAL


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_alembic_config() -> Config:
    root = _repo_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.resolved_database_url())
    return config


def _upgrade_schema_sync() -> None:
    command.upgrade(_build_alembic_config(), "head")


async def create_all() -> None:
    await asyncio.to_thread(_upgrade_schema_sync)


async def seed_if_empty(db: AsyncSession) -> None:
    res = await db.execute(select(User).limit(1))
    if res.scalar_one_or_none():
        return

    users = [
        User(
            username="owner",
            display_name="เจ้าของกิจการ",
            role=Role.OWNER,
            is_active=True,
            language="th",
            password_hash=hash_password("Owner@1234"),
            totp_secret=None,
        ),
        User(
            username="admin",
            display_name="ผู้จัดการร้าน",
            role=Role.ADMIN,
            is_active=True,
            language="th",
            password_hash=hash_password("Admin@1234"),
            totp_secret=None,
        ),
        User(
            username="stock",
            display_name="พนักงานคลัง",
            role=Role.STOCK,
            is_active=True,
            language="th",
            password_hash=hash_password("Stock@1234"),
            totp_secret=None,
        ),
        User(
            username="accountant",
            display_name="ฝ่ายบัญชี",
            role=Role.ACCOUNTANT,
            is_active=True,
            language="th",
            password_hash=hash_password("Acc@1234"),
            totp_secret=None,
        ),
        User(
            username="dev",
            display_name="นักพัฒนาระบบ",
            role=Role.DEV,
            is_active=True,
            language="en",
            password_hash=hash_password("Dev@1234"),
            totp_secret=None,
        ),
    ]
    for user in users:
        db.add(user)
    await db.commit()
