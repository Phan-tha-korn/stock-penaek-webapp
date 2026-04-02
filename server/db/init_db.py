from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config.config_loader import load_master_config
from server.db.database import Base, engine
from server.db.models import Product, Role, StockStatus, User
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


async def create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        driver = conn.engine.url.get_backend_name()
        if driver == "sqlite":
            rows = await conn.exec_driver_sql("PRAGMA table_info(products)")
            cols = {str(row[1]) for row in rows.fetchall()}
            if "category_id" not in cols:
                await conn.exec_driver_sql("ALTER TABLE products ADD COLUMN category_id VARCHAR(36)")
            if "last_category_id" not in cols:
                await conn.exec_driver_sql("ALTER TABLE products ADD COLUMN last_category_id VARCHAR(36)")


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
    for u in users:
        db.add(u)
    await db.commit()

    res = await db.execute(select(User).where(User.username == "owner"))
    owner = res.scalar_one()

    cfg = load_master_config()
    default_min = float(cfg.get("min_stock_threshold") or 10)

    demo_products = [
        
    ]

    for (
        sku,
        name_th,
        name_en,
        category,
        ptype,
        unit,
        cost,
        sell,
        qty,
        min_s,
        max_s,
        is_test,
        supplier,
        barcode,
    ) in demo_products:
        p = Product(
            sku=sku,
            name_th=name_th,
            name_en=name_en,
            category=category,
            type=ptype,
            unit=unit,
            cost_price=cost,
            selling_price=sell,
            stock_qty=qty,
            min_stock=min_s,
            max_stock=max_s,
            status=calc_status(float(qty), float(min_s), float(max_s), bool(is_test)),
            is_test=bool(is_test),
            supplier=supplier,
            barcode=barcode,
            image_url=None,
            notes="",
            created_by=owner.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(p)

    await db.commit()

