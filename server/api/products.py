from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import require_roles, get_current_user
from server.api.schemas import (
    ProductBulkCreateIn,
    ProductCreateIn,
    ProductDeleteIn,
    ProductListOut,
    ProductName,
    ProductOut,
    ProductUpdateIn,
    ProductBulkImportOut,
    ProductBulkRowResult,
    SheetsImportIn,
    SheetsImportOut,
    SheetsSyncOut,
    StockAdjustIn,
)
from server.db.database import get_db
from server.db.models import Product, ProductCategory, Role, StockAlertState, StockTransaction, TxnType, User
from server.db.init_db import calc_status
from server.services.audit import write_audit_log
from server.services.media_store import choose_image_for_row, parse_products_csv, read_zip_payload, save_product_image_bytes
from server.realtime.socket_manager import broadcast
from server.config.config_loader import load_master_config
from server.config.settings import settings


router = APIRouter(prefix="/products", tags=["products"])

DELETED_PREFIX = "__DELETED__:"
UNCATEGORIZED_SENTINEL = "__uncategorized__"


def _d(v) -> str:
    if v is None:
        return "0"
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)

def _is_deleted(p: Product) -> bool:
    return bool((p.notes or "").startswith(DELETED_PREFIX))


def _trigger_sheet_sync() -> None:
    try:
        from server.services.gsheets import schedule_sheet_sync
        schedule_sheet_sync()
    except Exception:
        pass


def _build_line_notification_message(*, product: Product, new_qty: float, new_pct: float, notify_messages: list[str], user: User, reason: str | None) -> str:
    cfg = load_master_config()
    lines = [f"[STOCK NOTICE] {product.name_th or product.sku}"]
    if bool(cfg.get("notification_include_name", True)):
        lines[0] = f"[STOCK NOTICE] {product.name_th or product.sku}"
    if bool(cfg.get("notification_include_sku", True)):
        lines.append(f"SKU: {product.sku}")
    if bool(cfg.get("notification_include_status", True)):
        lines.append(f"สถานะ: {product.status.value}")
    if bool(cfg.get("notification_include_current_qty", True)):
        lines.append(f"คงเหลือ: {new_qty} {product.unit}")
    if bool(cfg.get("notification_include_target_qty", True)):
        lines.append(f"ควรมี: {float(product.max_stock)} {product.unit}")
    if bool(cfg.get("notification_include_restock_qty", True)):
        lines.append(f"ต้องเติม: {max(0.0, float(product.max_stock) - new_qty)} {product.unit}")
    lines.append(f"เปอร์เซ็นต์: {new_pct:.1f}%")
    lines.append(f"เหตุการณ์: {', '.join(notify_messages)}")
    if bool(cfg.get("notification_include_actor", True)):
        lines.append(f"ผู้ทำรายการ: {user.username} ({user.role.value})")
    if bool(cfg.get("notification_include_reason", True)):
        lines.append(f"หมายเหตุ: {reason or '-'}")
    if bool(cfg.get("notification_include_image_url", False)) and product.image_url:
        lines.append(f"รูปสินค้า: {product.image_url}")
    return "\n" + "\n".join(lines)


def _to_out(p: Product) -> ProductOut:
    return ProductOut(
        id=p.id,
        sku=p.sku,
        category_id=p.category_id,
        name=ProductName(th=p.name_th, en=p.name_en),
        category=p.category if p.category_id else "",
        type=p.type,
        unit=p.unit,
        cost_price=_d(p.cost_price),
        selling_price=_d(p.selling_price) if p.selling_price is not None else None,
        stock_qty=_d(p.stock_qty),
        min_stock=_d(p.min_stock),
        max_stock=_d(p.max_stock),
        status=p.status,
        is_test=p.is_test,
        supplier=p.supplier,
        barcode=p.barcode,
        image_url=p.image_url,
        notes=p.notes,
        created_at=p.created_at,
        updated_at=p.updated_at,
        created_by=p.created_by,
    )


def _is_integer_only_unit(unit: str) -> bool:
    normalized = (unit or "").strip().lower()
    return normalized in {"ชิ้น", "piece", "pcs", "pc"}


def _round_rule(value: float) -> float:
    whole = int(value)
    fraction = abs(value - whole)
    if fraction <= 0.5:
        return float(whole)
    return float(whole + 1)


def _coerce_qty(value: float | None, *, unit: str, field_name: str) -> float:
    numeric = float(value or 0)
    if numeric < 0:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")
    if _is_integer_only_unit(unit) and not numeric.is_integer():
        raise HTTPException(status_code=400, detail=f"{field_name}_must_be_integer")
    return int(numeric) if _is_integer_only_unit(unit) else numeric


async def _resolve_category(db: AsyncSession, category_id: str | None) -> ProductCategory | None:
    value = (category_id or "").strip()
    if not value:
        return None
    category = await db.scalar(select(ProductCategory).where(ProductCategory.id == value, ProductCategory.is_deleted.is_(False)))
    if not category:
        raise HTTPException(status_code=400, detail="invalid_category")
    return category


def _apply_product_payload(p: Product, payload: ProductCreateIn | ProductUpdateIn) -> None:
    unit_value = ((payload.unit or "") if hasattr(payload, "unit") and payload.unit is not None else p.unit).strip()
    if isinstance(payload, ProductCreateIn) or payload.name_th is not None:
        p.name_th = ((payload.name_th or "") if hasattr(payload, "name_th") else p.name_th).strip()
    if isinstance(payload, ProductCreateIn) or payload.name_en is not None:
        p.name_en = ((payload.name_en or "") if hasattr(payload, "name_en") else p.name_en).strip()
    if isinstance(payload, ProductCreateIn) or payload.category is not None:
        p.category = ((payload.category or "") if hasattr(payload, "category") else p.category).strip()
    if isinstance(payload, ProductCreateIn) or payload.type is not None:
        p.type = ((payload.type or "") if hasattr(payload, "type") else p.type).strip()
    if isinstance(payload, ProductCreateIn) or payload.unit is not None:
        p.unit = unit_value
    if isinstance(payload, ProductCreateIn) or payload.cost_price is not None:
        p.cost_price = float(getattr(payload, "cost_price", 0) or 0)
    if isinstance(payload, ProductCreateIn):
        p.selling_price = float(payload.selling_price) if payload.selling_price is not None else None
    elif payload.selling_price is not None:
        p.selling_price = float(payload.selling_price)
    if isinstance(payload, ProductCreateIn):
        p.stock_qty = _coerce_qty(float(payload.stock_qty or 0), unit=unit_value, field_name="stock_qty")
    if isinstance(payload, ProductCreateIn) or payload.min_stock is not None:
        p.min_stock = _coerce_qty(float(getattr(payload, "min_stock", 0) or 0), unit=unit_value, field_name="min_stock")
    if isinstance(payload, ProductCreateIn) or payload.max_stock is not None:
        p.max_stock = _coerce_qty(float(getattr(payload, "max_stock", 0) or 0), unit=unit_value, field_name="max_stock")
    if isinstance(payload, ProductCreateIn):
        p.is_test = bool(payload.is_test)
    if isinstance(payload, ProductCreateIn) or payload.supplier is not None:
        p.supplier = ((payload.supplier or "") if hasattr(payload, "supplier") else p.supplier).strip()
    if isinstance(payload, ProductCreateIn) or payload.barcode is not None:
        p.barcode = ((payload.barcode or "") if hasattr(payload, "barcode") else p.barcode).strip()
    if isinstance(payload, ProductCreateIn) or payload.image_url is not None:
        p.image_url = getattr(payload, "image_url", p.image_url)
    if isinstance(payload, ProductCreateIn) or payload.notes is not None:
        p.notes = getattr(payload, "notes", p.notes) or ""
    p.status = calc_status(float(p.stock_qty), float(p.min_stock), float(p.max_stock), bool(p.is_test))
    p.updated_at = datetime.utcnow()


@router.get("", response_model=ProductListOut, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.OWNER, Role.DEV]))])
async def list_products(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = None,
    status: str | None = None,
    category_id: str | None = None,
    uncategorized_only: bool = False,
    product_type: str | None = None,
    is_test: bool | None = None,
    include_deleted: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Product)

    if not (include_deleted and user.role in (Role.OWNER, Role.DEV)):
        stmt = stmt.where(~Product.notes.like(f"{DELETED_PREFIX}%"))

    if q:
        parts = [x.strip().lower() for x in q.strip().split() if x.strip()]
        if parts:
            token_conds = []
            for token in parts:
                qs = f"%{token}%"
                token_conds.append(
                    or_(
                        func.lower(Product.sku).like(qs),
                        func.lower(Product.name_th).like(qs),
                        func.lower(Product.name_en).like(qs),
                        func.lower(Product.category).like(qs),
                        func.lower(Product.type).like(qs),
                        func.lower(Product.barcode).like(qs),
                        func.lower(Product.supplier).like(qs),
                    )
                )
            stmt = stmt.where(and_(*token_conds))

    if status:
        stmt = stmt.where(Product.status == status)
    if uncategorized_only:
        stmt = stmt.where(Product.category_id.is_(None))
    elif category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if product_type:
        stmt = stmt.where(func.lower(Product.type) == product_type.strip().lower())
    if is_test is not None:
        stmt = stmt.where(Product.is_test.is_(is_test))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    res = await db.execute(stmt.order_by(Product.updated_at.desc()).limit(limit).offset(offset))
    items = res.scalars().all()

    out = [_to_out(p) for p in items]
    return ProductListOut(items=out, total=int(total or 0))


@router.get("/public/products/{sku}", response_model=ProductOut)
async def get_public_product(sku: str, db: AsyncSession = Depends(get_db)):
    product = await db.scalar(select(Product).where(Product.sku == sku))
    if not product or _is_deleted(product):
        raise HTTPException(status_code=404, detail="Product not found")
    return _to_out(product)


@router.post(
    "/import-from-sheets",
    response_model=SheetsImportOut,
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))],
)
async def import_from_sheets(
    payload: SheetsImportIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        from server.services.gsheets import import_stock_from_sheet, sync_all_to_sheets
    except Exception:
        raise HTTPException(status_code=500, detail="sheets_not_available")

    res = await import_stock_from_sheet(
        actor_id=user.id,
        overwrite_stock_qty=bool(payload.overwrite_stock_qty),
        overwrite_prices=bool(payload.overwrite_prices),
    )
    if not res.get("ok"):
        return SheetsImportOut(ok=False, error=str(res.get("error") or "import_failed"))

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SHEETS_IMPORT",
        entity="sheets",
        entity_id=None,
        success=True,
        message="import_stock",
        before=None,
        after=res,
    )

    _trigger_sheet_sync()

    return SheetsImportOut(
        ok=True,
        created=int(res.get("created") or 0),
        updated=int(res.get("updated") or 0),
        skipped=int(res.get("skipped") or 0),
    )


@router.post(
    "/sync-to-sheets",
    response_model=SheetsSyncOut,
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))],
)
async def sync_to_sheets():
    try:
        from server.services.gsheets import sync_all_to_sheets
    except Exception:
        return SheetsSyncOut(ok=False, error="sheets_not_available")
    try:
        ok = await sync_all_to_sheets(fail_if_busy=True)
        if not ok:
            return SheetsSyncOut(ok=False, error="sync_skipped")
        return SheetsSyncOut(ok=True)
    except Exception as e:
        return SheetsSyncOut(ok=False, error=str(e))


@router.post(
    "/sync-to-sheets/full",
    response_model=SheetsSyncOut,
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))],
)
async def force_full_sync_to_sheets():
    try:
        from server.services.gsheets import sync_all_to_sheets
    except Exception:
        return SheetsSyncOut(ok=False, error="sheets_not_available")
    try:
        ok = await sync_all_to_sheets(fail_if_busy=True)
        if not ok:
            return SheetsSyncOut(ok=False, error="sync_skipped")
        return SheetsSyncOut(ok=True)
    except Exception as e:
        return SheetsSyncOut(ok=False, error=str(e))


@router.get("/filter-options", response_model=dict, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.OWNER, Role.DEV, Role.ACCOUNTANT]))])
async def product_filter_options(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Product.type).where(Product.type.is_not(None), Product.type != "")
    if user.role not in (Role.OWNER, Role.DEV):
        stmt = stmt.where(~Product.notes.like(f"{DELETED_PREFIX}%"))
    types = sorted({str(x[0]).strip() for x in (await db.execute(stmt)).all() if str(x[0]).strip()}, key=str.lower)
    return {"types": types}


@router.post("", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def create_product(
    payload: ProductCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sku = payload.sku.strip()
    if not sku:
        raise HTTPException(status_code=400, detail="invalid_sku")

    existing = await db.scalar(select(Product).where(Product.sku == sku))
    if existing:
        raise HTTPException(status_code=409, detail="sku_exists")
    category = await _resolve_category(db, payload.category_id)

    p = Product(
        sku=sku,
        category_id=None,
        last_category_id=None,
        name_th="",
        name_en="",
        category="",
        type="",
        unit="",
        cost_price=0,
        selling_price=None,
        stock_qty=0,
        min_stock=0,
        max_stock=0,
        status=calc_status(0, 0, 0, False),
        is_test=False,
        supplier="",
        barcode="",
        image_url=None,
        notes="",
        created_by=user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    _apply_product_payload(p, payload)
    p.category_id = category.id if category else None
    p.last_category_id = category.id if category else p.last_category_id
    p.category = category.name if category else (p.category or "")
    db.add(p)
    await db.commit()
    await db.refresh(p)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_CREATE",
        entity="product",
        entity_id=p.id,
        success=True,
        message="created",
        before=None,
        after={"sku": p.sku, "name_th": p.name_th},
    )

    _trigger_sheet_sync()

    return _to_out(p)


@router.post("/create-with-image", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def create_product_with_image(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sku: str = Form(...),
    category_id: str | None = Form(None),
    name_th: str = Form(...),
    name_en: str = Form(""),
    category: str = Form(""),
    type: str = Form(""),
    unit: str = Form(""),
    cost_price: float = Form(0),
    selling_price: float | None = Form(None),
    stock_qty: float = Form(0),
    min_stock: float = Form(0),
    max_stock: float = Form(0),
    is_test: bool = Form(False),
    supplier: str = Form(""),
    barcode: str = Form(""),
    notes: str = Form(""),
    image: UploadFile | None = File(default=None),
):
    payload = ProductCreateIn(
        sku=sku,
        category_id=category_id,
        name_th=name_th,
        name_en=name_en,
        category=category,
        type=type,
        unit=unit,
        cost_price=cost_price,
        selling_price=selling_price,
        stock_qty=stock_qty,
        min_stock=min_stock,
        max_stock=max_stock,
        is_test=is_test,
        supplier=supplier,
        barcode=barcode,
        notes=notes,
    )
    if image is not None and image.filename:
        raw = await image.read()
        try:
            payload.image_url = save_product_image_bytes(payload.sku, raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return await create_product(payload=payload, request=request, db=db, user=user)


@router.post("/bulk-create", response_model=ProductListOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def bulk_create_products(
    payload: ProductBulkCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if len(payload.items) < 2:
        raise HTTPException(status_code=400, detail="bulk_items_too_few")

    normalized: list[Product] = []
    seen: set[str] = set()
    for item in payload.items:
        sku = item.sku.strip()
        if not sku or not item.name_th.strip():
            raise HTTPException(status_code=400, detail="invalid_bulk_item")
        if sku in seen:
            raise HTTPException(status_code=400, detail="duplicate_bulk_sku")
        seen.add(sku)
        existing = await db.scalar(select(Product).where(Product.sku == sku))
        if existing and not _is_deleted(existing):
            raise HTTPException(status_code=409, detail=f"sku_exists:{sku}")
        category = await _resolve_category(db, item.category_id)
        product = Product(
            sku=sku,
            category_id=category.id if category else None,
            last_category_id=category.id if category else None,
            name_th="",
            name_en="",
            category=category.name if category else "",
            type="",
            unit="",
            cost_price=0,
            selling_price=None,
            stock_qty=0,
            min_stock=0,
            max_stock=0,
            status=calc_status(0, 0, 0, False),
            is_test=False,
            supplier="",
            barcode="",
            image_url=None,
            notes="",
            created_by=user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        _apply_product_payload(
            product,
            ProductCreateIn(
                sku=sku,
                category_id=item.category_id,
                name_th=item.name_th,
                name_en=item.name_en,
                category=category.name if category else (item.category or ""),
                type=item.type,
                unit=item.unit,
                cost_price=item.cost_price,
                selling_price=item.selling_price,
                stock_qty=item.stock_qty,
                min_stock=item.min_stock,
                max_stock=item.max_stock,
                is_test=item.is_test,
                supplier=item.supplier,
                barcode=item.barcode,
                notes=item.notes,
            ),
        )
        normalized.append(product)

    for product in normalized:
        db.add(product)
    await db.commit()
    for product in normalized:
        await db.refresh(product)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_BULK_CREATE",
        entity="product",
        entity_id=None,
        success=True,
        message="bulk_created",
        before=None,
        after={"count": len(normalized)},
    )
    _trigger_sheet_sync()
    return ProductListOut(items=[_to_out(product) for product in normalized], total=len(normalized))


@router.get("/bulk-import-template-zip", dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def bulk_import_template_zip(rows: int = Query(default=5, ge=1, le=200)):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        csv_lines = ["sku,name_th,category,unit,stock_qty,min_stock,max_stock,cost_price,selling_price,image_key"]
        for index in range(1, rows + 1):
            sku = f"SKU-{index:04d}"
            image_key = f"images/product-{index:04d}.jpg"
            csv_lines.append(f'{sku},,หมวดหมู่ตัวอย่าง,ชิ้น,0,0,0,0,0,{image_key}')
        zf.writestr("products.csv", "\n".join(csv_lines) + "\n")
        zf.writestr(
            "README.txt",
            (
                "ZIP ตัวอย่างสำหรับเพิ่มสินค้าใหม่หลายรายการ\n"
                "- ต้องมีไฟล์ products.csv ที่ root ของ ZIP\n"
                "- ถ้าต้องการแนบรูป ให้ใส่รูปไว้ในโฟลเดอร์ images/\n"
                "- ค่า image_key ใน products.csv ต้องตรงกับ path ของรูปใน ZIP เช่น images/product-0001.jpg\n"
                "- คอลัมน์ที่รองรับ: sku,name_th,category,unit,stock_qty,min_stock,max_stock,cost_price,selling_price,image_key\n"
            ),
        )
        zf.writestr("images/put-images-here.txt", "วางรูปสินค้าในโฟลเดอร์ images/ แล้วแก้ image_key ใน products.csv ให้ตรงกัน\n")
    buffer.seek(0)
    file_name = f"products-template-{rows}-rows.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/bulk-import-zip", response_model=ProductBulkImportOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def bulk_import_zip(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    overwrite_existing: bool = Form(False),
):
    raw_zip = await file.read()
    try:
        rows, images = read_zip_payload(raw_zip)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    created = 0
    updated = 0
    failed = 0
    items: list[ProductBulkRowResult] = []

    for row in rows:
        try:
            existing = await db.scalar(select(Product).where(Product.sku == row.sku))
            image_raw = choose_image_for_row(row, images)
            image_url = None
            if image_raw:
                try:
                    image_url = save_product_image_bytes(row.sku, image_raw)
                except ValueError:
                    image_url = None

            if existing and _is_deleted(existing):
                failed += 1
                items.append(ProductBulkRowResult(row=row.index, sku=row.sku, ok=False, action="skip", error="soft_deleted"))
                continue

            if existing and not overwrite_existing:
                failed += 1
                items.append(ProductBulkRowResult(row=row.index, sku=row.sku, ok=False, action="skip", error="already_exists"))
                continue

            if existing:
                payload = ProductUpdateIn(
                    name_th=row.name_th,
                    category=row.category,
                    unit=row.unit,
                    min_stock=row.min_stock,
                    max_stock=row.max_stock,
                    cost_price=row.cost_price,
                    selling_price=row.selling_price,
                    image_url=image_url if image_url else existing.image_url,
                )
                _apply_product_payload(existing, payload)
                updated += 1
                items.append(ProductBulkRowResult(row=row.index, sku=row.sku, ok=True, action="updated"))
            else:
                p = Product(
                    sku=row.sku,
                    name_th="",
                    name_en="",
                    category="",
                    type="",
                    unit="",
                    cost_price=0,
                    selling_price=None,
                    stock_qty=0,
                    min_stock=0,
                    max_stock=0,
                    status=calc_status(0, 0, 0, False),
                    is_test=False,
                    supplier="",
                    barcode="",
                    image_url=None,
                    notes="",
                    created_by=user.id,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                _apply_product_payload(
                    p,
                    ProductCreateIn(
                        sku=row.sku,
                        name_th=row.name_th,
                        category=row.category,
                        unit=row.unit,
                        stock_qty=row.stock_qty,
                        min_stock=row.min_stock,
                        max_stock=row.max_stock,
                        cost_price=row.cost_price,
                        selling_price=row.selling_price,
                        image_url=image_url,
                    ),
                )
                db.add(p)
                created += 1
                items.append(ProductBulkRowResult(row=row.index, sku=row.sku, ok=True, action="created"))
        except Exception as e:
            failed += 1
            items.append(ProductBulkRowResult(row=row.index, sku=row.sku, ok=False, action="error", error=str(e)))

    await db.commit()

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_BULK_IMPORT_ZIP",
        entity="product",
        entity_id=None,
        success=True,
        message="bulk_import_zip",
        before=None,
        after={"created": created, "updated": updated, "failed": failed},
    )
    _trigger_sheet_sync()
    return ProductBulkImportOut(ok=True, created=created, updated=updated, failed=failed, items=items)


@router.put("/{sku}", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def update_product(
    sku: str,
    payload: ProductUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = await db.scalar(select(Product).where(Product.sku == sku))
    if not p or _is_deleted(p):
        raise HTTPException(status_code=404, detail="Product not found")

    before = {"sku": p.sku, "name_th": p.name_th}
    fields_set = getattr(payload, "model_fields_set", set())
    if "category_id" in fields_set:
        category = await _resolve_category(db, payload.category_id)
        p.category_id = category.id if category else None
        if category:
            p.last_category_id = category.id
            p.category = category.name
        else:
            p.category = ""

    _apply_product_payload(p, payload)

    await db.commit()
    await db.refresh(p)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_UPDATE",
        entity="product",
        entity_id=p.id,
        success=True,
        message="updated",
        before=before,
        after={"sku": p.sku, "name_th": p.name_th},
    )

    _trigger_sheet_sync()

    return _to_out(p)


@router.post("/{sku}/update-with-image", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def update_product_with_image(
    sku: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    category_id: str | None = Form(None),
    name_th: str | None = Form(None),
    name_en: str | None = Form(None),
    category: str | None = Form(None),
    type: str | None = Form(None),
    unit: str | None = Form(None),
    cost_price: float | None = Form(None),
    selling_price: float | None = Form(None),
    min_stock: float | None = Form(None),
    max_stock: float | None = Form(None),
    supplier: str | None = Form(None),
    barcode: str | None = Form(None),
    notes: str | None = Form(None),
    image: UploadFile | None = File(default=None),
):
    p = await db.scalar(select(Product).where(Product.sku == sku))
    if not p or _is_deleted(p):
        raise HTTPException(status_code=404, detail="Product not found")

    payload = ProductUpdateIn(
        category_id=category_id,
        name_th=name_th,
        name_en=name_en,
        category=category,
        type=type,
        unit=unit,
        cost_price=cost_price,
        selling_price=selling_price,
        min_stock=min_stock,
        max_stock=max_stock,
        supplier=supplier,
        barcode=barcode,
        notes=notes,
    )
    if image is not None and image.filename:
        try:
            payload.image_url = save_product_image_bytes(p.sku, await image.read())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return await update_product(sku=sku, payload=payload, request=request, db=db, user=user)


@router.post("/bulk-delete", response_model=dict, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def bulk_delete(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skus = payload.get("skus") if isinstance(payload, dict) else None
    reason = (payload.get("reason") or "").strip() if isinstance(payload, dict) else ""
    if not isinstance(skus, list) or not skus:
        raise HTTPException(status_code=400, detail="invalid_skus")

    ts = datetime.utcnow().isoformat(timespec="seconds")
    done = 0
    for raw in skus:
        sku = (str(raw) or "").strip()
        if not sku:
            continue
        p = await db.scalar(select(Product).where(Product.sku == sku))
        if not p or _is_deleted(p):
            continue
        p.notes = f"{DELETED_PREFIX}{ts}:{user.id}:{reason}"
        p.updated_at = datetime.utcnow()
        done += 1

    await db.commit()

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_BULK_DELETE",
        entity="product",
        entity_id=None,
        success=True,
        message=reason or "bulk_deleted",
        before=None,
        after={"count": done},
    )

    _trigger_sheet_sync()

    return {"ok": True, "deleted": done}


@router.post("/delete-all-test", response_model=dict, dependencies=[Depends(require_roles([Role.DEV]))])
async def delete_all_test(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    res = await db.execute(select(Product))
    products = res.scalars().all()
    ts = datetime.utcnow().isoformat(timespec="seconds")
    done = 0
    for p in products:
        if _is_deleted(p):
            continue
        if not p.is_test:
            continue
        p.notes = f"{DELETED_PREFIX}{ts}:{user.id}:purge_test"
        p.updated_at = datetime.utcnow()
        done += 1

    await db.commit()

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_DELETE_ALL_TEST",
        entity="product",
        entity_id=None,
        success=True,
        message="purge_test",
        before=None,
        after={"count": done},
    )

    _trigger_sheet_sync()

    return {"ok": True, "deleted": done}


@router.post("/delete-all", response_model=dict, dependencies=[Depends(require_roles([Role.DEV]))])
async def delete_all(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    confirm = (payload.get("confirm") or "") if isinstance(payload, dict) else ""
    if confirm != "DELETE_ALL":
        raise HTTPException(status_code=400, detail="confirm_required")

    res = await db.execute(select(Product))
    products = res.scalars().all()
    ts = datetime.utcnow().isoformat(timespec="seconds")
    done = 0
    for p in products:
        if _is_deleted(p):
            continue
        p.notes = f"{DELETED_PREFIX}{ts}:{user.id}:purge_all"
        p.updated_at = datetime.utcnow()
        done += 1

    await db.commit()

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_DELETE_ALL",
        entity="product",
        entity_id=None,
        success=True,
        message="purge_all",
        before=None,
        after={"count": done},
    )

    _trigger_sheet_sync()

    return {"ok": True, "deleted": done}


@router.post("/{sku}/delete", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def delete_product(
    sku: str,
    payload: ProductDeleteIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = await db.scalar(select(Product).where(Product.sku == sku))
    if not p or _is_deleted(p):
        raise HTTPException(status_code=404, detail="Product not found")

    ts = datetime.utcnow().isoformat(timespec="seconds")
    reason = (payload.reason or "").strip()
    p.notes = f"{DELETED_PREFIX}{ts}:{user.id}:{reason}"
    p.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(p)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_DELETE",
        entity="product",
        entity_id=p.id,
        success=True,
        message=reason or "deleted",
        before={"sku": p.sku},
        after={"sku": p.sku},
    )

    _trigger_sheet_sync()

    return _to_out(p)


@router.post("/{sku}/restore", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def restore_product(
    sku: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = await db.scalar(select(Product).where(Product.sku == sku))
    if not p or not _is_deleted(p):
        raise HTTPException(status_code=404, detail="Product not found")

    p.notes = ""
    p.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(p)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="PRODUCT_RESTORE",
        entity="product",
        entity_id=p.id,
        success=True,
        message="restored",
        before={"sku": p.sku},
        after={"sku": p.sku},
    )

    _trigger_sheet_sync()

    return _to_out(p)

@router.post("/{sku}/adjust", response_model=ProductOut, dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV, Role.ACCOUNTANT]))])
async def adjust_stock(
    sku: str,
    payload: StockAdjustIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role == Role.ACCOUNTANT and payload.type == TxnType.ADJUST:
        raise HTTPException(status_code=403, detail="insufficient_role")
    product = await db.scalar(select(Product).where(Product.sku == sku))
    if not product or _is_deleted(product):
        raise HTTPException(status_code=404, detail="Product not found")

    old_status = product.status.value
    old_qty = float(product.stock_qty)
    adjust_amount = _coerce_qty(payload.qty, unit=product.unit, field_name="qty")
    if payload.type in (TxnType.STOCK_IN, TxnType.STOCK_OUT) and adjust_amount <= 0:
        raise HTTPException(status_code=400, detail="qty_must_be_positive")

    if payload.type == TxnType.STOCK_OUT:
        if old_qty < adjust_amount:
            raise HTTPException(status_code=400, detail="Insufficient stock")
        new_qty = old_qty - adjust_amount
    else: # STOCK_IN or ADJUST
        new_qty = old_qty + adjust_amount if payload.type == TxnType.STOCK_IN else adjust_amount

    product.stock_qty = new_qty
    product.status = calc_status(new_qty, float(product.min_stock), float(product.max_stock), product.is_test)
    product.updated_at = datetime.utcnow()

    txn = StockTransaction(
        type=payload.type,
        product_id=product.id,
        sku=product.sku,
        qty=(new_qty - old_qty) if payload.type == TxnType.ADJUST else adjust_amount,
        unit_cost=product.cost_price,
        unit_price=product.selling_price,
        reason=payload.reason,
        created_by=user.id
    )
    db.add(txn)
    
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action=f"STOCK_{payload.type.value}",
        entity="product",
        entity_id=product.id,
        success=True,
        message=payload.reason,
        before={"qty": old_qty, "status": old_status},
        after={"qty": new_qty, "status": product.status.value}
    )

    await db.commit()
    await db.refresh(product)

    try:
        if settings.notification_enabled:
            max_stock = float(product.max_stock or 0)
            if max_stock > 0:
                old_pct = (old_qty / max_stock) * 100.0 if max_stock else 0.0
                new_pct = (new_qty / max_stock) * 100.0 if max_stock else 0.0

                low_levels = [int(x) for x in (settings.notification_low_levels_pct or []) if 0 <= int(x) <= 100]
                high_levels = [int(x) for x in (settings.notification_high_levels_pct or []) if 0 <= int(x) <= 100]
                low_levels = sorted(list(dict.fromkeys(low_levels)), reverse=True)
                high_levels = sorted(list(dict.fromkeys(high_levels)))

                if low_levels or high_levels:
                    state = await db.scalar(select(StockAlertState).where(StockAlertState.product_id == product.id))
                    if not state:
                        state = StockAlertState(product_id=product.id, last_low_level_pct=None, last_high_level_pct=None, last_pct=None)
                        db.add(state)

                    if low_levels and new_pct > float(max(low_levels)):
                        state.last_low_level_pct = None
                    if high_levels and new_pct < float(min(high_levels)):
                        state.last_high_level_pct = None

                    low_crossed = [lvl for lvl in low_levels if old_pct > float(lvl) >= new_pct]
                    high_crossed = [lvl for lvl in high_levels if old_pct < float(lvl) <= new_pct]

                    notify_messages: list[str] = []

                    if low_crossed:
                        target = min(low_crossed)
                        if state.last_low_level_pct is None or target < int(state.last_low_level_pct):
                            state.last_low_level_pct = int(target)
                            notify_messages.append(f"ลงถึง {target}%")

                    if high_crossed:
                        target = max(high_crossed)
                        if state.last_high_level_pct is None or target > int(state.last_high_level_pct):
                            state.last_high_level_pct = int(target)
                            notify_messages.append(f"ขึ้นถึง {target}%")

                    state.last_pct = float(new_pct)
                    await db.commit()

                    if notify_messages:
                        try:
                            import asyncio
                            from server.services.line import send_line_notify

                            msg = _build_line_notification_message(
                                product=product,
                                new_qty=new_qty,
                                new_pct=new_pct,
                                notify_messages=notify_messages,
                                user=user,
                                reason=payload.reason,
                            )
                            for r in (settings.notification_roles or []):
                                asyncio.create_task(send_line_notify(str(r), msg))
                        except Exception:
                            pass
    except Exception:
        pass

    try:
        await broadcast(
            "stock_updated",
            {
                "sku": product.sku,
                "stock_qty": _d(product.stock_qty),
                "status": product.status.value,
                "updated_at": product.updated_at.isoformat(),
                "type": payload.type.value,
                "old_qty": old_qty,
                "new_qty": new_qty,
                "delta": (new_qty - old_qty),
                "actor_username": user.username,
                "actor_role": user.role.value,
            },
        )
    except Exception:
        pass

    _trigger_sheet_sync()

    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=ProductName(th=product.name_th, en=product.name_en),
        category=product.category,
        type=product.type,
        unit=product.unit,
        cost_price=_d(product.cost_price),
        selling_price=_d(product.selling_price) if product.selling_price is not None else None,
        stock_qty=_d(product.stock_qty),
        min_stock=_d(product.min_stock),
        max_stock=_d(product.max_stock),
        status=product.status,
        is_test=product.is_test,
        supplier=product.supplier,
        barcode=product.barcode,
        image_url=product.image_url,
        notes=product.notes,
        created_at=product.created_at,
        updated_at=product.updated_at,
        created_by=product.created_by,
    )

