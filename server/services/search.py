from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config.settings import settings
from server.db.models import (
    CanonicalGroupMember,
    CanonicalProductGroup,
    CatalogSearchDocument,
    CurrencyCode,
    MatchingGroupStatus,
    PriceRecord,
    PriceRecordStatus,
    PriceSearchProjection,
    Product,
    ProductAlias,
    ProductTagLink,
    Supplier,
    SupplierProductLink,
    SupplierReliabilityScore,
    Tag,
    VerificationAction,
    VerificationAssignment,
    VerificationDependencyWarning,
    VerificationQueueProjection,
    VerificationRequest,
    VerificationRequestItem,
    VerificationSafetyStatus,
    VerificationWorkflowStatus,
)


SEARCH_SELECTION_ACTIVE = "active"
SEARCH_SELECTION_LATEST = "latest"
SEARCH_SELECTION_HISTORICAL = "historical"
SEARCHABLE_SELECTIONS = {SEARCH_SELECTION_ACTIVE, SEARCH_SELECTION_LATEST, SEARCH_SELECTION_HISTORICAL}
ACTIVE_PRICE_COMPARE_STATUSES = {PriceRecordStatus.ACTIVE}
LATEST_PRICE_COMPARE_STATUSES = {
    PriceRecordStatus.ACTIVE,
    PriceRecordStatus.INACTIVE,
    PriceRecordStatus.REPLACED,
    PriceRecordStatus.EXPIRED,
    PriceRecordStatus.ARCHIVED,
}
HISTORICAL_PRICE_COMPARE_STATUSES = {
    PriceRecordStatus.ACTIVE,
    PriceRecordStatus.INACTIVE,
    PriceRecordStatus.REPLACED,
    PriceRecordStatus.EXPIRED,
    PriceRecordStatus.ARCHIVED,
}
DEFAULT_COMPARE_SORT = "final_total_cost_thb"
DEFAULT_HISTORY_SORT = "effective_at"
DEFAULT_QUEUE_SORT = "latest_action_at"


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _normalize_datetime(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_string(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_lower_query(value: str | None) -> str:
    return _normalize_string(value).lower()


def _normalize_limit(value: int | None, *, default: int = 50) -> int:
    try:
        limit = int(value or default)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid_search_limit") from exc
    return max(1, min(limit, max(1, int(settings.search_result_limit_max))))


def _normalize_quantity(value: int | None) -> int:
    try:
        quantity = int(value or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid_quantity") from exc
    if quantity < 1:
        raise HTTPException(status_code=400, detail="invalid_quantity")
    return quantity


def _normalize_selection(value: str | None) -> str:
    selection = _normalize_string(value or SEARCH_SELECTION_ACTIVE).lower()
    if selection not in SEARCHABLE_SELECTIONS:
        raise HTTPException(status_code=400, detail="invalid_price_selection_mode")
    return selection


def _normalize_sort_direction(value: str | None) -> str:
    direction = _normalize_string(value or "asc").lower()
    if direction not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="invalid_sort_direction")
    return direction


def _normalize_decimal(value: Any, *, field_name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}") from exc


def _normalize_status_values(values: Iterable[str] | None) -> list[str] | None:
    if values is None:
        return None
    normalized = [str(value).strip() for value in values if str(value or "").strip()]
    return normalized or None


async def _run_with_timeout(coro: Any, *, seconds: int, detail: str, log_key: str) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=max(1, int(seconds)))
    except asyncio.TimeoutError as exc:
        logger.warning("search_timeout:%s", log_key)
        raise HTTPException(status_code=504, detail=detail) from exc


def _join_tokens(*values: str) -> str:
    seen: list[str] = []
    for value in values:
        for token in [item for item in str(value or "").replace("|", " ").split() if item]:
            normalized = token.strip()
            if normalized and normalized not in seen:
                seen.append(normalized)
    return " ".join(seen)


def _product_lifecycle(product: Product) -> str:
    if product.deleted_at is not None:
        return "deleted"
    if product.archived_at is not None:
        return "archived"
    return "active"


async def _get_active_group_membership(
    db: AsyncSession,
    *,
    product_id: str,
) -> tuple[str | None, str]:
    membership = await db.scalar(
        select(CanonicalGroupMember)
        .where(
            CanonicalGroupMember.product_id == product_id,
            CanonicalGroupMember.removed_at.is_(None),
            CanonicalGroupMember.archived_at.is_(None),
        )
        .limit(1)
    )
    if membership is None:
        return None, ""
    group = await db.scalar(
        select(CanonicalProductGroup).where(
            CanonicalProductGroup.id == membership.group_id,
            CanonicalProductGroup.status == MatchingGroupStatus.ACTIVE,
            CanonicalProductGroup.archived_at.is_(None),
        )
    )
    if group is None:
        return None, ""
    return group.id, group.display_name


async def _get_product_alias_text(db: AsyncSession, *, product_id: str) -> str:
    aliases = (
        await db.execute(
            select(ProductAlias.alias)
            .where(ProductAlias.product_id == product_id, ProductAlias.deleted_at.is_(None))
            .order_by(ProductAlias.sort_order.asc(), ProductAlias.alias.asc())
        )
    ).scalars().all()
    return " | ".join(_normalize_string(alias) for alias in aliases if _normalize_string(alias))


async def _get_product_tag_text(db: AsyncSession, *, product_id: str) -> str:
    rows = (
        await db.execute(
            select(Tag.name)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .where(
                ProductTagLink.product_id == product_id,
                ProductTagLink.deleted_at.is_(None),
                Tag.archived_at.is_(None),
            )
            .order_by(Tag.name.asc())
        )
    ).scalars().all()
    return " | ".join(_normalize_string(name) for name in rows if _normalize_string(name))


async def _get_product_supplier_text(db: AsyncSession, *, product_id: str) -> str:
    rows = (
        await db.execute(
            select(Supplier.name)
            .join(SupplierProductLink, SupplierProductLink.supplier_id == Supplier.id)
            .where(
                SupplierProductLink.product_id == product_id,
                SupplierProductLink.archived_at.is_(None),
                Supplier.archived_at.is_(None),
                Supplier.deleted_at.is_(None),
            )
            .order_by(Supplier.name.asc())
        )
    ).scalars().all()
    return " | ".join(_normalize_string(name) for name in rows if _normalize_string(name))


async def _get_catalog_price_summary(db: AsyncSession, *, product_id: str) -> dict[str, Any]:
    now = _utc_now()
    active_rows = (
        await db.execute(
            select(PriceRecord)
            .where(
                PriceRecord.product_id == product_id,
                PriceRecord.status == PriceRecordStatus.ACTIVE,
                PriceRecord.archived_at.is_(None),
                PriceRecord.effective_at <= now,
                or_(PriceRecord.expire_at.is_(None), PriceRecord.expire_at > now),
            )
            .order_by(PriceRecord.effective_at.desc(), PriceRecord.final_total_cost.asc(), PriceRecord.id.asc())
        )
    ).scalars().all()
    latest = active_rows[0] if active_rows else None
    cheapest = min(active_rows, key=lambda row: (Decimal(str(row.final_total_cost or 0)), row.id)) if active_rows else None
    return {
        "active_price_count": len(active_rows),
        "latest_effective_at": latest.effective_at if latest else None,
        "latest_price_record_id": latest.id if latest else None,
        "latest_normalized_amount_thb": latest.normalized_amount if latest else None,
        "latest_final_total_cost_thb": latest.final_total_cost if latest else None,
        "cheapest_active_price_record_id": cheapest.id if cheapest else None,
        "cheapest_active_normalized_amount_thb": cheapest.normalized_amount if cheapest else None,
        "cheapest_active_final_total_cost_thb": cheapest.final_total_cost if cheapest else None,
    }


async def _get_verified_supplier_count(db: AsyncSession, *, product_id: str) -> int:
    count = await db.scalar(
        select(func.count(Supplier.id))
        .select_from(Supplier)
        .join(SupplierProductLink, SupplierProductLink.supplier_id == Supplier.id)
        .where(
            SupplierProductLink.product_id == product_id,
            SupplierProductLink.archived_at.is_(None),
            Supplier.archived_at.is_(None),
            Supplier.deleted_at.is_(None),
            Supplier.is_verified.is_(True),
        )
    )
    return int(count or 0)


async def sync_catalog_search_document_for_product(db: AsyncSession, *, product_id: str) -> CatalogSearchDocument | None:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    existing = await db.scalar(
        select(CatalogSearchDocument).where(CatalogSearchDocument.product_id == product_id)
    )
    if product is None:
        if existing is not None:
            await db.delete(existing)
        return None

    alias_text = await _get_product_alias_text(db, product_id=product.id)
    tag_text = await _get_product_tag_text(db, product_id=product.id)
    supplier_text = await _get_product_supplier_text(db, product_id=product.id)
    canonical_group_id, canonical_group_name = await _get_active_group_membership(db, product_id=product.id)
    price_summary = await _get_catalog_price_summary(db, product_id=product.id)
    verified_supplier_count = await _get_verified_supplier_count(db, product_id=product.id)
    search_text = _join_tokens(
        product.sku,
        product.name_th,
        product.name_en,
        product.category,
        alias_text,
        tag_text,
        supplier_text,
        canonical_group_name,
    )
    row = existing or CatalogSearchDocument(product_id=product.id)
    row.branch_id = product.branch_id
    row.canonical_group_id = canonical_group_id
    row.canonical_group_name = canonical_group_name
    row.sku = product.sku
    row.name_th = _normalize_string(product.name_th)
    row.name_en = _normalize_string(product.name_en)
    row.category_text = _normalize_string(product.category)
    row.alias_text = alias_text
    row.tag_text = tag_text
    row.supplier_text = supplier_text
    row.search_text = search_text
    row.lifecycle_status = _product_lifecycle(product)
    row.active_price_count = int(price_summary["active_price_count"])
    row.verified_supplier_count = verified_supplier_count
    row.latest_effective_at = price_summary["latest_effective_at"]
    row.latest_price_record_id = price_summary["latest_price_record_id"]
    row.latest_normalized_amount_thb = price_summary["latest_normalized_amount_thb"]
    row.latest_final_total_cost_thb = price_summary["latest_final_total_cost_thb"]
    row.cheapest_active_price_record_id = price_summary["cheapest_active_price_record_id"]
    row.cheapest_active_normalized_amount_thb = price_summary["cheapest_active_normalized_amount_thb"]
    row.cheapest_active_final_total_cost_thb = price_summary["cheapest_active_final_total_cost_thb"]
    row.updated_at = _utc_now()
    if existing is None:
        db.add(row)
    await db.flush()
    return row


async def sync_catalog_search_documents_for_products(
    db: AsyncSession,
    *,
    product_ids: Iterable[str],
) -> None:
    for product_id in {str(item).strip() for item in product_ids if str(item).strip()}:
        await sync_catalog_search_document_for_product(db, product_id=product_id)


async def sync_price_search_projection_for_price_record(
    db: AsyncSession,
    *,
    price_record_id: str,
) -> PriceSearchProjection | None:
    record = await db.scalar(select(PriceRecord).where(PriceRecord.id == price_record_id))
    existing = await db.scalar(
        select(PriceSearchProjection).where(PriceSearchProjection.price_record_id == price_record_id)
    )
    if record is None:
        if existing is not None:
            await db.delete(existing)
        return None

    product = await db.scalar(select(Product).where(Product.id == record.product_id))
    supplier = await db.scalar(select(Supplier).where(Supplier.id == record.supplier_id))
    score = await db.scalar(
        select(SupplierReliabilityScore).where(SupplierReliabilityScore.supplier_id == record.supplier_id)
    )
    canonical_group_id, canonical_group_name = await _get_active_group_membership(db, product_id=record.product_id)
    tag_text = await _get_product_tag_text(db, product_id=record.product_id)

    row = existing or PriceSearchProjection(price_record_id=record.id)
    row.product_id = record.product_id
    row.branch_id = record.branch_id
    row.supplier_id = record.supplier_id
    row.canonical_group_id = canonical_group_id
    row.canonical_group_name = canonical_group_name
    row.sku = product.sku if product else ""
    row.product_name_th = _normalize_string(product.name_th if product else "")
    row.product_name_en = _normalize_string(product.name_en if product else "")
    row.category_text = _normalize_string(product.category if product else "")
    row.tag_text = tag_text
    row.supplier_name = _normalize_string(supplier.name if supplier else "")
    row.supplier_is_verified = bool(supplier.is_verified) if supplier else False
    row.supplier_effective_score = score.effective_score if score else None
    row.status = record.status
    row.source_type = record.source_type
    row.delivery_mode = record.delivery_mode
    row.area_scope = record.area_scope
    row.price_dimension = record.price_dimension
    row.quantity_min = int(record.quantity_min)
    row.quantity_max = int(record.quantity_max) if record.quantity_max is not None else None
    row.original_currency = record.original_currency
    row.normalized_currency = CurrencyCode.THB
    row.normalized_amount_thb = record.normalized_amount
    row.vat_amount_thb = record.vat_amount
    row.shipping_cost_thb = record.shipping_cost
    row.fuel_cost_thb = record.fuel_cost
    row.labor_cost_thb = record.labor_cost
    row.utility_cost_thb = record.utility_cost
    row.supplier_fee_thb = record.supplier_fee
    row.discount_thb = record.discount
    row.final_total_cost_thb = record.final_total_cost
    row.verification_required = record.verification_required
    row.effective_at = record.effective_at
    row.expire_at = record.expire_at
    row.archived_at = record.archived_at
    row.updated_at = _utc_now()
    if existing is None:
        db.add(row)
    await db.flush()
    return row


async def sync_price_search_projections_for_price_records(
    db: AsyncSession,
    *,
    price_record_ids: Iterable[str],
) -> None:
    affected_products: set[str] = set()
    for price_record_id in {str(item).strip() for item in price_record_ids if str(item).strip()}:
        row = await sync_price_search_projection_for_price_record(db, price_record_id=price_record_id)
        if row is not None:
            affected_products.add(row.product_id)
    if affected_products:
        await sync_catalog_search_documents_for_products(db, product_ids=affected_products)


async def sync_price_search_projections_for_products(
    db: AsyncSession,
    *,
    product_ids: Iterable[str],
) -> None:
    resolved_product_ids = {str(item).strip() for item in product_ids if str(item).strip()}
    if not resolved_product_ids:
        return
    rows = (
        await db.execute(
            select(PriceRecord.id).where(PriceRecord.product_id.in_(resolved_product_ids))
        )
    ).scalars().all()
    await sync_price_search_projections_for_price_records(db, price_record_ids=rows)
    await sync_catalog_search_documents_for_products(db, product_ids=resolved_product_ids)


async def sync_search_projections_for_supplier(
    db: AsyncSession,
    *,
    supplier_id: str,
) -> None:
    price_record_ids = (
        await db.execute(select(PriceRecord.id).where(PriceRecord.supplier_id == supplier_id))
    ).scalars().all()
    product_ids = (
        await db.execute(
            select(SupplierProductLink.product_id).where(
                SupplierProductLink.supplier_id == supplier_id,
                SupplierProductLink.archived_at.is_(None),
            )
        )
    ).scalars().all()
    await sync_price_search_projections_for_price_records(db, price_record_ids=price_record_ids)
    await sync_catalog_search_documents_for_products(db, product_ids=product_ids)


async def sync_search_projections_for_matching_products(
    db: AsyncSession,
    *,
    product_ids: Iterable[str],
) -> None:
    await sync_price_search_projections_for_products(db, product_ids=product_ids)


async def sync_verification_queue_projection(
    db: AsyncSession,
    *,
    request_id: str,
) -> VerificationQueueProjection | None:
    request_record = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
    existing = await db.scalar(
        select(VerificationQueueProjection).where(VerificationQueueProjection.request_id == request_id)
    )
    if request_record is None:
        if existing is not None:
            await db.delete(existing)
        return None

    current_assignment = await db.scalar(
        select(VerificationAssignment).where(
            VerificationAssignment.request_id == request_id,
            VerificationAssignment.is_current.is_(True),
            VerificationAssignment.ended_at.is_(None),
        )
    )
    latest_action = await db.scalar(
        select(VerificationAction)
        .where(VerificationAction.request_id == request_id)
        .order_by(VerificationAction.created_at.desc(), VerificationAction.id.desc())
        .limit(1)
    )
    first_item = await db.scalar(
        select(VerificationRequestItem)
        .where(VerificationRequestItem.request_id == request_id)
        .order_by(VerificationRequestItem.sequence_no.asc())
        .limit(1)
    )
    dependency_rows = (
        await db.execute(
            select(VerificationDependencyWarning).where(VerificationDependencyWarning.request_id == request_id)
        )
    ).scalars().all()
    has_blocking = any(item.safety_status == VerificationSafetyStatus.BLOCKED for item in dependency_rows)
    is_overdue = (
        request_record.workflow_status == VerificationWorkflowStatus.PENDING
        and _utc_now() > request_record.sla_deadline_at
    )
    row = existing or VerificationQueueProjection(request_id=request_id)
    row.request_code = request_record.request_code
    row.branch_id = request_record.branch_id
    row.workflow_status = request_record.workflow_status
    row.risk_level = request_record.risk_level
    row.risk_score = request_record.risk_score
    row.subject_domain = request_record.subject_domain
    row.queue_key = request_record.queue_key
    row.safety_status = request_record.safety_status
    row.assignee_user_id = request_record.assignee_user_id
    row.assignee_role = current_assignment.assigned_role if current_assignment else None
    row.requested_by_user_id = request_record.requested_by_user_id
    row.item_count = int(request_record.item_count or 0)
    row.dependency_warning_count = int(request_record.dependency_warning_count or 0)
    row.current_escalation_level = int(request_record.current_escalation_level or 0)
    row.has_blocking_dependency = has_blocking
    row.is_overdue = is_overdue
    row.primary_entity_type = first_item.entity_type if first_item else None
    row.primary_entity_id = first_item.entity_id if first_item else None
    row.latest_action_type = latest_action.action_type.value if latest_action else None
    row.latest_action_at = latest_action.created_at if latest_action else request_record.last_action_at
    row.sla_deadline_at = request_record.sla_deadline_at
    row.created_at = request_record.created_at
    row.resolved_at = request_record.resolved_at or request_record.cancelled_at
    row.search_text = _join_tokens(
        request_record.request_code,
        request_record.subject_domain,
        request_record.queue_key,
        request_record.change_summary,
        first_item.entity_type if first_item else "",
        first_item.entity_id if first_item else "",
        row.assignee_role or "",
    )
    row.updated_at = _utc_now()
    if existing is None:
        db.add(row)
    await db.flush()
    return row


async def sync_verification_queue_projections(
    db: AsyncSession,
    *,
    request_ids: Iterable[str],
) -> None:
    for request_id in {str(item).strip() for item in request_ids if str(item).strip()}:
        await sync_verification_queue_projection(db, request_id=request_id)


def _apply_text_filter(stmt: Any, column: Any, query: str) -> Any:
    if not query:
        return stmt
    return stmt.where(func.lower(column).like(f"%{query}%"))


def _apply_catalog_filters(
    stmt: Any,
    *,
    branch_id: str | None,
    lifecycle_statuses: Sequence[str] | None,
    category: str | None,
    supplier_query: str | None,
    tag_query: str | None,
) -> Any:
    if branch_id:
        stmt = stmt.where(CatalogSearchDocument.branch_id == branch_id)
    if lifecycle_statuses:
        stmt = stmt.where(CatalogSearchDocument.lifecycle_status.in_(list(lifecycle_statuses)))
    if category:
        stmt = stmt.where(func.lower(CatalogSearchDocument.category_text) == _normalize_lower_query(category))
    if supplier_query:
        stmt = stmt.where(func.lower(CatalogSearchDocument.supplier_text).like(f"%{_normalize_lower_query(supplier_query)}%"))
    if tag_query:
        stmt = stmt.where(func.lower(CatalogSearchDocument.tag_text).like(f"%{_normalize_lower_query(tag_query)}%"))
    return stmt


async def quick_search_catalog(
    db: AsyncSession,
    *,
    query: str | None = None,
    branch_id: str | None = None,
    lifecycle_statuses: Sequence[str] | None = None,
    category: str | None = None,
    supplier_query: str | None = None,
    tag_query: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    async def _query() -> list[dict[str, Any]]:
        resolved_query = _normalize_lower_query(query)
        resolved_limit = _normalize_limit(limit, default=20)
        stmt = select(CatalogSearchDocument)
        stmt = _apply_catalog_filters(
            stmt,
            branch_id=branch_id,
            lifecycle_statuses=lifecycle_statuses,
            category=category,
            supplier_query=supplier_query,
            tag_query=tag_query,
        )
        if resolved_query:
            stmt = stmt.where(
                or_(
                    func.lower(CatalogSearchDocument.sku).like(f"%{resolved_query}%"),
                    func.lower(CatalogSearchDocument.name_th).like(f"%{resolved_query}%"),
                    func.lower(CatalogSearchDocument.name_en).like(f"%{resolved_query}%"),
                    func.lower(CatalogSearchDocument.alias_text).like(f"%{resolved_query}%"),
                    func.lower(CatalogSearchDocument.tag_text).like(f"%{resolved_query}%"),
                    func.lower(CatalogSearchDocument.search_text).like(f"%{resolved_query}%"),
                )
            )
        stmt = stmt.order_by(
            case((func.lower(CatalogSearchDocument.sku) == resolved_query, 0), else_=1),
            case((func.lower(CatalogSearchDocument.sku).like(f"{resolved_query}%"), 0), else_=1),
            case((CatalogSearchDocument.cheapest_active_final_total_cost_thb.is_(None), 1), else_=0),
            CatalogSearchDocument.cheapest_active_final_total_cost_thb.asc(),
            CatalogSearchDocument.updated_at.desc(),
        ).limit(resolved_limit)
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "product_id": row.product_id,
                "branch_id": row.branch_id,
                "canonical_group_id": row.canonical_group_id,
                "canonical_group_name": row.canonical_group_name,
                "sku": row.sku,
                "name_th": row.name_th,
                "name_en": row.name_en,
                "category_text": row.category_text,
                "alias_text": row.alias_text,
                "tag_text": row.tag_text,
                "supplier_text": row.supplier_text,
                "lifecycle_status": row.lifecycle_status,
                "active_price_count": row.active_price_count,
                "verified_supplier_count": row.verified_supplier_count,
                "latest_effective_at": row.latest_effective_at.isoformat() if row.latest_effective_at else None,
                "latest_final_total_cost_thb": float(row.latest_final_total_cost_thb) if row.latest_final_total_cost_thb is not None else None,
                "cheapest_active_final_total_cost_thb": float(row.cheapest_active_final_total_cost_thb) if row.cheapest_active_final_total_cost_thb is not None else None,
            }
            for row in rows
        ]

    return await _run_with_timeout(
        _query(),
        seconds=settings.search_query_timeout_seconds,
        detail="search_query_timeout",
        log_key="quick_search_catalog",
    )


async def _resolve_comparison_scope(
    db: AsyncSession,
    *,
    product_id: str | None,
    canonical_group_id: str | None,
) -> tuple[str | None, str | None]:
    if canonical_group_id:
        return None, canonical_group_id
    if not product_id:
        raise HTTPException(status_code=400, detail="comparison_scope_required")
    membership = await db.scalar(
        select(CanonicalGroupMember).where(
            CanonicalGroupMember.product_id == product_id,
            CanonicalGroupMember.removed_at.is_(None),
            CanonicalGroupMember.archived_at.is_(None),
        )
    )
    if membership is None:
        return product_id, None
    return None, membership.group_id


def _apply_price_projection_filters(
    stmt: Any,
    *,
    branch_id: str | None,
    supplier_ids: Sequence[str] | None,
    delivery_modes: Sequence[str] | None,
    area_scopes: Sequence[str] | None,
    lifecycle_statuses: Sequence[str] | None,
    original_currencies: Sequence[str] | None,
    price_dimensions: Sequence[str] | None,
    source_types: Sequence[str] | None,
    verified_supplier_only: bool,
    final_total_cost_min: Decimal | None,
    final_total_cost_max: Decimal | None,
    normalized_amount_min: Decimal | None,
    normalized_amount_max: Decimal | None,
    quantity: int | None,
) -> Any:
    if branch_id:
        stmt = stmt.where(PriceSearchProjection.branch_id == branch_id)
    if supplier_ids:
        stmt = stmt.where(PriceSearchProjection.supplier_id.in_(list(supplier_ids)))
    if delivery_modes:
        stmt = stmt.where(PriceSearchProjection.delivery_mode.in_(list(delivery_modes)))
    if area_scopes:
        stmt = stmt.where(PriceSearchProjection.area_scope.in_(list(area_scopes)))
    if lifecycle_statuses:
        stmt = stmt.where(PriceSearchProjection.status.in_(list(lifecycle_statuses)))
    if original_currencies:
        stmt = stmt.where(PriceSearchProjection.original_currency.in_(list(original_currencies)))
    if price_dimensions:
        stmt = stmt.where(PriceSearchProjection.price_dimension.in_(list(price_dimensions)))
    if source_types:
        stmt = stmt.where(PriceSearchProjection.source_type.in_(list(source_types)))
    if verified_supplier_only:
        stmt = stmt.where(PriceSearchProjection.supplier_is_verified.is_(True))
    if final_total_cost_min is not None:
        stmt = stmt.where(PriceSearchProjection.final_total_cost_thb >= final_total_cost_min)
    if final_total_cost_max is not None:
        stmt = stmt.where(PriceSearchProjection.final_total_cost_thb <= final_total_cost_max)
    if normalized_amount_min is not None:
        stmt = stmt.where(PriceSearchProjection.normalized_amount_thb >= normalized_amount_min)
    if normalized_amount_max is not None:
        stmt = stmt.where(PriceSearchProjection.normalized_amount_thb <= normalized_amount_max)
    if quantity is not None:
        stmt = stmt.where(
            PriceSearchProjection.quantity_min <= quantity,
            or_(PriceSearchProjection.quantity_max.is_(None), PriceSearchProjection.quantity_max >= quantity),
        )
    return stmt


def _apply_price_selection(stmt: Any, *, selection_mode: str, as_of: datetime, from_at: datetime | None, to_at: datetime | None) -> Any:
    if selection_mode == SEARCH_SELECTION_ACTIVE:
        return stmt.where(
            PriceSearchProjection.status == PriceRecordStatus.ACTIVE,
            PriceSearchProjection.archived_at.is_(None),
            PriceSearchProjection.effective_at <= as_of,
            or_(PriceSearchProjection.expire_at.is_(None), PriceSearchProjection.expire_at > as_of),
        )
    if selection_mode == SEARCH_SELECTION_LATEST:
        return stmt.where(
            PriceSearchProjection.status.in_(list(LATEST_PRICE_COMPARE_STATUSES)),
            PriceSearchProjection.effective_at <= as_of,
            or_(PriceSearchProjection.expire_at.is_(None), PriceSearchProjection.expire_at > as_of),
        )
    range_from = from_at or as_of
    range_to = to_at or as_of
    if range_from > range_to:
        raise HTTPException(status_code=400, detail="invalid_historical_range")
    return stmt.where(
        PriceSearchProjection.status.in_(list(HISTORICAL_PRICE_COMPARE_STATUSES)),
        PriceSearchProjection.effective_at <= range_to,
        or_(PriceSearchProjection.expire_at.is_(None), PriceSearchProjection.expire_at > range_from),
    )


def _apply_latest_partition(stmt: Any) -> Any:
    base = stmt.subquery()
    ranked = (
        select(
            *base.c,
            func.row_number()
            .over(
                partition_by=(
                    base.c.product_id,
                    base.c.supplier_id,
                    base.c.branch_id,
                    base.c.delivery_mode,
                    base.c.area_scope,
                    base.c.price_dimension,
                ),
                order_by=(base.c.effective_at.desc(), base.c.updated_at.desc(), base.c.price_record_id.desc()),
            )
            .label("search_rank"),
        )
    ).subquery()
    return select(ranked).where(ranked.c.search_rank == 1)


async def compare_prices(
    db: AsyncSession,
    *,
    product_id: str | None = None,
    canonical_group_id: str | None = None,
    branch_id: str | None = None,
    quantity: int | None = None,
    selection_mode: str | None = None,
    as_of: datetime | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    supplier_ids: Sequence[str] | None = None,
    delivery_modes: Sequence[str] | None = None,
    area_scopes: Sequence[str] | None = None,
    lifecycle_statuses: Sequence[str] | None = None,
    original_currencies: Sequence[str] | None = None,
    price_dimensions: Sequence[str] | None = None,
    source_types: Sequence[str] | None = None,
    verified_supplier_only: bool = False,
    final_total_cost_min: Any = None,
    final_total_cost_max: Any = None,
    normalized_amount_min: Any = None,
    normalized_amount_max: Any = None,
    sort_by: str = DEFAULT_COMPARE_SORT,
    sort_direction: str = "asc",
    limit: int | None = None,
) -> dict[str, Any]:
    async def _query() -> dict[str, Any]:
        selected_product_id, selected_group_id = await _resolve_comparison_scope(
            db,
            product_id=product_id,
            canonical_group_id=canonical_group_id,
        )
        resolved_selection = _normalize_selection(selection_mode)
        resolved_as_of = _normalize_datetime(as_of, field_name="as_of") or _utc_now()
        resolved_from = _normalize_datetime(from_at, field_name="from_at")
        resolved_to = _normalize_datetime(to_at, field_name="to_at")
        resolved_limit = _normalize_limit(limit, default=100)
        resolved_quantity = _normalize_quantity(quantity)

        stmt = select(PriceSearchProjection)
        if selected_group_id:
            stmt = stmt.where(PriceSearchProjection.canonical_group_id == selected_group_id)
        else:
            stmt = stmt.where(PriceSearchProjection.product_id == selected_product_id)
        stmt = _apply_price_projection_filters(
            stmt,
            branch_id=branch_id,
            supplier_ids=supplier_ids,
            delivery_modes=delivery_modes,
            area_scopes=area_scopes,
            lifecycle_statuses=_normalize_status_values(lifecycle_statuses),
            original_currencies=original_currencies,
            price_dimensions=price_dimensions,
            source_types=source_types,
            verified_supplier_only=verified_supplier_only,
            final_total_cost_min=_normalize_decimal(final_total_cost_min, field_name="final_total_cost_min"),
            final_total_cost_max=_normalize_decimal(final_total_cost_max, field_name="final_total_cost_max"),
            normalized_amount_min=_normalize_decimal(normalized_amount_min, field_name="normalized_amount_min"),
            normalized_amount_max=_normalize_decimal(normalized_amount_max, field_name="normalized_amount_max"),
            quantity=resolved_quantity,
        )
        stmt = _apply_price_selection(stmt, selection_mode=resolved_selection, as_of=resolved_as_of, from_at=resolved_from, to_at=resolved_to)

        if resolved_selection == SEARCH_SELECTION_LATEST:
            ranked_stmt = _apply_latest_partition(stmt)
            ranked = ranked_stmt.subquery()
            sort_col = getattr(ranked.c, sort_by, None)
            if sort_col is None:
                sort_col = ranked.c.final_total_cost_thb
            order_clause = sort_col.desc() if _normalize_sort_direction(sort_direction) == "desc" else sort_col.asc()
            stmt = select(ranked).order_by(order_clause, ranked.c.effective_at.desc(), ranked.c.price_record_id.asc()).limit(resolved_limit)
            rows = (await db.execute(stmt)).mappings().all()
            normalized_rows = [
                {
                    "price_record_id": row["price_record_id"],
                    "product_id": row["product_id"],
                    "supplier_id": row["supplier_id"],
                    "branch_id": row["branch_id"],
                    "canonical_group_id": row["canonical_group_id"],
                    "canonical_group_name": row["canonical_group_name"],
                    "sku": row["sku"],
                    "product_name_th": row["product_name_th"],
                    "product_name_en": row["product_name_en"],
                    "supplier_name": row["supplier_name"],
                    "supplier_is_verified": row["supplier_is_verified"],
                    "status": row["status"],
                    "source_type": row["source_type"],
                    "delivery_mode": row["delivery_mode"],
                    "area_scope": row["area_scope"],
                    "price_dimension": row["price_dimension"],
                    "quantity_min": row["quantity_min"],
                    "quantity_max": row["quantity_max"],
                    "original_currency": row["original_currency"],
                    "normalized_currency": row["normalized_currency"],
                    "normalized_amount_thb": float(row["normalized_amount_thb"]),
                    "vat_amount_thb": float(row["vat_amount_thb"]),
                    "shipping_cost_thb": float(row["shipping_cost_thb"]),
                    "fuel_cost_thb": float(row["fuel_cost_thb"]),
                    "labor_cost_thb": float(row["labor_cost_thb"]),
                    "utility_cost_thb": float(row["utility_cost_thb"]),
                    "supplier_fee_thb": float(row["supplier_fee_thb"]),
                    "discount_thb": float(row["discount_thb"]),
                    "final_total_cost_thb": float(row["final_total_cost_thb"]),
                    "effective_at": row["effective_at"].isoformat() if row["effective_at"] else None,
                    "expire_at": row["expire_at"].isoformat() if row["expire_at"] else None,
                    "selection_mode": resolved_selection,
                }
                for row in rows
            ]
        else:
            sort_col = getattr(PriceSearchProjection, sort_by, None)
            if sort_col is None:
                sort_col = PriceSearchProjection.final_total_cost_thb
            order_clause = sort_col.desc() if _normalize_sort_direction(sort_direction) == "desc" else sort_col.asc()
            stmt = stmt.order_by(order_clause, PriceSearchProjection.effective_at.desc(), PriceSearchProjection.price_record_id.asc()).limit(resolved_limit)
            normalized_rows = [
                {
                    "price_record_id": row.price_record_id,
                    "product_id": row.product_id,
                    "supplier_id": row.supplier_id,
                    "branch_id": row.branch_id,
                    "canonical_group_id": row.canonical_group_id,
                    "canonical_group_name": row.canonical_group_name,
                    "sku": row.sku,
                    "product_name_th": row.product_name_th,
                    "product_name_en": row.product_name_en,
                    "supplier_name": row.supplier_name,
                    "supplier_is_verified": row.supplier_is_verified,
                    "status": row.status.value,
                    "source_type": row.source_type.value,
                    "delivery_mode": row.delivery_mode,
                    "area_scope": row.area_scope,
                    "price_dimension": row.price_dimension,
                    "quantity_min": row.quantity_min,
                    "quantity_max": row.quantity_max,
                    "original_currency": row.original_currency.value,
                    "normalized_currency": row.normalized_currency.value,
                    "normalized_amount_thb": float(row.normalized_amount_thb),
                    "vat_amount_thb": float(row.vat_amount_thb),
                    "shipping_cost_thb": float(row.shipping_cost_thb),
                    "fuel_cost_thb": float(row.fuel_cost_thb),
                    "labor_cost_thb": float(row.labor_cost_thb),
                    "utility_cost_thb": float(row.utility_cost_thb),
                    "supplier_fee_thb": float(row.supplier_fee_thb),
                    "discount_thb": float(row.discount_thb),
                    "final_total_cost_thb": float(row.final_total_cost_thb),
                    "effective_at": row.effective_at.isoformat() if row.effective_at else None,
                    "expire_at": row.expire_at.isoformat() if row.expire_at else None,
                    "selection_mode": resolved_selection,
                }
                for row in (await db.execute(stmt)).scalars().all()
            ]

        return {
            "scope_product_id": selected_product_id,
            "scope_canonical_group_id": selected_group_id,
            "selection_mode": resolved_selection,
            "compare_currency": CurrencyCode.THB.value,
            "as_of": resolved_as_of.isoformat(),
            "row_count": len(normalized_rows),
            "rows": normalized_rows,
        }

    return await _run_with_timeout(
        _query(),
        seconds=settings.search_query_timeout_seconds,
        detail="comparison_query_timeout",
        log_key="compare_prices",
    )


async def search_price_history(
    db: AsyncSession,
    *,
    product_id: str | None = None,
    canonical_group_id: str | None = None,
    supplier_id: str | None = None,
    branch_id: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    lifecycle_statuses: Sequence[str] | None = None,
    sort_direction: str = "desc",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    async def _query() -> list[dict[str, Any]]:
        resolved_from = _normalize_datetime(from_at, field_name="from_at")
        resolved_to = _normalize_datetime(to_at, field_name="to_at")
        if resolved_from is None or resolved_to is None:
            raise HTTPException(status_code=400, detail="historical_range_required")
        if resolved_from > resolved_to:
            raise HTTPException(status_code=400, detail="invalid_historical_range")
        if (resolved_to - resolved_from).days > int(settings.historical_query_max_days):
            raise HTTPException(status_code=400, detail="historical_range_too_large")
        selected_product_id, selected_group_id = await _resolve_comparison_scope(
            db,
            product_id=product_id,
            canonical_group_id=canonical_group_id,
        )
        stmt = select(PriceSearchProjection)
        if selected_group_id:
            stmt = stmt.where(PriceSearchProjection.canonical_group_id == selected_group_id)
        else:
            stmt = stmt.where(PriceSearchProjection.product_id == selected_product_id)
        stmt = _apply_price_projection_filters(
            stmt,
            branch_id=branch_id,
            supplier_ids=[supplier_id] if supplier_id else None,
            delivery_modes=None,
            area_scopes=None,
            lifecycle_statuses=_normalize_status_values(lifecycle_statuses) or [item.value for item in HISTORICAL_PRICE_COMPARE_STATUSES],
            original_currencies=None,
            price_dimensions=None,
            source_types=None,
            verified_supplier_only=False,
            final_total_cost_min=None,
            final_total_cost_max=None,
            normalized_amount_min=None,
            normalized_amount_max=None,
            quantity=None,
        )
        stmt = _apply_price_selection(
            stmt,
            selection_mode=SEARCH_SELECTION_HISTORICAL,
            as_of=resolved_to,
            from_at=resolved_from,
            to_at=resolved_to,
        )
        order_clause = PriceSearchProjection.effective_at.desc() if _normalize_sort_direction(sort_direction) == "desc" else PriceSearchProjection.effective_at.asc()
        stmt = stmt.order_by(order_clause, PriceSearchProjection.price_record_id.asc()).limit(_normalize_limit(limit, default=100))
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "price_record_id": row.price_record_id,
                "product_id": row.product_id,
                "canonical_group_id": row.canonical_group_id,
                "supplier_id": row.supplier_id,
                "status": row.status.value,
                "effective_at": row.effective_at.isoformat() if row.effective_at else None,
                "expire_at": row.expire_at.isoformat() if row.expire_at else None,
                "normalized_amount_thb": float(row.normalized_amount_thb),
                "final_total_cost_thb": float(row.final_total_cost_thb),
            }
            for row in rows
        ]

    return await _run_with_timeout(
        _query(),
        seconds=settings.report_query_timeout_seconds,
        detail="historical_query_timeout",
        log_key="search_price_history",
    )


async def search_verification_queue(
    db: AsyncSession,
    *,
    query: str | None = None,
    branch_id: str | None = None,
    workflow_statuses: Sequence[str] | None = None,
    risk_levels: Sequence[str] | None = None,
    subject_domains: Sequence[str] | None = None,
    queue_keys: Sequence[str] | None = None,
    assignee_user_id: str | None = None,
    overdue_only: bool = False,
    has_blocking_dependency: bool | None = None,
    sort_by: str = DEFAULT_QUEUE_SORT,
    sort_direction: str = "desc",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    async def _query() -> list[dict[str, Any]]:
        resolved_query = _normalize_lower_query(query)
        stmt = select(VerificationQueueProjection)
        if branch_id:
            stmt = stmt.where(VerificationQueueProjection.branch_id == branch_id)
        if workflow_statuses:
            stmt = stmt.where(VerificationQueueProjection.workflow_status.in_(list(workflow_statuses)))
        if risk_levels:
            stmt = stmt.where(VerificationQueueProjection.risk_level.in_(list(risk_levels)))
        if subject_domains:
            stmt = stmt.where(VerificationQueueProjection.subject_domain.in_(list(subject_domains)))
        if queue_keys:
            stmt = stmt.where(VerificationQueueProjection.queue_key.in_(list(queue_keys)))
        if assignee_user_id:
            stmt = stmt.where(VerificationQueueProjection.assignee_user_id == assignee_user_id)
        if overdue_only:
            stmt = stmt.where(VerificationQueueProjection.is_overdue.is_(True))
        if has_blocking_dependency is not None:
            stmt = stmt.where(VerificationQueueProjection.has_blocking_dependency.is_(has_blocking_dependency))
        if resolved_query:
            stmt = stmt.where(
                or_(
                    func.lower(VerificationQueueProjection.request_code).like(f"%{resolved_query}%"),
                    func.lower(VerificationQueueProjection.search_text).like(f"%{resolved_query}%"),
                )
            )
        sort_col = getattr(VerificationQueueProjection, sort_by, None)
        if sort_col is None:
            sort_col = VerificationQueueProjection.latest_action_at
        order_clause = sort_col.desc() if _normalize_sort_direction(sort_direction) == "desc" else sort_col.asc()
        stmt = stmt.order_by(
            VerificationQueueProjection.is_overdue.desc(),
            VerificationQueueProjection.has_blocking_dependency.desc(),
            order_clause,
            VerificationQueueProjection.request_code.asc(),
        ).limit(_normalize_limit(limit, default=100))
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {
                "request_id": row.request_id,
                "request_code": row.request_code,
                "branch_id": row.branch_id,
                "workflow_status": row.workflow_status.value,
                "risk_level": row.risk_level.value,
                "risk_score": row.risk_score,
                "subject_domain": row.subject_domain,
                "queue_key": row.queue_key,
                "safety_status": row.safety_status.value,
                "assignee_user_id": row.assignee_user_id,
                "assignee_role": row.assignee_role,
                "item_count": row.item_count,
                "dependency_warning_count": row.dependency_warning_count,
                "current_escalation_level": row.current_escalation_level,
                "has_blocking_dependency": row.has_blocking_dependency,
                "is_overdue": row.is_overdue,
                "primary_entity_type": row.primary_entity_type,
                "primary_entity_id": row.primary_entity_id,
                "latest_action_type": row.latest_action_type,
                "latest_action_at": row.latest_action_at.isoformat() if row.latest_action_at else None,
                "sla_deadline_at": row.sla_deadline_at.isoformat() if row.sla_deadline_at else None,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            }
            for row in rows
        ]

    return await _run_with_timeout(
        _query(),
        seconds=settings.search_query_timeout_seconds,
        detail="verification_queue_query_timeout",
        log_key="search_verification_queue",
    )
