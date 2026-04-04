from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
import asyncio
import json
import logging
from typing import Any
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.config.settings import settings
from server.db.models import (
    CanonicalGroupMember,
    CanonicalProductGroup,
    CostFormula,
    CostFormulaVersion,
    PriceRecord,
    Product,
    ReportSnapshot,
    ReportSnapshotItem,
    ReportSnapshotItemType,
    ReportSnapshotLink,
    ReportSnapshotLinkRole,
    ReportSnapshotStatus,
    ReportSnapshotType,
    Supplier,
    User,
    VerificationDependencyWarning,
    VerificationRequest,
    VerificationRequestItem,
)

logger = logging.getLogger(__name__)


VERSIONED_ENTITY_TYPES = {
    "price_record",
    "cost_formula",
    "cost_formula_version",
    "canonical_product_group",
    "verification_request",
}


def _utc_now() -> datetime:
    return datetime.utcnow()


async def _run_in_consistent_boundary(db: AsyncSession, callback: Callable[[], Awaitable[Any]]) -> Any:
    if db.in_transaction():
        return await callback()
    async with db.begin():
        return await callback()


def _build_snapshot_code(prefix: str = "SNAP") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _safe_string(value: Any, *, max_length: int = 255) -> str:
    return str(value or "").strip()[:max_length]


def _validate_snapshot_payload(payload_json: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(payload_json, default=str, ensure_ascii=True).encode("utf-8")
    if len(encoded) > max(256, int(settings.snapshot_max_payload_bytes)):
        raise HTTPException(status_code=413, detail="report_snapshot_payload_too_large")
    return payload_json


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _datetime_token(value: datetime | None) -> str:
    return value.isoformat() if value else "none"


def _product_version_token(product: Product) -> str:
    return f"product:{product.id}:{_datetime_token(product.updated_at)}:{_datetime_token(product.deleted_at)}:{_datetime_token(product.archived_at)}"


def _supplier_version_token(supplier: Supplier) -> str:
    return f"supplier:{supplier.id}:{_datetime_token(supplier.updated_at)}:{str(bool(supplier.is_verified)).lower()}"


def _price_record_version_token(record: PriceRecord) -> str:
    return f"price_record:{record.id}:{record.status.value}:{_datetime_token(record.updated_at)}:{_datetime_token(record.effective_at)}"


def _formula_version_token(version: CostFormulaVersion) -> str:
    return f"cost_formula_version:{version.id}:v{version.version_no}"


def _formula_token(formula: CostFormula, version: CostFormulaVersion | None) -> str:
    version_bit = f"v{version.version_no}" if version is not None else "no-active-version"
    return f"cost_formula:{formula.id}:{version_bit}"


def _matching_group_version_token(group: CanonicalProductGroup) -> str:
    return f"canonical_product_group:{group.id}:v{group.version_no}"


def _verification_request_version_token(request_record: VerificationRequest) -> str:
    return f"verification_request:{request_record.id}:{request_record.workflow_status.value}:{_datetime_token(request_record.updated_at)}"


async def _load_product(db: AsyncSession, product_id: str) -> Product | None:
    return await db.scalar(select(Product).where(Product.id == product_id))


async def _load_supplier(db: AsyncSession, supplier_id: str) -> Supplier | None:
    return await db.scalar(select(Supplier).where(Supplier.id == supplier_id))


async def _load_price_record(db: AsyncSession, price_record_id: str) -> PriceRecord | None:
    return await db.scalar(select(PriceRecord).where(PriceRecord.id == price_record_id))


async def _load_formula_version(db: AsyncSession, formula_version_id: str) -> CostFormulaVersion | None:
    return await db.scalar(select(CostFormulaVersion).where(CostFormulaVersion.id == formula_version_id))


async def _load_formula(db: AsyncSession, formula_id: str) -> CostFormula | None:
    return await db.scalar(select(CostFormula).where(CostFormula.id == formula_id))


async def _load_group(db: AsyncSession, group_id: str) -> CanonicalProductGroup | None:
    return await db.scalar(select(CanonicalProductGroup).where(CanonicalProductGroup.id == group_id))


async def _active_group_for_product(db: AsyncSession, product_id: str) -> CanonicalProductGroup | None:
    membership = await db.scalar(
        select(CanonicalGroupMember).where(
            CanonicalGroupMember.product_id == product_id,
            CanonicalGroupMember.removed_at.is_(None),
            CanonicalGroupMember.archived_at.is_(None),
        )
    )
    if membership is None:
        return None
    return await _load_group(db, membership.group_id)


async def _matching_group_payload(db: AsyncSession, group: CanonicalProductGroup) -> dict[str, Any]:
    memberships = (
        await db.execute(
            select(CanonicalGroupMember).where(
                CanonicalGroupMember.group_id == group.id,
                CanonicalGroupMember.removed_at.is_(None),
                CanonicalGroupMember.archived_at.is_(None),
            )
        )
    ).scalars().all()
    return {
        "group_id": group.id,
        "code": group.code,
        "display_name": group.display_name,
        "status": group.status.value,
        "lock_state": group.lock_state.value,
        "version_no": int(group.version_no),
        "members": [
            {
                "product_id": member.product_id,
                "is_primary": bool(member.is_primary),
                "assigned_at": member.assigned_at.isoformat() if member.assigned_at else None,
            }
            for member in memberships
        ],
    }


async def _source_snapshot_for_entity(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str | None,
) -> tuple[ReportSnapshotItemType | None, str | None, dict[str, Any] | None]:
    normalized = _safe_string(entity_type, max_length=64).lower()
    if not entity_id:
        return None, None, None
    if normalized == "price_record":
        record = await _load_price_record(db, entity_id)
        if record is None:
            return ReportSnapshotItemType.PRICE_RECORD, None, {"missing": True, "price_record_id": entity_id}
        return (
            ReportSnapshotItemType.PRICE_RECORD,
            _price_record_version_token(record),
            {
                "price_record_id": record.id,
                "product_id": record.product_id,
                "supplier_id": record.supplier_id,
                "branch_id": record.branch_id,
                "status": record.status.value,
                "quantity_min": int(record.quantity_min),
                "quantity_max": int(record.quantity_max) if record.quantity_max is not None else None,
                "normalized_currency": record.normalized_currency.value,
                "normalized_amount": float(record.normalized_amount),
                "vat_amount": float(record.vat_amount),
                "shipping_cost": float(record.shipping_cost),
                "fuel_cost": float(record.fuel_cost),
                "labor_cost": float(record.labor_cost),
                "utility_cost": float(record.utility_cost),
                "supplier_fee": float(record.supplier_fee),
                "discount": float(record.discount),
                "final_total_cost": float(record.final_total_cost),
                "effective_at": record.effective_at.isoformat() if record.effective_at else None,
                "expire_at": record.expire_at.isoformat() if record.expire_at else None,
                "formula_id": record.formula_id,
                "formula_version_id": record.formula_version_id,
            },
        )
    if normalized == "cost_formula_version":
        version = await _load_formula_version(db, entity_id)
        if version is None:
            return ReportSnapshotItemType.FORMULA_VERSION, None, {"missing": True, "formula_version_id": entity_id}
        return (
            ReportSnapshotItemType.FORMULA_VERSION,
            _formula_version_token(version),
            {
                "formula_version_id": version.id,
                "formula_id": version.formula_id,
                "version_no": int(version.version_no),
                "expression_text": version.expression_text,
                "variables_json": version.variables_json,
                "constants_json": version.constants_json,
                "dependency_keys_json": version.dependency_keys_json,
                "is_active_version": bool(version.is_active_version),
                "activated_at": version.activated_at.isoformat() if version.activated_at else None,
            },
        )
    if normalized == "cost_formula":
        formula = await _load_formula(db, entity_id)
        if formula is None:
            return ReportSnapshotItemType.FORMULA_VERSION, None, {"missing": True, "formula_id": entity_id}
        active_version = await _load_formula_version(db, formula.active_version_id) if formula.active_version_id else None
        return (
            ReportSnapshotItemType.FORMULA_VERSION,
            _formula_token(formula, active_version),
            {
                "formula_id": formula.id,
                "code": formula.code,
                "name": formula.name,
                "status": formula.status.value,
                "scope_type": formula.scope_type.value,
                "scope_ref_id": formula.scope_ref_id,
                "active_version_id": formula.active_version_id,
                "active_version_no": int(active_version.version_no) if active_version else None,
            },
        )
    if normalized == "canonical_product_group":
        group = await _load_group(db, entity_id)
        if group is None:
            return ReportSnapshotItemType.MATCHING_GROUP, None, {"missing": True, "group_id": entity_id}
        return (
            ReportSnapshotItemType.MATCHING_GROUP,
            _matching_group_version_token(group),
            await _matching_group_payload(db, group),
        )
    if normalized == "verification_request":
        request_record = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == entity_id))
        if request_record is None:
            return ReportSnapshotItemType.VERIFICATION_STATE, None, {"missing": True, "request_id": entity_id}
        return (
            ReportSnapshotItemType.VERIFICATION_STATE,
            _verification_request_version_token(request_record),
            {
                "request_id": request_record.id,
                "request_code": request_record.request_code,
                "workflow_status": request_record.workflow_status.value,
                "risk_level": request_record.risk_level.value,
                "risk_score": request_record.risk_score,
                "safety_status": request_record.safety_status.value,
                "subject_domain": request_record.subject_domain,
                "queue_key": request_record.queue_key,
                "branch_id": request_record.branch_id,
                "sla_deadline_at": request_record.sla_deadline_at.isoformat() if request_record.sla_deadline_at else None,
                "resolved_at": request_record.resolved_at.isoformat() if request_record.resolved_at else None,
            },
        )
    if normalized == "supplier":
        supplier = await _load_supplier(db, entity_id)
        if supplier is None:
            return ReportSnapshotItemType.SUPPLIER_STATE, None, {"missing": True, "supplier_id": entity_id}
        return (
            ReportSnapshotItemType.SUPPLIER_STATE,
            _supplier_version_token(supplier),
            {
                "supplier_id": supplier.id,
                "branch_id": supplier.branch_id,
                "code": supplier.code,
                "name": supplier.name,
                "status": supplier.status.value,
                "is_verified": bool(supplier.is_verified),
            },
        )
    if normalized == "product":
        product = await _load_product(db, entity_id)
        if product is None:
            return ReportSnapshotItemType.PRODUCT_STATE, None, {"missing": True, "product_id": entity_id}
        return (
            ReportSnapshotItemType.PRODUCT_STATE,
            _product_version_token(product),
            {
                "product_id": product.id,
                "branch_id": product.branch_id,
                "sku": product.sku,
                "name_th": product.name_th,
                "name_en": product.name_en,
                "category": product.category,
                "status": product.status.value if product.status else None,
            },
        )
    return None, None, None


async def _insert_snapshot_item(
    db: AsyncSession,
    *,
    snapshot_id: str,
    item_type: ReportSnapshotItemType,
    source_entity_type: str,
    source_entity_id: str | None,
    source_version_token: str | None,
    payload_json: dict[str, Any],
) -> ReportSnapshotItem:
    row = ReportSnapshotItem(
        snapshot_id=snapshot_id,
        item_type=item_type,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        source_version_token=source_version_token,
        payload_json=_validate_snapshot_payload(payload_json),
        created_at=_utc_now(),
    )
    db.add(row)
    await db.flush()
    return row


async def _insert_link(
    db: AsyncSession,
    *,
    snapshot_id: str,
    linked_entity_type: str,
    linked_entity_id: str,
    link_role: ReportSnapshotLinkRole,
) -> None:
    db.add(
        ReportSnapshotLink(
            snapshot_id=snapshot_id,
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
            link_role=link_role,
            created_at=_utc_now(),
        )
    )
    await db.flush()


async def create_verification_approval_snapshot(
    db: AsyncSession,
    *,
    request_record: VerificationRequest,
    items: Sequence[VerificationRequestItem],
    dependency_warnings: Sequence[VerificationDependencyWarning],
    actor: User | None,
    apply_results: Sequence[dict[str, Any]] | None = None,
    reason: str,
) -> ReportSnapshot:
    async def _callback() -> ReportSnapshot:
        now = _utc_now()
        snapshot = ReportSnapshot(
            snapshot_code=_build_snapshot_code("VSNAP"),
            snapshot_type=ReportSnapshotType.DECISION_TRACE,
            scope_type="verification_request",
            scope_ref_id=request_record.id,
            branch_id=request_record.branch_id,
            as_of_at=now,
            generation_reason=_safe_string(reason, max_length=4000),
            generated_by_user_id=actor.id if actor else None,
            source_consistency_token=f"verification:{request_record.id}:{_datetime_token(now)}",
            status=ReportSnapshotStatus.COMPLETED,
            created_at=now,
        )
        db.add(snapshot)
        await db.flush()

        await _insert_link(
            db,
            snapshot_id=snapshot.id,
            linked_entity_type="verification_request",
            linked_entity_id=request_record.id,
            link_role=ReportSnapshotLinkRole.PRIMARY,
        )
        await _insert_snapshot_item(
            db,
            snapshot_id=snapshot.id,
            item_type=ReportSnapshotItemType.VERIFICATION_STATE,
            source_entity_type="verification_request",
            source_entity_id=request_record.id,
            source_version_token=_verification_request_version_token(request_record),
            payload_json={
                "request_id": request_record.id,
                "request_code": request_record.request_code,
                "workflow_status": request_record.workflow_status.value,
                "risk_level": request_record.risk_level.value,
                "risk_score": request_record.risk_score,
                "safety_status": request_record.safety_status.value,
                "subject_domain": request_record.subject_domain,
                "queue_key": request_record.queue_key,
                "branch_id": request_record.branch_id,
                "resolved_at": request_record.resolved_at.isoformat() if request_record.resolved_at else None,
                "apply_results": list(apply_results or []),
            },
        )

        seen_sources: set[tuple[str, str]] = set()
        for item in items:
            item_payload = {
                "request_item_id": item.id,
                "sequence_no": item.sequence_no,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "subject_key": item.subject_key,
                "change_type": item.change_type,
                "handler_key": item.handler_key,
                "approval_strategy": item.approval_strategy.value,
                "risk_level": item.risk_level.value,
                "safety_status": item.safety_status.value,
                "diff_summary": item.diff_summary,
                "before_json": item.before_json,
                "proposed_after_json": item.proposed_after_json,
            }
            source_item_type, derived_version_token, source_payload = await _source_snapshot_for_entity(
                db,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
            )
            version_token = item.entity_version_token or derived_version_token
            if item.entity_id and item.entity_type in VERSIONED_ENTITY_TYPES and not version_token:
                raise HTTPException(status_code=409, detail="snapshot_version_token_required")
            await _insert_snapshot_item(
                db,
                snapshot_id=snapshot.id,
                item_type=ReportSnapshotItemType.REQUEST_ITEM,
                source_entity_type=item.entity_type,
                source_entity_id=item.entity_id,
                source_version_token=version_token,
                payload_json=item_payload,
            )
            if item.entity_id:
                await _insert_link(
                    db,
                    snapshot_id=snapshot.id,
                    linked_entity_type=item.entity_type,
                    linked_entity_id=item.entity_id,
                    link_role=ReportSnapshotLinkRole.RELATED,
                )
            if source_item_type is not None and item.entity_id and (item.entity_type, item.entity_id) not in seen_sources:
                await _insert_snapshot_item(
                    db,
                    snapshot_id=snapshot.id,
                    item_type=source_item_type,
                    source_entity_type=item.entity_type,
                    source_entity_id=item.entity_id,
                    source_version_token=version_token or derived_version_token,
                    payload_json=source_payload or {},
                )
                seen_sources.add((item.entity_type, item.entity_id))

        for warning in dependency_warnings:
            await _insert_snapshot_item(
                db,
                snapshot_id=snapshot.id,
                item_type=ReportSnapshotItemType.DEPENDENCY_WARNING,
                source_entity_type=warning.dependency_type,
                source_entity_id=warning.dependency_entity_id,
                source_version_token=None,
                payload_json={
                    "request_item_id": warning.request_item_id,
                    "dependency_type": warning.dependency_type,
                    "dependency_entity_type": warning.dependency_entity_type,
                    "dependency_entity_id": warning.dependency_entity_id,
                    "safety_status": warning.safety_status.value,
                    "message": warning.message,
                    "detail_json": warning.detail_json,
                },
            )
            if warning.dependency_entity_id and warning.dependency_entity_type:
                await _insert_link(
                    db,
                    snapshot_id=snapshot.id,
                    linked_entity_type=warning.dependency_entity_type,
                    linked_entity_id=warning.dependency_entity_id,
                    link_role=ReportSnapshotLinkRole.DEPENDENCY,
                )
        logger.info("report_snapshot_created:%s:%s", snapshot.snapshot_type.value, snapshot.id)
        return snapshot

    try:
        return await _run_in_consistent_boundary(db, _callback)
    except Exception:
        logger.exception("report_snapshot_create_failed:verification:%s", request_record.id)
        raise


async def create_pricing_change_snapshot(
    db: AsyncSession,
    *,
    record: PriceRecord,
    actor: User | None,
    reason: str,
    related_price_record_id: str | None = None,
) -> ReportSnapshot:
    async def _callback() -> ReportSnapshot:
        now = _utc_now()
        snapshot = ReportSnapshot(
            snapshot_code=_build_snapshot_code("PSNAP"),
            snapshot_type=ReportSnapshotType.DECISION_TRACE,
            scope_type="price_record",
            scope_ref_id=record.id,
            branch_id=record.branch_id,
            as_of_at=now,
            generation_reason=_safe_string(reason, max_length=4000),
            generated_by_user_id=actor.id if actor else None,
            source_consistency_token=f"pricing:{record.id}:{_datetime_token(now)}",
            status=ReportSnapshotStatus.COMPLETED,
            created_at=now,
        )
        db.add(snapshot)
        await db.flush()

        await _insert_link(
            db,
            snapshot_id=snapshot.id,
            linked_entity_type="price_record",
            linked_entity_id=record.id,
            link_role=ReportSnapshotLinkRole.PRIMARY,
        )
        source_item_type, source_version_token, source_payload = await _source_snapshot_for_entity(
            db,
            entity_type="price_record",
            entity_id=record.id,
        )
        assert source_item_type is not None
        await _insert_snapshot_item(
            db,
            snapshot_id=snapshot.id,
            item_type=source_item_type,
            source_entity_type="price_record",
            source_entity_id=record.id,
            source_version_token=source_version_token,
            payload_json=source_payload or {},
        )

        if record.product_id:
            product_item_type, product_version_token, product_payload = await _source_snapshot_for_entity(
                db,
                entity_type="product",
                entity_id=record.product_id,
            )
            if product_item_type is not None:
                await _insert_link(
                    db,
                    snapshot_id=snapshot.id,
                    linked_entity_type="product",
                    linked_entity_id=record.product_id,
                    link_role=ReportSnapshotLinkRole.RELATED,
                )
                await _insert_snapshot_item(
                    db,
                    snapshot_id=snapshot.id,
                    item_type=product_item_type,
                    source_entity_type="product",
                    source_entity_id=record.product_id,
                    source_version_token=product_version_token,
                    payload_json=product_payload or {},
                )
            group = await _active_group_for_product(db, record.product_id)
            if group is not None:
                await _insert_link(
                    db,
                    snapshot_id=snapshot.id,
                    linked_entity_type="canonical_product_group",
                    linked_entity_id=group.id,
                    link_role=ReportSnapshotLinkRole.RELATED,
                )
                await _insert_snapshot_item(
                    db,
                    snapshot_id=snapshot.id,
                    item_type=ReportSnapshotItemType.MATCHING_GROUP,
                    source_entity_type="canonical_product_group",
                    source_entity_id=group.id,
                    source_version_token=_matching_group_version_token(group),
                    payload_json=await _matching_group_payload(db, group),
                )
        if record.supplier_id:
            supplier_item_type, supplier_version_token, supplier_payload = await _source_snapshot_for_entity(
                db,
                entity_type="supplier",
                entity_id=record.supplier_id,
            )
            if supplier_item_type is not None:
                await _insert_link(
                    db,
                    snapshot_id=snapshot.id,
                    linked_entity_type="supplier",
                    linked_entity_id=record.supplier_id,
                    link_role=ReportSnapshotLinkRole.RELATED,
                )
                await _insert_snapshot_item(
                    db,
                    snapshot_id=snapshot.id,
                    item_type=supplier_item_type,
                    source_entity_type="supplier",
                    source_entity_id=record.supplier_id,
                    source_version_token=supplier_version_token,
                    payload_json=supplier_payload or {},
                )
        if record.formula_version_id:
            formula_item_type, formula_version_token, formula_payload = await _source_snapshot_for_entity(
                db,
                entity_type="cost_formula_version",
                entity_id=record.formula_version_id,
            )
            if formula_item_type is not None:
                await _insert_link(
                    db,
                    snapshot_id=snapshot.id,
                    linked_entity_type="cost_formula_version",
                    linked_entity_id=record.formula_version_id,
                    link_role=ReportSnapshotLinkRole.RELATED,
                )
                await _insert_snapshot_item(
                    db,
                    snapshot_id=snapshot.id,
                    item_type=formula_item_type,
                    source_entity_type="cost_formula_version",
                    source_entity_id=record.formula_version_id,
                    source_version_token=formula_version_token,
                    payload_json=formula_payload or {},
                )
        if related_price_record_id:
            await _insert_link(
                db,
                snapshot_id=snapshot.id,
                linked_entity_type="price_record",
                linked_entity_id=related_price_record_id,
                link_role=ReportSnapshotLinkRole.RELATED,
            )
        logger.info("report_snapshot_created:%s:%s", snapshot.snapshot_type.value, snapshot.id)
        return snapshot

    try:
        return await _run_in_consistent_boundary(db, _callback)
    except Exception:
        logger.exception("report_snapshot_create_failed:pricing:%s", record.id)
        raise


async def get_report_snapshot_by_id(
    db: AsyncSession,
    *,
    snapshot_id: str,
    item_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    async def _query() -> dict[str, Any]:
        snapshot = await db.scalar(select(ReportSnapshot).where(ReportSnapshot.id == snapshot_id))
        if snapshot is None:
            raise HTTPException(status_code=404, detail="report_snapshot_not_found")
        item_stmt = select(ReportSnapshotItem).where(ReportSnapshotItem.snapshot_id == snapshot_id)
        if item_types:
            normalized_item_types = []
            for item_type in item_types:
                try:
                    normalized_item_types.append(ReportSnapshotItemType(str(item_type).strip().lower()))
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="invalid_report_snapshot_item_type") from exc
            item_stmt = item_stmt.where(ReportSnapshotItem.item_type.in_(normalized_item_types))
        items = (await db.execute(item_stmt.order_by(ReportSnapshotItem.created_at.asc(), ReportSnapshotItem.id.asc()))).scalars().all()
        links = (
            await db.execute(
                select(ReportSnapshotLink)
                .where(ReportSnapshotLink.snapshot_id == snapshot_id)
                .order_by(ReportSnapshotLink.created_at.asc(), ReportSnapshotLink.id.asc())
            )
        ).scalars().all()
        return {
            "id": snapshot.id,
            "snapshot_code": snapshot.snapshot_code,
            "snapshot_type": _enum_value(snapshot.snapshot_type),
            "scope_type": snapshot.scope_type,
            "scope_ref_id": snapshot.scope_ref_id,
            "branch_id": snapshot.branch_id,
            "as_of_at": snapshot.as_of_at.isoformat() if snapshot.as_of_at else None,
            "period_from": snapshot.period_from.isoformat() if snapshot.period_from else None,
            "period_to": snapshot.period_to.isoformat() if snapshot.period_to else None,
            "generation_reason": snapshot.generation_reason,
            "generated_by_user_id": snapshot.generated_by_user_id,
            "source_consistency_token": snapshot.source_consistency_token,
            "status": _enum_value(snapshot.status),
            "items": [
                {
                    "id": item.id,
                    "item_type": _enum_value(item.item_type),
                    "source_entity_type": item.source_entity_type,
                    "source_entity_id": item.source_entity_id,
                    "source_version_token": item.source_version_token,
                    "payload_json": item.payload_json,
                }
                for item in items
            ],
            "links": [
                {
                    "id": link.id,
                    "linked_entity_type": link.linked_entity_type,
                    "linked_entity_id": link.linked_entity_id,
                    "link_role": _enum_value(link.link_role),
                }
                for link in links
            ],
        }

    try:
        return await asyncio.wait_for(
            _query(),
            timeout=max(1, int(settings.report_query_timeout_seconds)),
        )
    except asyncio.TimeoutError as exc:
        logger.warning("report_snapshot_query_timeout:%s", snapshot_id)
        raise HTTPException(status_code=504, detail="report_snapshot_query_timeout") from exc
