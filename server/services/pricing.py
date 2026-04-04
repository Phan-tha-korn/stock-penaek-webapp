from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import (
    AreaScope,
    CostFormula,
    CostFormulaVersion,
    CurrencyCode,
    DeliveryMode,
    ExchangeRateSnapshot,
    PriceDimension,
    PriceRecord,
    PriceRecordStatus,
    PriceSourceType,
    Product,
    Supplier,
    User,
)
from server.services.audit import write_audit_log
from server.services.notifications import publish_pricing_notification
from server.services.search import sync_price_search_projections_for_price_records
from server.services.snapshots import create_pricing_change_snapshot


ACTIVE_PRICE_STATUS = {PriceRecordStatus.ACTIVE}
EDITABLE_PRICE_STATUS = {PriceRecordStatus.DRAFT, PriceRecordStatus.PENDING_VERIFY, PriceRecordStatus.INACTIVE}
ALLOWED_DELIVERY_MODES = {item.value for item in DeliveryMode}
ALLOWED_AREA_SCOPES = {item.value for item in AreaScope}
ALLOWED_PRICE_DIMENSIONS = {item.value for item in PriceDimension}
TWO_CURRENCY_CODES = {CurrencyCode.THB.value, CurrencyCode.USD.value}
MONEY_QUANT = Decimal("0.000001")
RATE_QUANT = Decimal("0.00000001")
DISTANCE_QUANT = Decimal("0.001")
MAX_OPEN_QUANTITY = 2_147_483_647


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_utc_datetime(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def serialize_utc_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_utc_datetime(value, field_name="datetime")
    assert normalized is not None
    return normalized.replace(tzinfo=timezone.utc).isoformat()


@dataclass
class NormalizedMoney:
    original_currency: CurrencyCode
    original_amount: Decimal
    normalized_currency: CurrencyCode
    normalized_amount: Decimal
    exchange_rate: Decimal


@dataclass
class PriceComputation:
    normalized_money: NormalizedMoney
    base_price: Decimal
    vat_percent: Decimal
    vat_amount: Decimal
    shipping_cost: Decimal
    fuel_cost: Decimal
    labor_cost: Decimal
    utility_cost: Decimal
    distance_meter: Decimal
    distance_cost: Decimal
    supplier_fee: Decimal
    discount: Decimal
    final_total_cost: Decimal


def _to_decimal(value: Any, *, quant: Decimal = MONEY_QUANT) -> Decimal:
    decimal = Decimal(str(value or 0))
    return decimal.quantize(quant, rounding=ROUND_HALF_UP)


def validate_currency_code(currency: str) -> CurrencyCode:
    value = str(currency or "").upper()
    if value not in TWO_CURRENCY_CODES:
        raise HTTPException(status_code=400, detail="unsupported_currency")
    return CurrencyCode(value)


def validate_delivery_mode(value: str) -> str:
    normalized = str(value or DeliveryMode.STANDARD.value).strip().lower()
    if normalized not in ALLOWED_DELIVERY_MODES:
        raise HTTPException(status_code=400, detail="invalid_delivery_mode")
    return normalized


def validate_area_scope(value: str) -> str:
    normalized = str(value or AreaScope.GLOBAL.value).strip().lower()
    if normalized not in ALLOWED_AREA_SCOPES:
        raise HTTPException(status_code=400, detail="invalid_area_scope")
    return normalized


def validate_price_dimension(value: str) -> str:
    normalized = str(value or PriceDimension.REAL_TOTAL_COST.value).strip().lower()
    if normalized not in ALLOWED_PRICE_DIMENSIONS:
        raise HTTPException(status_code=400, detail="invalid_price_dimension")
    return normalized


def validate_quantity_range(quantity_min: int, quantity_max: int | None) -> tuple[int, int | None]:
    try:
        min_value = int(quantity_min)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_quantity_min") from exc
    max_value = None
    if quantity_max not in (None, ""):
        try:
            max_value = int(quantity_max)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid_quantity_max") from exc
    if min_value < 1:
        raise HTTPException(status_code=400, detail="invalid_quantity_min")
    if max_value is not None and max_value < min_value:
        raise HTTPException(status_code=400, detail="invalid_quantity_range")
    return min_value, max_value


def validate_price_status(value: str) -> PriceRecordStatus:
    try:
        return PriceRecordStatus(str(value or PriceRecordStatus.DRAFT.value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_price_status") from exc


def validate_price_source_type(value: str) -> PriceSourceType:
    try:
        return PriceSourceType(str(value or PriceSourceType.MANUAL_ENTRY.value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_price_source_type") from exc


def normalize_currency_amount(*, original_currency: str, original_amount: Any, exchange_rate: Any) -> NormalizedMoney:
    currency = validate_currency_code(original_currency)
    original = _to_decimal(original_amount)
    rate = _to_decimal(exchange_rate, quant=RATE_QUANT)
    if rate <= 0:
        raise HTTPException(status_code=400, detail="invalid_exchange_rate")

    if currency == CurrencyCode.THB:
        rate = Decimal("1").quantize(RATE_QUANT, rounding=ROUND_HALF_UP)
        normalized = original
    else:
        normalized = (original * rate).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    return NormalizedMoney(
        original_currency=currency,
        original_amount=original,
        normalized_currency=CurrencyCode.THB,
        normalized_amount=normalized,
        exchange_rate=rate,
    )


def calculate_vat_amount(base_price: Any, vat_percent: Any) -> Decimal:
    base = _to_decimal(base_price)
    vat = _to_decimal(vat_percent, quant=Decimal("0.01"))
    if vat < 0 or vat > Decimal("100"):
        raise HTTPException(status_code=400, detail="invalid_vat_percent")
    return (base * vat / Decimal("100")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def calculate_final_total_cost(
    *,
    base_price: Any,
    vat_percent: Any,
    shipping_cost: Any = 0,
    fuel_cost: Any = 0,
    labor_cost: Any = 0,
    utility_cost: Any = 0,
    distance_meter: Any = 0,
    distance_cost: Any = 0,
    supplier_fee: Any = 0,
    discount: Any = 0,
) -> PriceComputation:
    base = _to_decimal(base_price)
    vat_pct = _to_decimal(vat_percent, quant=Decimal("0.01"))
    vat_amount = calculate_vat_amount(base, vat_pct)
    shipping = _to_decimal(shipping_cost)
    fuel = _to_decimal(fuel_cost)
    labor = _to_decimal(labor_cost)
    utility = _to_decimal(utility_cost)
    meter = _to_decimal(distance_meter, quant=DISTANCE_QUANT)
    distance = _to_decimal(distance_cost)
    supplier_fee_dec = _to_decimal(supplier_fee)
    discount_dec = _to_decimal(discount)
    for field_name, field_value in {
        "shipping_cost": shipping,
        "fuel_cost": fuel,
        "labor_cost": labor,
        "utility_cost": utility,
        "distance_meter": meter,
        "distance_cost": distance,
        "supplier_fee": supplier_fee_dec,
        "discount": discount_dec,
    }.items():
        if field_value < 0:
            raise HTTPException(status_code=400, detail=f"invalid_{field_name}")

    total = (base + vat_amount + shipping + fuel + labor + utility + distance + supplier_fee_dec - discount_dec).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )
    if total < 0:
        raise HTTPException(status_code=400, detail="invalid_final_total_cost")

    return PriceComputation(
        normalized_money=NormalizedMoney(
            original_currency=CurrencyCode.THB,
            original_amount=base,
            normalized_currency=CurrencyCode.THB,
            normalized_amount=base,
            exchange_rate=Decimal("1").quantize(RATE_QUANT, rounding=ROUND_HALF_UP),
        ),
        base_price=base,
        vat_percent=vat_pct,
        vat_amount=vat_amount,
        shipping_cost=shipping,
        fuel_cost=fuel,
        labor_cost=labor,
        utility_cost=utility,
        distance_meter=meter,
        distance_cost=distance,
        supplier_fee=supplier_fee_dec,
        discount=discount_dec,
        final_total_cost=total,
    )


def compute_price_record_totals(
    *,
    original_currency: str,
    original_amount: Any,
    exchange_rate: Any,
    vat_percent: Any,
    shipping_cost: Any = 0,
    fuel_cost: Any = 0,
    labor_cost: Any = 0,
    utility_cost: Any = 0,
    distance_meter: Any = 0,
    distance_cost: Any = 0,
    supplier_fee: Any = 0,
    discount: Any = 0,
) -> PriceComputation:
    normalized_money = normalize_currency_amount(
        original_currency=original_currency,
        original_amount=original_amount,
        exchange_rate=exchange_rate,
    )
    total = calculate_final_total_cost(
        base_price=normalized_money.normalized_amount,
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
    total.normalized_money = normalized_money
    return total


def quantity_ranges_overlap(min_a: int, max_a: int | None, min_b: int, max_b: int | None) -> bool:
    upper_a = max_a if max_a is not None else MAX_OPEN_QUANTITY
    upper_b = max_b if max_b is not None else MAX_OPEN_QUANTITY
    return int(min_a) <= int(upper_b) and int(min_b) <= int(upper_a)


def time_ranges_overlap(start_a: datetime, end_a: datetime | None, start_b: datetime, end_b: datetime | None) -> bool:
    normalized_start_a = normalize_utc_datetime(start_a, field_name="effective_at")
    normalized_end_a = normalize_utc_datetime(end_a, field_name="expire_at")
    normalized_start_b = normalize_utc_datetime(start_b, field_name="effective_at")
    normalized_end_b = normalize_utc_datetime(end_b, field_name="expire_at")

    assert normalized_start_a is not None
    assert normalized_start_b is not None
    upper_a = normalized_end_a or datetime.max
    upper_b = normalized_end_b or datetime.max
    return normalized_start_a < upper_b and normalized_start_b < upper_a


async def ensure_price_record_refs_exist(
    db: AsyncSession,
    *,
    product_id: str,
    supplier_id: str,
    branch_id: str,
    formula_id: str | None = None,
    formula_version_id: str | None = None,
) -> None:
    formula: CostFormula | None = None
    product = await db.scalar(select(Product).where(Product.id == product_id, Product.deleted_at.is_(None)))
    if not product:
        raise HTTPException(status_code=404, detail="product_not_found")
    supplier = await db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.deleted_at.is_(None)))
    if not supplier:
        raise HTTPException(status_code=404, detail="supplier_not_found")
    if product.branch_id and product.branch_id != branch_id:
        raise HTTPException(status_code=400, detail="product_branch_mismatch")
    if supplier.branch_id and supplier.branch_id != branch_id:
        raise HTTPException(status_code=400, detail="supplier_branch_mismatch")
    if formula_id:
        formula = await db.scalar(select(CostFormula).where(CostFormula.id == formula_id, CostFormula.archived_at.is_(None)))
        if not formula:
            raise HTTPException(status_code=404, detail="cost_formula_not_found")
    if formula_version_id:
        version = await db.scalar(
            select(CostFormulaVersion).where(CostFormulaVersion.id == formula_version_id, CostFormulaVersion.archived_at.is_(None))
        )
        if not version:
            raise HTTPException(status_code=404, detail="cost_formula_version_not_found")
        if formula_id and version.formula_id != formula_id:
            raise HTTPException(status_code=400, detail="cost_formula_version_mismatch")


async def resolve_exchange_rate_snapshot(
    db: AsyncSession,
    *,
    original_currency: str,
    exchange_rate: Any,
    snapshot_at: datetime | None,
    source_name: str,
    actor_id: str | None,
) -> ExchangeRateSnapshot | None:
    currency = validate_currency_code(original_currency)
    captured_at = normalize_utc_datetime(snapshot_at, field_name="exchange_rate_snapshot_at") or utc_now().replace(tzinfo=None)
    if currency == CurrencyCode.THB:
        return None

    rate = _to_decimal(exchange_rate, quant=RATE_QUANT)
    snapshot = ExchangeRateSnapshot(
        base_currency=currency,
        quote_currency=CurrencyCode.THB,
        rate_value=rate,
        source_name=str(source_name or "manual"),
        captured_at=captured_at,
        created_by=actor_id,
        created_at=utc_now().replace(tzinfo=None),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def find_conflicting_price_records(
    db: AsyncSession,
    *,
    product_id: str,
    supplier_id: str,
    branch_id: str,
    delivery_mode: str,
    area_scope: str,
    price_dimension: str,
    quantity_min: int,
    quantity_max: int | None,
    effective_at: datetime,
    expire_at: datetime | None,
    exclude_price_record_id: str | None = None,
) -> list[PriceRecord]:
    stmt: Select[tuple[PriceRecord]] = select(PriceRecord).where(
        PriceRecord.product_id == product_id,
        PriceRecord.supplier_id == supplier_id,
        PriceRecord.branch_id == branch_id,
        PriceRecord.delivery_mode == delivery_mode,
        PriceRecord.area_scope == area_scope,
        PriceRecord.price_dimension == price_dimension,
        PriceRecord.status == PriceRecordStatus.ACTIVE,
        PriceRecord.archived_at.is_(None),
    )
    if exclude_price_record_id:
        stmt = stmt.where(PriceRecord.id != exclude_price_record_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        row
        for row in rows
        if quantity_ranges_overlap(quantity_min, quantity_max, row.quantity_min, row.quantity_max)
        and time_ranges_overlap(effective_at, expire_at, row.effective_at, row.expire_at)
    ]


async def validate_price_record_payload(
    db: AsyncSession,
    *,
    product_id: str,
    supplier_id: str,
    branch_id: str,
    status: str,
    delivery_mode: str,
    area_scope: str,
    price_dimension: str,
    quantity_min: int,
    quantity_max: int | None,
    original_currency: str,
    original_amount: Any,
    exchange_rate: Any,
    vat_percent: Any,
    effective_at: datetime,
    expire_at: datetime | None,
    exclude_price_record_id: str | None = None,
    formula_id: str | None = None,
    formula_version_id: str | None = None,
) -> None:
    validate_quantity_range(quantity_min, quantity_max)
    validate_delivery_mode(delivery_mode)
    validate_area_scope(area_scope)
    validate_price_dimension(price_dimension)
    validate_currency_code(original_currency)
    await ensure_price_record_refs_exist(
        db,
        product_id=product_id,
        supplier_id=supplier_id,
        branch_id=branch_id,
        formula_id=formula_id,
        formula_version_id=formula_version_id,
    )
    if expire_at is not None and expire_at <= effective_at:
        raise HTTPException(status_code=400, detail="invalid_effective_range")
    if _to_decimal(original_amount) < 0:
        raise HTTPException(status_code=400, detail="invalid_original_amount")
    if validate_price_status(status) == PriceRecordStatus.ACTIVE:
        conflicts = await find_conflicting_price_records(
            db,
            product_id=product_id,
            supplier_id=supplier_id,
            branch_id=branch_id,
            delivery_mode=delivery_mode,
            area_scope=area_scope,
            price_dimension=price_dimension,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            effective_at=effective_at,
            expire_at=expire_at,
            exclude_price_record_id=exclude_price_record_id,
        )
        if conflicts:
            raise HTTPException(status_code=409, detail="active_price_conflict")


def serialize_price_record(record: PriceRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "product_id": record.product_id,
        "supplier_id": record.supplier_id,
        "branch_id": record.branch_id,
        "source_type": record.source_type.value,
        "status": record.status.value,
        "delivery_mode": record.delivery_mode,
        "area_scope": record.area_scope,
        "price_dimension": record.price_dimension,
        "quantity_min": record.quantity_min,
        "quantity_max": record.quantity_max,
        "original_currency": record.original_currency.value,
        "original_amount": str(record.original_amount),
        "normalized_currency": record.normalized_currency.value,
        "normalized_amount": str(record.normalized_amount),
        "normalized_amount_usage": "normalized base amount in THB before VAT and extra cost components",
        "exchange_rate": str(record.exchange_rate),
        "exchange_rate_source": record.exchange_rate_source,
        "exchange_rate_snapshot_id": record.exchange_rate_snapshot_id,
        "exchange_rate_snapshot_at": serialize_utc_datetime(record.exchange_rate_snapshot_at),
        "base_price": str(record.base_price),
        "vat_percent": str(record.vat_percent),
        "vat_amount": str(record.vat_amount),
        "shipping_cost": str(record.shipping_cost),
        "fuel_cost": str(record.fuel_cost),
        "labor_cost": str(record.labor_cost),
        "utility_cost": str(record.utility_cost),
        "distance_meter": str(record.distance_meter),
        "distance_cost": str(record.distance_cost),
        "supplier_fee": str(record.supplier_fee),
        "discount": str(record.discount),
        "final_total_cost": str(record.final_total_cost),
        "final_total_cost_usage": "main comparison field after VAT and additional cost components",
        "formula_id": record.formula_id,
        "formula_version_id": record.formula_version_id,
        "verification_required": record.verification_required,
        "effective_at": serialize_utc_datetime(record.effective_at),
        "expire_at": serialize_utc_datetime(record.expire_at),
        "replaced_by_price_record_id": record.replaced_by_price_record_id,
        "archived_at": serialize_utc_datetime(record.archived_at),
    }


async def create_price_record(
    db: AsyncSession,
    *,
    actor: User,
    request: Request | None,
    payload: dict[str, Any],
) -> PriceRecord:
    delivery_mode = validate_delivery_mode(str(payload.get("delivery_mode") or DeliveryMode.STANDARD.value))
    area_scope = validate_area_scope(str(payload.get("area_scope") or AreaScope.GLOBAL.value))
    price_dimension = validate_price_dimension(str(payload.get("price_dimension") or PriceDimension.REAL_TOTAL_COST.value))
    status = validate_price_status(str(payload.get("status") or PriceRecordStatus.DRAFT.value))
    quantity_min, quantity_max = validate_quantity_range(int(payload.get("quantity_min") or 0), payload.get("quantity_max"))
    effective_at = normalize_utc_datetime(payload.get("effective_at"), field_name="effective_at") or utc_now().replace(tzinfo=None)
    expire_at = normalize_utc_datetime(payload.get("expire_at"), field_name="expire_at")
    exclude_price_record_id = payload.get("exclude_price_record_id")

    await validate_price_record_payload(
        db,
        product_id=str(payload.get("product_id") or ""),
        supplier_id=str(payload.get("supplier_id") or ""),
        branch_id=str(payload.get("branch_id") or ""),
        status=status.value,
        delivery_mode=delivery_mode,
        area_scope=area_scope,
        price_dimension=price_dimension,
        quantity_min=quantity_min,
        quantity_max=quantity_max,
        original_currency=str(payload.get("original_currency") or CurrencyCode.THB.value),
        original_amount=payload.get("original_amount"),
        exchange_rate=payload.get("exchange_rate"),
        vat_percent=payload.get("vat_percent", 0),
        effective_at=effective_at,
        expire_at=expire_at,
        exclude_price_record_id=str(exclude_price_record_id) if exclude_price_record_id else None,
        formula_id=payload.get("formula_id"),
        formula_version_id=payload.get("formula_version_id"),
    )

    totals = compute_price_record_totals(
        original_currency=str(payload.get("original_currency") or CurrencyCode.THB.value),
        original_amount=payload.get("original_amount"),
        exchange_rate=payload.get("exchange_rate"),
        vat_percent=payload.get("vat_percent", 0),
        shipping_cost=payload.get("shipping_cost", 0),
        fuel_cost=payload.get("fuel_cost", 0),
        labor_cost=payload.get("labor_cost", 0),
        utility_cost=payload.get("utility_cost", 0),
        distance_meter=payload.get("distance_meter", 0),
        distance_cost=payload.get("distance_cost", 0),
        supplier_fee=payload.get("supplier_fee", 0),
        discount=payload.get("discount", 0),
    )
    snapshot = await resolve_exchange_rate_snapshot(
        db,
        original_currency=str(payload.get("original_currency") or CurrencyCode.THB.value),
        exchange_rate=totals.normalized_money.exchange_rate,
        snapshot_at=normalize_utc_datetime(payload.get("exchange_rate_snapshot_at"), field_name="exchange_rate_snapshot_at"),
        source_name=str(payload.get("exchange_rate_source") or "manual"),
        actor_id=actor.id,
    )

    record = PriceRecord(
        product_id=str(payload.get("product_id") or ""),
        supplier_id=str(payload.get("supplier_id") or ""),
        branch_id=str(payload.get("branch_id") or ""),
        source_type=validate_price_source_type(str(payload.get("source_type") or PriceSourceType.MANUAL_ENTRY.value)),
        status=status,
        delivery_mode=delivery_mode,
        area_scope=area_scope,
        price_dimension=price_dimension,
        quantity_min=quantity_min,
        quantity_max=quantity_max,
        original_currency=totals.normalized_money.original_currency,
        original_amount=totals.normalized_money.original_amount,
        normalized_currency=CurrencyCode.THB,
        normalized_amount=totals.normalized_money.normalized_amount,
        exchange_rate=totals.normalized_money.exchange_rate,
        exchange_rate_source=str(payload.get("exchange_rate_source") or "manual"),
        exchange_rate_snapshot_id=snapshot.id if snapshot else None,
        exchange_rate_snapshot_at=normalize_utc_datetime(payload.get("exchange_rate_snapshot_at"), field_name="exchange_rate_snapshot_at")
        or utc_now().replace(tzinfo=None),
        base_price=totals.normalized_money.normalized_amount,
        vat_percent=totals.vat_percent,
        vat_amount=totals.vat_amount,
        shipping_cost=totals.shipping_cost,
        fuel_cost=totals.fuel_cost,
        labor_cost=totals.labor_cost,
        utility_cost=totals.utility_cost,
        distance_meter=totals.distance_meter,
        distance_cost=totals.distance_cost,
        supplier_fee=totals.supplier_fee,
        discount=totals.discount,
        final_total_cost=totals.final_total_cost,
        formula_id=payload.get("formula_id"),
        formula_version_id=payload.get("formula_version_id"),
        verification_required=bool(payload.get("verification_required", False)),
        effective_at=effective_at,
        expire_at=expire_at,
        note=str(payload.get("note") or ""),
        created_by=actor.id,
        updated_by=actor.id,
        created_at=utc_now().replace(tzinfo=None),
        updated_at=utc_now().replace(tzinfo=None),
    )
    db.add(record)
    await db.flush()
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="PRICE_RECORD_CREATE",
        entity="price_record",
        entity_id=record.id,
        success=True,
        message="price_record_created",
        before=None,
        after=serialize_price_record(record),
        branch_id=record.branch_id,
        reason="price_record_created",
        diff_summary="price record create",
    )
    if record.verification_required or record.status == PriceRecordStatus.PENDING_VERIFY:
        await publish_pricing_notification(
            db,
            event_type="pricing.verification_required",
            price_record_id=record.id,
            branch_id=record.branch_id,
            product_id=record.product_id,
            supplier_id=record.supplier_id,
            triggered_by_user_id=actor.id,
            severity="high",
        )
    await sync_price_search_projections_for_price_records(db, price_record_ids=[record.id])
    return record


async def replace_price_record(
    db: AsyncSession,
    *,
    existing_record: PriceRecord,
    actor: User,
    request: Request | None,
    replacement_payload: dict[str, Any],
) -> PriceRecord:
    if existing_record.status not in ACTIVE_PRICE_STATUS | EDITABLE_PRICE_STATUS:
        raise HTTPException(status_code=400, detail="price_record_not_replaceable")
    before = serialize_price_record(existing_record)
    replacement_payload = {**replacement_payload}
    replacement_payload.setdefault("product_id", existing_record.product_id)
    replacement_payload.setdefault("supplier_id", existing_record.supplier_id)
    replacement_payload.setdefault("branch_id", existing_record.branch_id)
    replacement_payload.setdefault("source_type", existing_record.source_type.value)
    replacement_payload.setdefault("status", PriceRecordStatus.ACTIVE.value)
    replacement_payload.setdefault("delivery_mode", existing_record.delivery_mode)
    replacement_payload.setdefault("area_scope", existing_record.area_scope)
    replacement_payload.setdefault("price_dimension", existing_record.price_dimension)
    replacement_payload.setdefault("quantity_min", existing_record.quantity_min)
    replacement_payload.setdefault("quantity_max", existing_record.quantity_max)
    replacement_payload.setdefault("effective_at", utc_now())
    replacement_payload["exclude_price_record_id"] = existing_record.id
    replacement = await create_price_record(db, actor=actor, request=request, payload=replacement_payload)

    existing_record.status = PriceRecordStatus.REPLACED
    existing_record.expire_at = replacement.effective_at
    existing_record.replaced_by_price_record_id = replacement.id
    existing_record.updated_by = actor.id
    existing_record.updated_at = utc_now().replace(tzinfo=None)
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="PRICE_RECORD_REPLACE",
        entity="price_record",
        entity_id=existing_record.id,
        success=True,
        message="price_record_replaced",
        before=before,
        after=serialize_price_record(existing_record),
        branch_id=existing_record.branch_id,
        reason="price_record_replaced",
        diff_summary=f"replaced_by:{replacement.id}",
    )
    await publish_pricing_notification(
        db,
        event_type="pricing.price_record_replaced",
        price_record_id=existing_record.id,
        branch_id=existing_record.branch_id,
        product_id=existing_record.product_id,
        supplier_id=existing_record.supplier_id,
        triggered_by_user_id=actor.id,
        severity="critical",
        related_price_record_id=replacement.id,
    )
    await create_pricing_change_snapshot(
        db,
        record=existing_record,
        actor=actor,
        reason="price_record_replaced",
        related_price_record_id=replacement.id,
    )
    await sync_price_search_projections_for_price_records(
        db,
        price_record_ids=[existing_record.id, replacement.id],
    )
    return replacement


async def archive_price_record(
    db: AsyncSession,
    *,
    record: PriceRecord,
    actor: User,
    request: Request | None,
    reason: str,
) -> PriceRecord:
    before = serialize_price_record(record)
    record.status = PriceRecordStatus.ARCHIVED
    record.archived_at = utc_now().replace(tzinfo=None)
    record.updated_by = actor.id
    record.updated_at = utc_now().replace(tzinfo=None)
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="PRICE_RECORD_ARCHIVE",
        entity="price_record",
        entity_id=record.id,
        success=True,
        message=reason or "price_record_archived",
        before=before,
        after=serialize_price_record(record),
        branch_id=record.branch_id,
        reason=reason or "price_record_archived",
        diff_summary="price record archived",
    )
    await publish_pricing_notification(
        db,
        event_type="pricing.price_record_archived",
        price_record_id=record.id,
        branch_id=record.branch_id,
        product_id=record.product_id,
        supplier_id=record.supplier_id,
        triggered_by_user_id=actor.id,
        severity="high",
    )
    await create_pricing_change_snapshot(
        db,
        record=record,
        actor=actor,
        reason=reason or "price_record_archived",
    )
    await sync_price_search_projections_for_price_records(db, price_record_ids=[record.id])
    return record
