from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import orjson
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import (
    Product,
    Supplier,
    SupplierChangeProposal,
    SupplierContact,
    SupplierLink,
    SupplierPickupPoint,
    SupplierProductLink,
    SupplierProposalStatus,
    SupplierReliabilityBreakdown,
    SupplierReliabilityProfile,
    SupplierReliabilityScore,
    SupplierStatus,
)
from server.services.branches import ensure_default_branch
from server.services.notifications import publish_supplier_verification_notification
from server.services.catalog_foundation import normalize_supplier_key
from server.services.search import sync_search_projections_for_supplier


@dataclass
class SupplierReliabilityResult:
    overall_score: float
    auto_score: float
    effective_score: float
    breakdown: dict[str, float]


def normalize_supplier_name(name: str) -> str:
    return " ".join((name or "").strip().split())


def build_supplier_code() -> str:
    return f"SUP-{uuid.uuid4().hex[:8].upper()}"


def serialize_supplier_snapshot(supplier: Supplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "branch_id": supplier.branch_id,
        "code": supplier.code,
        "name": supplier.name,
        "normalized_name": supplier.normalized_name,
        "phone": supplier.phone,
        "line_id": supplier.line_id,
        "facebook_url": supplier.facebook_url,
        "website_url": supplier.website_url,
        "address": supplier.address,
        "pickup_notes": supplier.pickup_notes,
        "source_details": supplier.source_details,
        "purchase_history_notes": supplier.purchase_history_notes,
        "reliability_note": supplier.reliability_note,
        "status": supplier.status.value,
        "is_verified": supplier.is_verified,
        "archived_at": supplier.archived_at.isoformat() if supplier.archived_at else None,
        "deleted_at": supplier.deleted_at.isoformat() if supplier.deleted_at else None,
        "delete_reason": supplier.delete_reason,
    }


def apply_supplier_payload(supplier: Supplier, payload: dict[str, Any], *, actor_id: str | None = None) -> Supplier:
    name = normalize_supplier_name(str(payload.get("name") or supplier.name or ""))
    supplier.name = name
    supplier.normalized_name = normalize_supplier_key(name)
    supplier.phone = str(payload.get("phone") or "").strip()
    supplier.line_id = str(payload.get("line_id") or "").strip()
    supplier.facebook_url = str(payload.get("facebook_url") or "").strip()
    supplier.website_url = str(payload.get("website_url") or "").strip()
    supplier.address = str(payload.get("address") or "").strip()
    supplier.pickup_notes = str(payload.get("pickup_notes") or "").strip()
    supplier.source_details = str(payload.get("source_details") or "").strip()
    supplier.purchase_history_notes = str(payload.get("purchase_history_notes") or "").strip()
    supplier.reliability_note = str(payload.get("reliability_note") or "").strip()
    supplier.is_verified = bool(payload.get("is_verified", supplier.is_verified))
    status = str(payload.get("status") or supplier.status.value or SupplierStatus.ACTIVE.value).upper()
    supplier.status = SupplierStatus(status)
    supplier.branch_id = payload.get("branch_id") or supplier.branch_id
    supplier.updated_by = actor_id
    supplier.updated_at = datetime.utcnow()
    if supplier.status == SupplierStatus.ARCHIVED and not supplier.archived_at:
        supplier.archived_at = datetime.utcnow()
    if supplier.status != SupplierStatus.ARCHIVED:
        supplier.archived_at = None
    return supplier


async def replace_supplier_contacts(db: AsyncSession, supplier: Supplier, items: list[dict[str, Any]]) -> None:
    existing = (
        await db.execute(
            select(SupplierContact).where(SupplierContact.supplier_id == supplier.id, SupplierContact.archived_at.is_(None))
        )
    ).scalars().all()
    now = datetime.utcnow()
    for row in existing:
        row.archived_at = now

    for index, item in enumerate(items):
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        db.add(
            SupplierContact(
                supplier_id=supplier.id,
                contact_type=str(item.get("contact_type") or "other").strip() or "other",
                label=str(item.get("label") or "").strip(),
                value=value,
                is_primary=bool(item.get("is_primary", index == 0)),
                sort_order=index,
                created_at=now,
                updated_at=now,
            )
        )


async def replace_supplier_links(db: AsyncSession, supplier: Supplier, items: list[dict[str, Any]]) -> None:
    existing = (
        await db.execute(
            select(SupplierLink).where(SupplierLink.supplier_id == supplier.id, SupplierLink.archived_at.is_(None))
        )
    ).scalars().all()
    now = datetime.utcnow()
    for row in existing:
        row.archived_at = now

    for index, item in enumerate(items):
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        db.add(
            SupplierLink(
                supplier_id=supplier.id,
                link_type=str(item.get("link_type") or "other").strip() or "other",
                label=str(item.get("label") or "").strip(),
                url=url,
                is_primary=bool(item.get("is_primary", index == 0)),
                sort_order=index,
                created_at=now,
                updated_at=now,
            )
        )


async def replace_supplier_pickup_points(db: AsyncSession, supplier: Supplier, items: list[dict[str, Any]]) -> None:
    existing = (
        await db.execute(
            select(SupplierPickupPoint).where(
                SupplierPickupPoint.supplier_id == supplier.id,
                SupplierPickupPoint.archived_at.is_(None),
            )
        )
    ).scalars().all()
    now = datetime.utcnow()
    for row in existing:
        row.archived_at = now

    for index, item in enumerate(items):
        label = str(item.get("label") or "").strip()
        address = str(item.get("address") or "").strip()
        details = str(item.get("details") or "").strip()
        if not any([label, address, details]):
            continue
        db.add(
            SupplierPickupPoint(
                supplier_id=supplier.id,
                label=label,
                address=address,
                details=details,
                is_primary=bool(item.get("is_primary", index == 0)),
                created_at=now,
                updated_at=now,
            )
        )


async def get_or_create_supplier_by_name(
    db: AsyncSession,
    *,
    name: str,
    branch_id: str | None = None,
    actor_id: str | None = None,
) -> Supplier | None:
    cleaned_name = normalize_supplier_name(name)
    normalized = normalize_supplier_key(cleaned_name)
    if not normalized:
        return None

    supplier = await db.scalar(select(Supplier).where(Supplier.normalized_name == normalized))
    if supplier:
        if branch_id and not supplier.branch_id:
            supplier.branch_id = branch_id
        return supplier

    supplier = Supplier(
        branch_id=branch_id,
        code=build_supplier_code(),
        name=cleaned_name,
        normalized_name=normalized,
        status=SupplierStatus.ACTIVE,
        created_by=actor_id,
        updated_by=actor_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier)
    await db.flush()
    await sync_search_projections_for_supplier(db, supplier_id=supplier.id)
    return supplier


async def recalculate_supplier_reliability(db: AsyncSession, supplier: Supplier) -> SupplierReliabilityResult:
    product_count = int(
        await db.scalar(
            select(func.count()).select_from(SupplierProductLink).where(
                SupplierProductLink.supplier_id == supplier.id,
                SupplierProductLink.archived_at.is_(None),
            )
        )
        or 0
    )
    rejected_proposals = int(
        await db.scalar(
            select(func.count()).select_from(SupplierChangeProposal).where(
                SupplierChangeProposal.supplier_id == supplier.id,
                SupplierChangeProposal.status == SupplierProposalStatus.REJECTED,
            )
        )
        or 0
    )
    pickup_points = int(
        await db.scalar(
            select(func.count()).select_from(SupplierPickupPoint).where(
                SupplierPickupPoint.supplier_id == supplier.id,
                SupplierPickupPoint.archived_at.is_(None),
            )
        )
        or 0
    )

    completeness_fields = [
        supplier.phone,
        supplier.line_id,
        supplier.facebook_url,
        supplier.website_url,
        supplier.address,
        supplier.pickup_notes,
        supplier.source_details,
        supplier.purchase_history_notes,
    ]
    data_completeness = round((sum(1 for value in completeness_fields if str(value or "").strip()) / len(completeness_fields)) * 100, 2)
    price_competitiveness = 50.0
    purchase_frequency = float(min(100, product_count * 20))
    delivery_reliability = 75.0 if pickup_points or supplier.address.strip() else 50.0
    verification_confidence = 95.0 if supplier.is_verified else 40.0
    dispute_reject = float(max(0, 100 - (rejected_proposals * 20)))

    weights = {
        "price_competitiveness": 0.15,
        "purchase_frequency": 0.15,
        "delivery_reliability": 0.20,
        "data_completeness": 0.20,
        "verification_confidence": 0.20,
        "dispute_reject": 0.10,
    }
    breakdown = {
        "price_competitiveness": round(price_competitiveness, 2),
        "purchase_frequency": round(purchase_frequency, 2),
        "delivery_reliability": round(delivery_reliability, 2),
        "data_completeness": round(data_completeness, 2),
        "verification_confidence": round(verification_confidence, 2),
        "dispute_reject": round(dispute_reject, 2),
    }
    auto_score = round(sum(breakdown[key] * weight for key, weight in weights.items()), 2)

    profile = await db.scalar(select(SupplierReliabilityProfile).where(SupplierReliabilityProfile.supplier_id == supplier.id))
    if not profile:
        profile = await db.scalar(
            select(SupplierReliabilityProfile).where(
                SupplierReliabilityProfile.legacy_supplier_key == supplier.normalized_name
            )
        )
    if not profile:
        profile = SupplierReliabilityProfile(
            supplier_id=supplier.id,
            legacy_supplier_name=supplier.name,
            legacy_supplier_key=supplier.normalized_name,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(profile)
        await db.flush()

    profile.supplier_id = supplier.id
    profile.legacy_supplier_name = supplier.name
    profile.legacy_supplier_key = supplier.normalized_name
    profile.auto_score = auto_score
    profile.price_competitiveness_score = breakdown["price_competitiveness"]
    profile.purchase_frequency_score = breakdown["purchase_frequency"]
    profile.delivery_reliability_score = breakdown["delivery_reliability"]
    profile.data_completeness_score = breakdown["data_completeness"]
    profile.verification_confidence_score = breakdown["verification_confidence"]
    profile.dispute_reject_score = breakdown["dispute_reject"]
    effective_score = float(
        profile.owner_override_score
        if profile.owner_override_score is not None
        else profile.dev_override_score
        if profile.dev_override_score is not None
        else auto_score
    )
    profile.overall_score = effective_score
    profile.updated_at = datetime.utcnow()

    score = await db.scalar(select(SupplierReliabilityScore).where(SupplierReliabilityScore.supplier_id == supplier.id))
    if not score:
        score = SupplierReliabilityScore(supplier_id=supplier.id)
        db.add(score)
        await db.flush()
    score.overall_score = effective_score
    score.auto_score = auto_score
    score.effective_score = effective_score
    score.calculated_at = datetime.utcnow()
    score.updated_at = datetime.utcnow()

    existing_breakdowns = (
        await db.execute(
            select(SupplierReliabilityBreakdown).where(SupplierReliabilityBreakdown.supplier_score_id == score.id)
        )
    ).scalars().all()
    for row in existing_breakdowns:
        await db.delete(row)

    for metric_key, value in breakdown.items():
        db.add(
            SupplierReliabilityBreakdown(
                supplier_score_id=score.id,
                metric_key=metric_key,
                score_value=value,
                weight=weights[metric_key] * 100,
                detail_text=f"auto:{metric_key}",
                created_at=datetime.utcnow(),
            )
        )

    return SupplierReliabilityResult(
        overall_score=effective_score,
        auto_score=auto_score,
        effective_score=effective_score,
        breakdown=breakdown,
    )


async def sync_product_supplier_links(
    db: AsyncSession,
    *,
    product: Product,
    actor_id: str | None = None,
) -> Supplier | None:
    branch = await ensure_default_branch(db)
    if not product.branch_id:
        product.branch_id = branch.id

    active_links = (
        await db.execute(
            select(SupplierProductLink).where(
                SupplierProductLink.product_id == product.id,
                SupplierProductLink.archived_at.is_(None),
            )
        )
    ).scalars().all()

    supplier_name = normalize_supplier_name(product.supplier or "")
    if not supplier_name:
        now = datetime.utcnow()
        for link in active_links:
            link.archived_at = now
            link.updated_at = now
        return None

    supplier = await get_or_create_supplier_by_name(
        db,
        name=supplier_name,
        branch_id=product.branch_id,
        actor_id=actor_id,
    )
    if supplier is None:
        return None

    now = datetime.utcnow()
    matching_link = None
    for link in active_links:
        if link.supplier_id == supplier.id:
            matching_link = link
            link.is_primary = True
            link.legacy_supplier_name = supplier_name
            link.updated_at = now
        else:
            link.archived_at = now
            link.updated_at = now

    if matching_link is None:
        db.add(
            SupplierProductLink(
                supplier_id=supplier.id,
                product_id=product.id,
                legacy_supplier_name=supplier_name,
                is_primary=True,
                linked_by_user_id=actor_id,
                created_at=now,
                updated_at=now,
            )
        )

    await recalculate_supplier_reliability(db, supplier)
    await sync_search_projections_for_supplier(db, supplier_id=supplier.id)
    return supplier


async def bootstrap_supplier_foundations(db: AsyncSession) -> dict[str, int]:
    branch = await ensure_default_branch(db)
    products = (
        await db.execute(
            select(Product).where(Product.supplier.is_not(None), Product.supplier != "", Product.deleted_at.is_(None))
        )
    ).scalars().all()
    created_or_linked = 0
    for product in products:
        supplier = await sync_product_supplier_links(db, product=product, actor_id=product.created_by)
        if supplier is not None:
            created_or_linked += 1
            if not supplier.branch_id:
                supplier.branch_id = branch.id
    await db.flush()
    return {"linked_products": created_or_linked}


def proposal_payload_json(payload: dict[str, Any]) -> str:
    return orjson.dumps(payload).decode("utf-8")


async def create_supplier_change_proposal(
    db: AsyncSession,
    *,
    supplier: Supplier | None,
    action: str,
    payload: dict[str, Any],
    actor_id: str | None,
) -> SupplierChangeProposal:
    proposal = SupplierChangeProposal(
        supplier_id=supplier.id if supplier else None,
        action=action,
        status=SupplierProposalStatus.PENDING,
        proposed_by_user_id=actor_id,
        requires_dev_review=True,
        proposed_payload_json=proposal_payload_json(payload),
        current_payload_json=proposal_payload_json(serialize_supplier_snapshot(supplier)) if supplier else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(proposal)
    await db.flush()
    await publish_supplier_verification_notification(
        db,
        proposal_id=proposal.id,
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.name if supplier else str(payload.get("name") or action or "supplier"),
        branch_id=supplier.branch_id if supplier else payload.get("branch_id"),
        triggered_by_user_id=actor_id,
    )
    return proposal
