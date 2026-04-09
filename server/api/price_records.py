from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.db.database import get_db
from server.db.models import (
    PriceRecord,
    PriceRecordStatus,
    PriceSourceType,
    Product,
    Role,
    Supplier,
    User,
)
from server.services.audit import write_audit_log
from server.services.branches import ensure_default_branch
from server.services.pricing import (
    compute_price_record_totals,
    normalize_utc_datetime,
    resolve_exchange_rate_snapshot,
    serialize_price_record,
    serialize_utc_datetime,
    utc_now,
    validate_area_scope,
    validate_delivery_mode,
    validate_price_dimension,
    validate_price_record_payload,
    validate_price_source_type,
    validate_price_status,
    validate_quantity_range,
)
from server.services.search import sync_price_search_projections_for_price_records

router = APIRouter(prefix="/price-records", tags=["price-records"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PriceRecordCreateIn(BaseModel):
    product_id: str
    supplier_id: str
    source_type: str = "manual_entry"
    status: str = "draft"
    delivery_mode: str = "standard"
    area_scope: str = "global"
    price_dimension: str = "real_total_cost"
    quantity_min: int = 1
    quantity_max: int | None = None
    original_currency: str = "THB"
    original_amount: float = 0
    exchange_rate: float = 1
    vat_percent: float = 0
    shipping_cost: float = 0
    fuel_cost: float = 0
    labor_cost: float = 0
    utility_cost: float = 0
    distance_meter: float = 0
    distance_cost: float = 0
    supplier_fee: float = 0
    discount: float = 0
    effective_at: datetime | None = None
    expire_at: datetime | None = None
    note: str = ""


class PriceRecordUpdateIn(BaseModel):
    source_type: str | None = None
    status: str | None = None
    delivery_mode: str | None = None
    area_scope: str | None = None
    price_dimension: str | None = None
    quantity_min: int | None = None
    quantity_max: int | None = None
    original_currency: str | None = None
    original_amount: float | None = None
    exchange_rate: float | None = None
    vat_percent: float | None = None
    shipping_cost: float | None = None
    fuel_cost: float | None = None
    labor_cost: float | None = None
    utility_cost: float | None = None
    distance_meter: float | None = None
    distance_cost: float | None = None
    supplier_fee: float | None = None
    discount: float | None = None
    effective_at: datetime | None = None
    expire_at: datetime | None = None
    note: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV, Role.ADMIN]))],
)
async def list_price_records(
    product_id: str | None = Query(None),
    supplier_id: str | None = Query(None),
    status: str | None = Query(None),
    include_archived: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    stmt = select(PriceRecord)
    count_stmt = select(func.count()).select_from(PriceRecord)

    filters = []
    if product_id:
        filters.append(PriceRecord.product_id == product_id)
    if supplier_id:
        filters.append(PriceRecord.supplier_id == supplier_id)
    if status:
        filters.append(PriceRecord.status == validate_price_status(status))
    if not include_archived:
        filters.append(PriceRecord.archived_at.is_(None))

    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(
            stmt.order_by(PriceRecord.updated_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    # Batch-load product and supplier names for the response
    product_ids = {r.product_id for r in rows}
    supplier_ids = {r.supplier_id for r in rows}
    products_map: dict[str, Product] = {}
    suppliers_map: dict[str, Supplier] = {}
    if product_ids:
        p_rows = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
        products_map = {p.id: p for p in p_rows}
    if supplier_ids:
        s_rows = (await db.execute(select(Supplier).where(Supplier.id.in_(supplier_ids)))).scalars().all()
        suppliers_map = {s.id: s for s in s_rows}

    items = []
    for r in rows:
        rec = serialize_price_record(r)
        product = products_map.get(r.product_id)
        supplier = suppliers_map.get(r.supplier_id)
        rec["product_sku"] = product.sku if product else ""
        rec["product_name_th"] = product.name_th if product else ""
        rec["supplier_name"] = supplier.name if supplier else ""
        rec["note"] = r.note or ""
        rec["created_at"] = serialize_utc_datetime(r.created_at)
        rec["updated_at"] = serialize_utc_datetime(r.updated_at)
        items.append(rec)

    return {"items": items, "total": total}


@router.post(
    "",
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV, Role.ADMIN]))],
)
async def create_price_record(
    body: PriceRecordCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    branch = await ensure_default_branch(db)
    effective_at = normalize_utc_datetime(body.effective_at, field_name="effective_at") or _utc_now_naive()
    expire_at = normalize_utc_datetime(body.expire_at, field_name="expire_at")

    # Validate all references and business rules
    await validate_price_record_payload(
        db,
        product_id=body.product_id,
        supplier_id=body.supplier_id,
        branch_id=branch.id,
        status=body.status,
        delivery_mode=body.delivery_mode,
        area_scope=body.area_scope,
        price_dimension=body.price_dimension,
        quantity_min=body.quantity_min,
        quantity_max=body.quantity_max,
        original_currency=body.original_currency,
        original_amount=body.original_amount,
        exchange_rate=body.exchange_rate,
        vat_percent=body.vat_percent,
        effective_at=effective_at,
        expire_at=expire_at,
    )

    # Compute totals
    comp = compute_price_record_totals(
        original_currency=body.original_currency,
        original_amount=body.original_amount,
        exchange_rate=body.exchange_rate,
        vat_percent=body.vat_percent,
        shipping_cost=body.shipping_cost,
        fuel_cost=body.fuel_cost,
        labor_cost=body.labor_cost,
        utility_cost=body.utility_cost,
        distance_meter=body.distance_meter,
        distance_cost=body.distance_cost,
        supplier_fee=body.supplier_fee,
        discount=body.discount,
    )

    # Resolve exchange rate snapshot for non-THB
    snapshot = await resolve_exchange_rate_snapshot(
        db,
        original_currency=body.original_currency,
        exchange_rate=body.exchange_rate,
        snapshot_at=None,
        source_name="manual",
        actor_id=user.id,
    )

    now = _utc_now_naive()
    record = PriceRecord(
        product_id=body.product_id,
        supplier_id=body.supplier_id,
        branch_id=branch.id,
        source_type=validate_price_source_type(body.source_type),
        status=validate_price_status(body.status),
        delivery_mode=validate_delivery_mode(body.delivery_mode),
        area_scope=validate_area_scope(body.area_scope),
        price_dimension=validate_price_dimension(body.price_dimension),
        quantity_min=body.quantity_min,
        quantity_max=body.quantity_max,
        original_currency=comp.normalized_money.original_currency,
        original_amount=comp.normalized_money.original_amount,
        normalized_currency=comp.normalized_money.normalized_currency,
        normalized_amount=comp.normalized_money.normalized_amount,
        exchange_rate=comp.normalized_money.exchange_rate,
        exchange_rate_source="manual",
        exchange_rate_snapshot_id=snapshot.id if snapshot else None,
        exchange_rate_snapshot_at=now,
        base_price=comp.base_price,
        vat_percent=comp.vat_percent,
        vat_amount=comp.vat_amount,
        shipping_cost=comp.shipping_cost,
        fuel_cost=comp.fuel_cost,
        labor_cost=comp.labor_cost,
        utility_cost=comp.utility_cost,
        distance_meter=comp.distance_meter,
        distance_cost=comp.distance_cost,
        supplier_fee=comp.supplier_fee,
        discount=comp.discount,
        final_total_cost=comp.final_total_cost,
        verification_required=False,
        effective_at=effective_at,
        expire_at=expire_at,
        note=body.note or "",
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.flush()

    # Sync search projection
    await sync_price_search_projections_for_price_records(db, price_record_ids=[record.id])

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="price_record.create",
        entity="price_record",
        entity_id=record.id,
        success=True,
        message=f"Created price record for product {record.product_id}",
    )
    await db.commit()

    result = serialize_price_record(record)
    result["note"] = record.note or ""
    result["created_at"] = serialize_utc_datetime(record.created_at)
    result["updated_at"] = serialize_utc_datetime(record.updated_at)
    return result


@router.put(
    "/{record_id}",
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV, Role.ADMIN]))],
)
async def update_price_record(
    record_id: str,
    body: PriceRecordUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    record = await db.scalar(select(PriceRecord).where(PriceRecord.id == record_id, PriceRecord.archived_at.is_(None)))
    if not record:
        raise HTTPException(status_code=404, detail="price_record_not_found")

    branch = await ensure_default_branch(db)

    # Merge updates onto current values
    source_type = body.source_type if body.source_type is not None else record.source_type.value if isinstance(record.source_type, PriceSourceType) else record.source_type
    status = body.status if body.status is not None else record.status.value if isinstance(record.status, PriceRecordStatus) else record.status
    delivery_mode = body.delivery_mode if body.delivery_mode is not None else record.delivery_mode
    area_scope = body.area_scope if body.area_scope is not None else record.area_scope
    price_dimension = body.price_dimension if body.price_dimension is not None else record.price_dimension
    quantity_min = body.quantity_min if body.quantity_min is not None else record.quantity_min
    quantity_max = body.quantity_max if body.quantity_max is not None else record.quantity_max
    original_currency = body.original_currency if body.original_currency is not None else (record.original_currency.value if isinstance(record.original_currency, type(record.original_currency)) and hasattr(record.original_currency, "value") else str(record.original_currency))
    original_amount = body.original_amount if body.original_amount is not None else float(record.original_amount)
    exchange_rate = body.exchange_rate if body.exchange_rate is not None else float(record.exchange_rate)
    vat_percent = body.vat_percent if body.vat_percent is not None else float(record.vat_percent)
    shipping_cost = body.shipping_cost if body.shipping_cost is not None else float(record.shipping_cost)
    fuel_cost = body.fuel_cost if body.fuel_cost is not None else float(record.fuel_cost)
    labor_cost = body.labor_cost if body.labor_cost is not None else float(record.labor_cost)
    utility_cost = body.utility_cost if body.utility_cost is not None else float(record.utility_cost)
    distance_meter = body.distance_meter if body.distance_meter is not None else float(record.distance_meter)
    distance_cost = body.distance_cost if body.distance_cost is not None else float(record.distance_cost)
    supplier_fee = body.supplier_fee if body.supplier_fee is not None else float(record.supplier_fee)
    discount = body.discount if body.discount is not None else float(record.discount)
    effective_at_raw = body.effective_at if body.effective_at is not None else record.effective_at
    expire_at_raw = body.expire_at if body.expire_at is not None else record.expire_at
    effective_at = normalize_utc_datetime(effective_at_raw, field_name="effective_at") or _utc_now_naive()
    expire_at = normalize_utc_datetime(expire_at_raw, field_name="expire_at")

    await validate_price_record_payload(
        db,
        product_id=record.product_id,
        supplier_id=record.supplier_id,
        branch_id=branch.id,
        status=status,
        delivery_mode=delivery_mode,
        area_scope=area_scope,
        price_dimension=price_dimension,
        quantity_min=quantity_min,
        quantity_max=quantity_max,
        original_currency=original_currency,
        original_amount=original_amount,
        exchange_rate=exchange_rate,
        vat_percent=vat_percent,
        effective_at=effective_at,
        expire_at=expire_at,
        exclude_price_record_id=record.id,
    )

    comp = compute_price_record_totals(
        original_currency=original_currency,
        original_amount=original_amount,
        exchange_rate=exchange_rate,
        vat_percent=vat_percent,
        shipping_cost=shipping_cost,
        fuel_cost=fuel_cost,
        labor_cost=labor_cost,
        utility_cost=utility_cost,
        distance_meter=distance_meter,
        distance_cost=distance_cost,
        supplier_fee=supplier_fee,
        discount=discount,
    )

    now = _utc_now_naive()
    record.source_type = validate_price_source_type(source_type)
    record.status = validate_price_status(status)
    record.delivery_mode = validate_delivery_mode(delivery_mode)
    record.area_scope = validate_area_scope(area_scope)
    record.price_dimension = validate_price_dimension(price_dimension)
    record.quantity_min = quantity_min
    record.quantity_max = quantity_max
    record.original_currency = comp.normalized_money.original_currency
    record.original_amount = float(comp.normalized_money.original_amount)
    record.normalized_currency = comp.normalized_money.normalized_currency
    record.normalized_amount = float(comp.normalized_money.normalized_amount)
    record.exchange_rate = float(comp.normalized_money.exchange_rate)
    record.base_price = float(comp.base_price)
    record.vat_percent = float(comp.vat_percent)
    record.vat_amount = float(comp.vat_amount)
    record.shipping_cost = float(comp.shipping_cost)
    record.fuel_cost = float(comp.fuel_cost)
    record.labor_cost = float(comp.labor_cost)
    record.utility_cost = float(comp.utility_cost)
    record.distance_meter = float(comp.distance_meter)
    record.distance_cost = float(comp.distance_cost)
    record.supplier_fee = float(comp.supplier_fee)
    record.discount = float(comp.discount)
    record.final_total_cost = float(comp.final_total_cost)
    record.effective_at = effective_at
    record.expire_at = expire_at
    if body.note is not None:
        record.note = body.note
    record.updated_by = user.id
    record.updated_at = now

    await db.flush()
    await sync_price_search_projections_for_price_records(db, price_record_ids=[record.id])

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="price_record.update",
        entity="price_record",
        entity_id=record.id,
        success=True,
        message=f"Updated price record {record.id}",
    )
    await db.commit()

    result = serialize_price_record(record)
    result["note"] = record.note or ""
    result["created_at"] = serialize_utc_datetime(record.created_at)
    result["updated_at"] = serialize_utc_datetime(record.updated_at)
    return result


@router.delete(
    "/{record_id}",
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV, Role.ADMIN]))],
)
async def archive_price_record(
    record_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    record = await db.scalar(select(PriceRecord).where(PriceRecord.id == record_id, PriceRecord.archived_at.is_(None)))
    if not record:
        raise HTTPException(status_code=404, detail="price_record_not_found")

    record.archived_at = _utc_now_naive()
    record.updated_by = user.id
    record.updated_at = _utc_now_naive()
    await db.flush()

    await sync_price_search_projections_for_price_records(db, price_record_ids=[record.id])

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="price_record.archive",
        entity="price_record",
        entity_id=record.id,
        success=True,
        message=f"Archived price record {record.id}",
    )
    await db.commit()

    return {"status": "archived", "id": record_id}


@router.get(
    "/dropdown/products",
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV, Role.ADMIN]))],
)
async def dropdown_products(
    q: str = Query("", max_length=200),
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Return lightweight product list for dropdown selectors."""
    DELETED_PREFIX = "__DELETED__:"
    stmt = select(Product).where(
        Product.deleted_at.is_(None),
        Product.archived_at.is_(None),
        ~Product.notes.like(f"{DELETED_PREFIX}%"),
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            Product.sku.ilike(pattern)
            | Product.name_th.ilike(pattern)
            | Product.name_en.ilike(pattern)
        )
    stmt = stmt.order_by(Product.sku.asc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"id": p.id, "sku": p.sku, "name_th": p.name_th or "", "name_en": p.name_en or "", "unit": p.unit or ""}
        for p in rows
    ]


@router.get(
    "/dropdown/suppliers",
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV, Role.ADMIN]))],
)
async def dropdown_suppliers(
    q: str = Query("", max_length=200),
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    """Return lightweight supplier list for dropdown selectors."""
    stmt = select(Supplier).where(
        Supplier.deleted_at.is_(None),
        Supplier.archived_at.is_(None),
    )
    if q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(Supplier.name.ilike(pattern) | Supplier.code.ilike(pattern))
    stmt = stmt.order_by(Supplier.name.asc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"id": s.id, "code": s.code or "", "name": s.name} for s in rows]
