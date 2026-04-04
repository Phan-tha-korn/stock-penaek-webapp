from __future__ import annotations

from datetime import datetime
from typing import Any

import orjson
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.api.schemas import (
    AttachmentOut,
    SupplierCreateIn,
    SupplierListOut,
    SupplierOut,
    SupplierPickupPointOut,
    SupplierProposalActionIn,
    SupplierProposalOut,
    SupplierReliabilityBreakdownOut,
    SupplierReliabilityOut,
    SupplierUpdateIn,
    SupplierContactOut,
    SupplierLinkOut,
)
from server.db.database import get_db
from server.db.models import (
    Attachment,
    Role,
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
    User,
)
from server.services.attachments import archive_entity_attachment, create_attachment_for_entity, list_entity_attachments
from server.services.audit import write_audit_log
from server.services.branches import ensure_default_branch
from server.services.catalog_foundation import normalize_supplier_key
from server.services.suppliers import (
    apply_supplier_payload,
    create_supplier_change_proposal,
    get_or_create_supplier_by_name,
    normalize_supplier_name,
    recalculate_supplier_reliability,
    replace_supplier_contacts,
    replace_supplier_links,
    replace_supplier_pickup_points,
    serialize_supplier_snapshot,
)


router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _proposal_json(value: str | None) -> dict | None:
    if not value:
        return None
    return orjson.loads(value)


def _attachment_out(row: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=row.id,
        original_filename=row.original_filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        classification=row.classification,
        storage_driver=row.storage_driver.value,
        storage_bucket=row.storage_bucket,
        storage_key=row.storage_key,
        status=row.status.value,
        malware_status=row.malware_status.value,
        owner_user_id=row.owner_user_id,
        created_at=row.created_at,
        archived_at=row.archived_at,
        deleted_at=row.deleted_at,
    )


def _proposal_out(row: SupplierChangeProposal) -> SupplierProposalOut:
    return SupplierProposalOut(
        id=row.id,
        supplier_id=row.supplier_id,
        action=row.action,
        status=row.status.value,
        proposed_by_user_id=row.proposed_by_user_id,
        reviewed_by_user_id=row.reviewed_by_user_id,
        approved_supplier_id=row.approved_supplier_id,
        requires_dev_review=row.requires_dev_review,
        proposed_payload=_proposal_json(row.proposed_payload_json),
        current_payload=_proposal_json(row.current_payload_json),
        review_note=row.review_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
        reviewed_at=row.reviewed_at,
    )


async def _active_contacts(db: AsyncSession, supplier_id: str) -> list[SupplierContact]:
    return (
        await db.execute(
            select(SupplierContact)
            .where(SupplierContact.supplier_id == supplier_id, SupplierContact.archived_at.is_(None))
            .order_by(SupplierContact.sort_order.asc(), SupplierContact.created_at.asc())
        )
    ).scalars().all()


async def _active_links(db: AsyncSession, supplier_id: str) -> list[SupplierLink]:
    return (
        await db.execute(
            select(SupplierLink)
            .where(SupplierLink.supplier_id == supplier_id, SupplierLink.archived_at.is_(None))
            .order_by(SupplierLink.sort_order.asc(), SupplierLink.created_at.asc())
        )
    ).scalars().all()


async def _active_pickups(db: AsyncSession, supplier_id: str) -> list[SupplierPickupPoint]:
    return (
        await db.execute(
            select(SupplierPickupPoint)
            .where(SupplierPickupPoint.supplier_id == supplier_id, SupplierPickupPoint.archived_at.is_(None))
            .order_by(SupplierPickupPoint.created_at.asc())
        )
    ).scalars().all()


async def _supplier_product_count(db: AsyncSession, supplier_id: str) -> int:
    count = await db.scalar(
        select(func.count()).select_from(SupplierProductLink).where(
            SupplierProductLink.supplier_id == supplier_id,
            SupplierProductLink.archived_at.is_(None),
        )
    )
    return int(count or 0)


async def _supplier_reliability_out(db: AsyncSession, supplier_id: str) -> SupplierReliabilityOut | None:
    score = await db.scalar(select(SupplierReliabilityScore).where(SupplierReliabilityScore.supplier_id == supplier_id))
    if not score:
        profile = await db.scalar(select(SupplierReliabilityProfile).where(SupplierReliabilityProfile.supplier_id == supplier_id))
        if not profile:
            return None
        return SupplierReliabilityOut(
            overall_score=float(profile.overall_score or 0),
            auto_score=float(profile.auto_score or 0),
            effective_score=float(profile.overall_score or 0),
            breakdown=[
                SupplierReliabilityBreakdownOut(metric_key="price_competitiveness", score_value=float(profile.price_competitiveness_score or 0), weight=15, detail_text="profile"),
                SupplierReliabilityBreakdownOut(metric_key="purchase_frequency", score_value=float(profile.purchase_frequency_score or 0), weight=15, detail_text="profile"),
                SupplierReliabilityBreakdownOut(metric_key="delivery_reliability", score_value=float(profile.delivery_reliability_score or 0), weight=20, detail_text="profile"),
                SupplierReliabilityBreakdownOut(metric_key="data_completeness", score_value=float(profile.data_completeness_score or 0), weight=20, detail_text="profile"),
                SupplierReliabilityBreakdownOut(metric_key="verification_confidence", score_value=float(profile.verification_confidence_score or 0), weight=20, detail_text="profile"),
                SupplierReliabilityBreakdownOut(metric_key="dispute_reject", score_value=float(profile.dispute_reject_score or 0), weight=10, detail_text="profile"),
            ],
        )

    breakdown_rows = (
        await db.execute(
            select(SupplierReliabilityBreakdown).where(SupplierReliabilityBreakdown.supplier_score_id == score.id)
        )
    ).scalars().all()
    return SupplierReliabilityOut(
        overall_score=float(score.overall_score or 0),
        auto_score=float(score.auto_score or 0),
        effective_score=float(score.effective_score or 0),
        breakdown=[
            SupplierReliabilityBreakdownOut(
                metric_key=row.metric_key,
                score_value=float(row.score_value or 0),
                weight=float(row.weight or 0),
                detail_text=row.detail_text,
            )
            for row in breakdown_rows
        ],
    )


async def _supplier_out(db: AsyncSession, supplier: Supplier, *, include_detail: bool) -> SupplierOut:
    contacts = await _active_contacts(db, supplier.id) if include_detail else []
    links = await _active_links(db, supplier.id) if include_detail else []
    pickups = await _active_pickups(db, supplier.id) if include_detail else []
    attachments = await list_entity_attachments(db, entity_type="supplier", entity_id=supplier.id) if include_detail else []
    return SupplierOut(
        id=supplier.id,
        branch_id=supplier.branch_id,
        code=supplier.code,
        name=supplier.name,
        normalized_name=supplier.normalized_name,
        phone=supplier.phone,
        line_id=supplier.line_id,
        facebook_url=supplier.facebook_url,
        website_url=supplier.website_url,
        address=supplier.address,
        pickup_notes=supplier.pickup_notes,
        source_details=supplier.source_details,
        purchase_history_notes=supplier.purchase_history_notes,
        reliability_note=supplier.reliability_note,
        status=supplier.status.value,
        is_verified=supplier.is_verified,
        archived_at=supplier.archived_at,
        deleted_at=supplier.deleted_at,
        delete_reason=supplier.delete_reason,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
        product_count=await _supplier_product_count(db, supplier.id),
        contacts=[
            SupplierContactOut(
                id=row.id,
                contact_type=row.contact_type,
                label=row.label,
                value=row.value,
                is_primary=row.is_primary,
                sort_order=row.sort_order,
                created_at=row.created_at,
                archived_at=row.archived_at,
            )
            for row in contacts
        ],
        links=[
            SupplierLinkOut(
                id=row.id,
                link_type=row.link_type,
                label=row.label,
                url=row.url,
                is_primary=row.is_primary,
                sort_order=row.sort_order,
                created_at=row.created_at,
                archived_at=row.archived_at,
            )
            for row in links
        ],
        pickup_points=[
            SupplierPickupPointOut(
                id=row.id,
                label=row.label,
                address=row.address,
                details=row.details,
                is_primary=row.is_primary,
                created_at=row.created_at,
                archived_at=row.archived_at,
            )
            for row in pickups
        ],
        reliability=await _supplier_reliability_out(db, supplier.id),
        attachments=[_attachment_out(row) for row in attachments],
    )


async def _get_supplier_or_404(db: AsyncSession, supplier_id: str) -> Supplier:
    supplier = await db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.deleted_at.is_(None)))
    if not supplier:
        raise HTTPException(status_code=404, detail="supplier_not_found")
    return supplier


def _payload_dict(payload: SupplierCreateIn | SupplierUpdateIn, *, existing: Supplier | None = None) -> dict[str, Any]:
    if isinstance(payload, SupplierCreateIn):
        data = payload.model_dump()
    else:
        data = payload.model_dump(exclude_none=True)
    if existing is not None and "name" not in data:
        data["name"] = existing.name
    data["name"] = normalize_supplier_name(str(data.get("name") or ""))
    if not data["name"]:
        raise HTTPException(status_code=400, detail="supplier_name_required")
    normalized = normalize_supplier_key(data["name"])
    if not normalized:
        raise HTTPException(status_code=400, detail="supplier_name_required")
    data["normalized_name"] = normalized
    return data


@router.get(
    "",
    response_model=SupplierListOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    q: str | None = None,
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Supplier).where(Supplier.deleted_at.is_(None))
    if not include_archived:
        stmt = stmt.where(Supplier.archived_at.is_(None))
    if q:
        token = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Supplier.name).like(token),
                func.lower(Supplier.code).like(token),
                func.lower(Supplier.phone).like(token),
                func.lower(Supplier.line_id).like(token),
            )
        )

    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        await db.execute(stmt.order_by(Supplier.updated_at.desc(), Supplier.created_at.desc()).limit(limit).offset(offset))
    ).scalars().all()
    return SupplierListOut(items=[await _supplier_out(db, row, include_detail=False) for row in rows], total=total)


@router.get(
    "/proposals",
    response_model=list[SupplierProposalOut],
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def list_supplier_proposals(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
):
    stmt = select(SupplierChangeProposal)
    if status:
        stmt = stmt.where(SupplierChangeProposal.status == SupplierProposalStatus(status.upper()))
    rows = (await db.execute(stmt.order_by(SupplierChangeProposal.created_at.desc()))).scalars().all()
    return [_proposal_out(row) for row in rows]


@router.get(
    "/{supplier_id}",
    response_model=SupplierOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def get_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
):
    supplier = await _get_supplier_or_404(db, supplier_id)
    return await _supplier_out(db, supplier, include_detail=True)


@router.post(
    "",
    response_model=SupplierOut | SupplierProposalOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def create_supplier(
    payload: SupplierCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = _payload_dict(payload)
    existing = await db.scalar(select(Supplier).where(Supplier.normalized_name == data["normalized_name"], Supplier.deleted_at.is_(None)))
    if existing:
        raise HTTPException(status_code=409, detail="supplier_name_exists")

    branch = await ensure_default_branch(db)
    data["branch_id"] = data.get("branch_id") or branch.id
    if user.role == Role.ADMIN:
        proposal = await create_supplier_change_proposal(db, supplier=None, action="create", payload=data, actor_id=user.id)
        await write_audit_log(
            db,
            request=request,
            actor=user,
            action="SUPPLIER_PROPOSAL_CREATE",
            entity="supplier_proposal",
            entity_id=proposal.id,
            success=True,
            message="supplier_create_pending_dev_review",
            before=None,
            after={"action": "create", "name": data["name"]},
            branch_id=data["branch_id"],
            reason="admin_change_requires_dev_review",
            diff_summary="supplier create proposal",
        )
        await db.commit()
        return _proposal_out(proposal)

    supplier = Supplier(
        branch_id=data["branch_id"],
        code="",
        name="",
        normalized_name="",
        created_by=user.id,
        updated_by=user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier)
    await db.flush()
    supplier.code = supplier.code or f"SUP-{supplier.id[:8].upper()}"
    apply_supplier_payload(supplier, data, actor_id=user.id)
    await replace_supplier_contacts(db, supplier, [item.model_dump() for item in payload.contacts])
    await replace_supplier_links(db, supplier, [item.model_dump() for item in payload.links])
    await replace_supplier_pickup_points(db, supplier, [item.model_dump() for item in payload.pickup_points])
    await recalculate_supplier_reliability(db, supplier)
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_CREATE",
        entity="supplier",
        entity_id=supplier.id,
        success=True,
        message="supplier_created",
        before=None,
        after=serialize_supplier_snapshot(supplier),
        branch_id=supplier.branch_id,
        reason="supplier_created",
        diff_summary="supplier create",
    )
    await db.commit()
    return await _supplier_out(db, supplier, include_detail=True)


@router.put(
    "/{supplier_id}",
    response_model=SupplierOut | SupplierProposalOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def update_supplier(
    supplier_id: str,
    payload: SupplierUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = await _get_supplier_or_404(db, supplier_id)
    data = _payload_dict(payload, existing=supplier)
    conflict = await db.scalar(
        select(Supplier).where(
            Supplier.normalized_name == data["normalized_name"],
            Supplier.id != supplier.id,
            Supplier.deleted_at.is_(None),
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="supplier_name_exists")

    if user.role == Role.ADMIN:
        proposal = await create_supplier_change_proposal(db, supplier=supplier, action="update", payload=data, actor_id=user.id)
        await write_audit_log(
            db,
            request=request,
            actor=user,
            action="SUPPLIER_PROPOSAL_CREATE",
            entity="supplier_proposal",
            entity_id=proposal.id,
            success=True,
            message="supplier_update_pending_dev_review",
            before=serialize_supplier_snapshot(supplier),
            after=data,
            branch_id=supplier.branch_id,
            reason="admin_change_requires_dev_review",
            diff_summary="supplier update proposal",
        )
        await db.commit()
        return _proposal_out(proposal)

    before = serialize_supplier_snapshot(supplier)
    apply_supplier_payload(supplier, data, actor_id=user.id)
    if payload.contacts is not None:
        await replace_supplier_contacts(db, supplier, [item.model_dump() for item in payload.contacts])
    if payload.links is not None:
        await replace_supplier_links(db, supplier, [item.model_dump() for item in payload.links])
    if payload.pickup_points is not None:
        await replace_supplier_pickup_points(db, supplier, [item.model_dump() for item in payload.pickup_points])
    await recalculate_supplier_reliability(db, supplier)
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_UPDATE",
        entity="supplier",
        entity_id=supplier.id,
        success=True,
        message="supplier_updated",
        before=before,
        after=serialize_supplier_snapshot(supplier),
        branch_id=supplier.branch_id,
        reason="supplier_updated",
        diff_summary="supplier update",
    )
    await db.commit()
    return await _supplier_out(db, supplier, include_detail=True)


@router.delete(
    "/{supplier_id}",
    response_model=SupplierOut | SupplierProposalOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def archive_supplier(
    supplier_id: str,
    request: Request,
    reason: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = await _get_supplier_or_404(db, supplier_id)
    if user.role == Role.ADMIN:
        proposal = await create_supplier_change_proposal(
            db,
            supplier=supplier,
            action="archive",
            payload={"name": supplier.name, "status": SupplierStatus.ARCHIVED.value, "reason": reason},
            actor_id=user.id,
        )
        await write_audit_log(
            db,
            request=request,
            actor=user,
            action="SUPPLIER_PROPOSAL_CREATE",
            entity="supplier_proposal",
            entity_id=proposal.id,
            success=True,
            message="supplier_archive_pending_dev_review",
            before=serialize_supplier_snapshot(supplier),
            after={"status": SupplierStatus.ARCHIVED.value, "reason": reason},
            branch_id=supplier.branch_id,
            reason="admin_change_requires_dev_review",
            diff_summary="supplier archive proposal",
        )
        await db.commit()
        return _proposal_out(proposal)

    before = serialize_supplier_snapshot(supplier)
    supplier.status = SupplierStatus.ARCHIVED
    supplier.archived_at = datetime.utcnow()
    supplier.delete_reason = reason or supplier.delete_reason
    supplier.updated_by = user.id
    supplier.updated_at = datetime.utcnow()
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_ARCHIVE",
        entity="supplier",
        entity_id=supplier.id,
        success=True,
        message=reason or "supplier_archived",
        before=before,
        after=serialize_supplier_snapshot(supplier),
        branch_id=supplier.branch_id,
        reason=reason or "supplier_archived",
        diff_summary="supplier archive",
    )
    await db.commit()
    return await _supplier_out(db, supplier, include_detail=True)


@router.get(
    "/{supplier_id}/proposals",
    response_model=list[SupplierProposalOut],
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def supplier_proposals(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(SupplierChangeProposal)
            .where(SupplierChangeProposal.supplier_id == supplier_id)
            .order_by(SupplierChangeProposal.created_at.desc())
        )
    ).scalars().all()
    return [_proposal_out(row) for row in rows]


async def _apply_proposal_to_supplier(
    *,
    db: AsyncSession,
    proposal: SupplierChangeProposal,
    reviewer: User,
) -> Supplier:
    payload = _proposal_json(proposal.proposed_payload_json) or {}
    supplier = await db.scalar(select(Supplier).where(Supplier.id == proposal.supplier_id)) if proposal.supplier_id else None
    branch = await ensure_default_branch(db)

    if proposal.action == "create":
        supplier = Supplier(
            branch_id=str(payload.get("branch_id") or branch.id),
            code="",
            name="",
            normalized_name="",
            created_by=reviewer.id,
            updated_by=reviewer.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(supplier)
        await db.flush()
        supplier.code = f"SUP-{supplier.id[:8].upper()}"
    elif not supplier:
        raise HTTPException(status_code=404, detail="supplier_not_found")

    if proposal.action == "archive":
        supplier.status = SupplierStatus.ARCHIVED
        supplier.archived_at = datetime.utcnow()
        supplier.delete_reason = str(payload.get("reason") or supplier.delete_reason or "")
        supplier.updated_by = reviewer.id
        supplier.updated_at = datetime.utcnow()
        return supplier

    apply_supplier_payload(supplier, payload, actor_id=reviewer.id)
    contacts_payload = payload.get("contacts")
    links_payload = payload.get("links")
    pickups_payload = payload.get("pickup_points")
    if isinstance(contacts_payload, list):
        await replace_supplier_contacts(db, supplier, contacts_payload)
    if isinstance(links_payload, list):
        await replace_supplier_links(db, supplier, links_payload)
    if isinstance(pickups_payload, list):
        await replace_supplier_pickup_points(db, supplier, pickups_payload)
    await recalculate_supplier_reliability(db, supplier)
    return supplier


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=SupplierProposalOut,
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))],
)
async def approve_supplier_proposal(
    proposal_id: str,
    payload: SupplierProposalActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proposal = await db.scalar(
        select(SupplierChangeProposal).where(
            SupplierChangeProposal.id == proposal_id,
            SupplierChangeProposal.status == SupplierProposalStatus.PENDING,
        )
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="supplier_proposal_not_found")

    supplier = await _apply_proposal_to_supplier(db=db, proposal=proposal, reviewer=user)
    proposal.status = SupplierProposalStatus.APPROVED
    proposal.review_note = payload.review_note
    proposal.reviewed_by_user_id = user.id
    proposal.reviewed_at = datetime.utcnow()
    proposal.updated_at = datetime.utcnow()
    proposal.approved_supplier_id = supplier.id

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_PROPOSAL_APPROVE",
        entity="supplier_proposal",
        entity_id=proposal.id,
        success=True,
        message="supplier_proposal_approved",
        before=proposal.current_payload_json,
        after=proposal.proposed_payload_json,
        branch_id=supplier.branch_id,
        reason=payload.review_note or "supplier_proposal_approved",
        diff_summary=f"{proposal.action} approved",
    )
    await db.commit()
    return _proposal_out(proposal)


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=SupplierProposalOut,
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))],
)
async def reject_supplier_proposal(
    proposal_id: str,
    payload: SupplierProposalActionIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proposal = await db.scalar(
        select(SupplierChangeProposal).where(
            SupplierChangeProposal.id == proposal_id,
            SupplierChangeProposal.status == SupplierProposalStatus.PENDING,
        )
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="supplier_proposal_not_found")

    proposal.status = SupplierProposalStatus.REJECTED
    proposal.review_note = payload.review_note
    proposal.reviewed_by_user_id = user.id
    proposal.reviewed_at = datetime.utcnow()
    proposal.updated_at = datetime.utcnow()

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_PROPOSAL_REJECT",
        entity="supplier_proposal",
        entity_id=proposal.id,
        success=True,
        message="supplier_proposal_rejected",
        before=proposal.current_payload_json,
        after=proposal.proposed_payload_json,
        branch_id=None,
        reason=payload.review_note or "supplier_proposal_rejected",
        diff_summary=f"{proposal.action} rejected",
    )
    await db.commit()
    return _proposal_out(proposal)


@router.get(
    "/{supplier_id}/attachments",
    response_model=list[AttachmentOut],
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def supplier_attachments(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
):
    await _get_supplier_or_404(db, supplier_id)
    rows = await list_entity_attachments(db, entity_type="supplier", entity_id=supplier_id)
    return [_attachment_out(row) for row in rows]


@router.post(
    "/{supplier_id}/attachments",
    response_model=AttachmentOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def upload_supplier_attachment(
    supplier_id: str,
    request: Request,
    classification: str = Form("other"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = await _get_supplier_or_404(db, supplier_id)
    attachment = await create_attachment_for_entity(
        db,
        actor=user,
        entity_type="supplier",
        entity_id=supplier.id,
        branch_id=supplier.branch_id,
        upload=file,
        classification=classification,
    )
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_ATTACHMENT_UPLOAD",
        entity="supplier",
        entity_id=supplier.id,
        success=True,
        message="supplier_attachment_uploaded",
        before=None,
        after={"attachment_id": attachment.id, "classification": attachment.classification},
        branch_id=supplier.branch_id,
        reason="supplier_attachment_uploaded",
        diff_summary="attachment upload",
    )
    await db.commit()
    return _attachment_out(attachment)


@router.delete(
    "/{supplier_id}/attachments/{attachment_id}",
    response_model=AttachmentOut,
    dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))],
)
async def archive_supplier_attachment(
    supplier_id: str,
    attachment_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = await _get_supplier_or_404(db, supplier_id)
    attachment = await archive_entity_attachment(
        db,
        entity_type="supplier",
        entity_id=supplier.id,
        attachment_id=attachment_id,
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment_not_found")
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="SUPPLIER_ATTACHMENT_ARCHIVE",
        entity="supplier",
        entity_id=supplier.id,
        success=True,
        message="supplier_attachment_archived",
        before={"attachment_id": attachment.id},
        after={"attachment_id": attachment.id, "status": attachment.status.value},
        branch_id=supplier.branch_id,
        reason="supplier_attachment_archived",
        diff_summary="attachment archive",
    )
    await db.commit()
    return _attachment_out(attachment)
