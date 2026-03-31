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
        ("TH-FOOD-0001", "บะหมี่กึ่งสำเร็จรูป รสต้มยำกุ้ง", "Instant noodles (Tom Yum)", "อาหารแห้ง > บะหมี่", "อาหาร", "piece", 5.5, 7.0, 120, default_min, 200, False, "สหพัฒน์", "8850000000001"),
        ("TH-FOOD-0002", "ปลากระป๋อง ซอสมะเขือเทศ", "Canned sardines (Tomato sauce)", "อาหารกระป๋อง > ปลา", "อาหาร", "piece", 12.0, 16.0, 48, default_min, 100, False, "ไทยยูเนี่ยน", "8850000000002"),
        ("TH-FOOD-0003", "น้ำปลาแท้ 700ml", "Fish sauce 700ml", "เครื่องปรุง > น้ำปลา", "เครื่องปรุง", "piece", 24.0, 32.0, 18, default_min, 60, False, "ทิพรส", "8850000000003"),
        ("TH-FOOD-0004", "ซีอิ๊วขาว 700ml", "Soy sauce 700ml", "เครื่องปรุง > ซีอิ๊ว", "เครื่องปรุง", "piece", 26.0, 35.0, 9, default_min, 60, False, "ภูเขาทอง", "8850000000004"),
        ("TH-FOOD-0005", "น้ำตาลทราย 1kg", "Sugar 1kg", "วัตถุดิบ > น้ำตาล", "วัตถุดิบ", "piece", 27.0, 35.0, 6, default_min, 50, False, "มิตรผล", "8850000000005"),
        ("TH-DRINK-0001", "น้ำดื่ม 600ml", "Drinking water 600ml", "เครื่องดื่ม > น้ำเปล่า", "เครื่องดื่ม", "piece", 4.0, 7.0, 240, default_min, 300, False, "สิงห์", "8850000000101"),
        ("TH-DRINK-0002", "ชาเขียวพร้อมดื่ม 420ml", "Green tea 420ml", "เครื่องดื่ม > ชาพร้อมดื่ม", "เครื่องดื่ม", "piece", 13.0, 18.0, 22, default_min, 120, False, "โออิชิ", "8850000000102"),
        ("TH-DRINK-0003", "กาแฟกระป๋อง 180ml", "Canned coffee 180ml", "เครื่องดื่ม > กาแฟ", "เครื่องดื่ม", "piece", 10.5, 15.0, 11, default_min, 120, False, "เบอร์ดี้", "8850000000103"),
        ("TH-HH-0001", "ผงซักฟอก 800g", "Laundry detergent 800g", "ของใช้ในบ้าน > ซักผ้า", "ของใช้", "piece", 39.0, 55.0, 14, default_min, 80, False, "บรีส", "8850000000201"),
        ("TH-HH-0002", "น้ำยาล้างจาน 550ml", "Dishwashing liquid 550ml", "ของใช้ในบ้าน > ครัว", "ของใช้", "piece", 18.0, 25.0, 8, default_min, 60, False, "ซันไลต์", "8850000000202"),
        ("TH-HH-0003", "ทิชชู่ม้วน 6 ม้วน", "Toilet tissue 6 rolls", "ของใช้ในบ้าน > กระดาษทิชชู่", "ของใช้", "piece", 45.0, 65.0, 5, default_min, 40, False, "สก๊อตต์", "8850000000203"),
        ("TH-PER-0001", "ยาสีฟัน 160g", "Toothpaste 160g", "ของใช้ส่วนตัว > ช่องปาก", "ของใช้ส่วนตัว", "piece", 32.0, 45.0, 12, default_min, 50, False, "คอลเกต", "8850000000301"),
        ("TH-PER-0002", "แชมพู 400ml", "Shampoo 400ml", "ของใช้ส่วนตัว > เส้นผม", "ของใช้ส่วนตัว", "piece", 52.0, 79.0, 7, default_min, 40, False, "แพนทีน", "8850000000302"),
        ("TH-PER-0003", "สบู่ก้อน 105g", "Bar soap 105g", "ของใช้ส่วนตัว > ทำความสะอาด", "ของใช้ส่วนตัว", "piece", 12.0, 18.0, 3, default_min, 60, False, "ลักส์", "8850000000303"),
        ("TH-SNACK-0001", "ขนมขบเคี้ยวมันฝรั่ง 50g", "Potato chips 50g", "ขนม > มันฝรั่ง", "ขนม", "piece", 12.0, 20.0, 26, default_min, 120, False, "เลย์", "8850000000401"),
        ("TH-SNACK-0002", "ขนมปังกรอบ 60g", "Crackers 60g", "ขนม > ปังกรอบ", "ขนม", "piece", 9.0, 15.0, 16, default_min, 120, False, "ฟาร์มเฮ้าส์", "8850000000402"),
        ("TH-ICE-0001", "ไอศกรีมแท่ง", "Ice cream bar", "แช่แข็ง > ไอศกรีม", "แช่แข็ง", "piece", 7.5, 12.0, 0, default_min, 100, False, "วอลล์", "8850000000501"),
        ("TH-DAIRY-0001", "นม UHT 200ml", "UHT milk 200ml", "นม > UHT", "นม", "piece", 9.0, 12.0, 9, default_min, 200, False, "ดัชมิลล์", "8850000000601"),
        ("TH-DAIRY-0002", "โยเกิร์ตรสธรรมชาติ 135g", "Yogurt (Plain) 135g", "นม > โยเกิร์ต", "นม", "piece", 10.0, 15.0, 2, default_min, 80, False, "เมจิ", "8850000000602"),
        ("TH-TEST-0001", "สินค้าใหม่ (รอเปิดใช้งาน)", "New product (pending)", "TEST STOCK", "TEST", "piece", 0.0, None, 0, default_min, 0, True, "", "TEST0001"),
        ("TH-TEST-0002", "อะไหล่สายชาร์จ (รอข้อมูลราคา)", "Charging cable (pending price)", "อิเล็กทรอนิกส์ > สายชาร์จ", "อิเล็กทรอนิกส์", "piece", 0.0, None, 0, default_min, 0, True, "OEM", "TEST0002"),
        ("TH-TEST-0003", "ของชำล็อตทดลอง", "Grocery test batch", "TEST STOCK", "TEST", "piece", 0.0, None, 0, default_min, 0, True, "", "TEST0003"),
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

