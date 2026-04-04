from __future__ import annotations

from datetime import datetime, timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.db.database import get_db
from server.db.models import (
    AuditEvent,
    AuditSeverity,
    MatchingDependencyCheck,
    MatchingDependencyStatus,
    NotificationEvent,
    NotificationOutbox,
    NotificationOutboxStatus,
    PriceRecord,
    PriceRecordStatus,
    PriceSearchProjection,
    Product,
    Role,
    User,
    UserBranchScope,
    VerificationQueueProjection,
)
from server.services.search import compare_prices, quick_search_catalog, search_price_history, search_verification_queue


router = APIRouter(prefix="/zones", tags=["zones"])
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def _csv_values(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _validate_optional_id(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not SAFE_ID_RE.fullmatch(cleaned):
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")
    return cleaned


def _validate_optional_text(value: str | None, *, field_name: str, max_length: int = 255) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}")
    return cleaned


async def _visible_branch_ids(db: AsyncSession, *, user: User) -> list[str] | None:
    if user.role == Role.OWNER:
        return None
    rows = (
        await db.execute(
            select(UserBranchScope.branch_id).where(
                UserBranchScope.user_id == user.id,
                UserBranchScope.can_view.is_(True),
            )
        )
    ).scalars().all()
    return list(rows) or None


def _apply_branch_visibility(stmt, *, column, requested_branch_id: str | None, visible_branch_ids: list[str] | None):
    if requested_branch_id:
        return stmt.where(column == requested_branch_id)
    if visible_branch_ids is None:
        return stmt
    return stmt.where(or_(column.is_(None), column.in_(visible_branch_ids)))


async def _resolve_requested_branch(
    db: AsyncSession,
    *,
    user: User,
    branch_id: str | None,
) -> tuple[str | None, list[str] | None]:
    visible_branch_ids = await _visible_branch_ids(db, user=user)
    if branch_id and visible_branch_ids is not None and branch_id not in visible_branch_ids:
        raise HTTPException(status_code=403, detail="forbidden_branch_scope")
    return branch_id, visible_branch_ids


def _default_landing_for_role(role: Role) -> str:
    if role == Role.OWNER:
        return "/zones/owner"
    if role == Role.DEV:
        return "/zones/dev"
    if role == Role.ADMIN:
        return "/zones/admin"
    return "/zones/stock/search"


async def _base_summary(
    db: AsyncSession,
    *,
    requested_branch_id: str | None,
    visible_branch_ids: list[str] | None,
) -> dict[str, object]:
    pending_stmt = select(func.count()).select_from(VerificationQueueProjection).where(
        VerificationQueueProjection.workflow_status == "pending"
    )
    pending_stmt = _apply_branch_visibility(
        pending_stmt,
        column=VerificationQueueProjection.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    verification_pending = int(await db.scalar(pending_stmt) or 0)

    overdue_stmt = select(func.count()).select_from(VerificationQueueProjection).where(
        VerificationQueueProjection.is_overdue.is_(True)
    )
    overdue_stmt = _apply_branch_visibility(
        overdue_stmt,
        column=VerificationQueueProjection.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    verification_overdue = int(await db.scalar(overdue_stmt) or 0)

    failed_stmt = select(func.count()).select_from(NotificationOutbox).where(
        NotificationOutbox.status == NotificationOutboxStatus.FAILED
    )
    failed_stmt = _apply_branch_visibility(
        failed_stmt,
        column=NotificationOutbox.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    notification_failed = int(await db.scalar(failed_stmt) or 0)

    retry_stmt = select(func.count()).select_from(NotificationOutbox).where(
        NotificationOutbox.status == NotificationOutboxStatus.RETRY_SCHEDULED
    )
    retry_stmt = _apply_branch_visibility(
        retry_stmt,
        column=NotificationOutbox.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    notification_retrying = int(await db.scalar(retry_stmt) or 0)

    active_price_stmt = select(func.count()).select_from(PriceSearchProjection).where(
        PriceSearchProjection.status == PriceRecordStatus.ACTIVE
    )
    active_price_stmt = _apply_branch_visibility(
        active_price_stmt,
        column=PriceSearchProjection.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    active_prices = int(await db.scalar(active_price_stmt) or 0)

    matching_stmt = select(func.count()).select_from(MatchingDependencyCheck).where(
        MatchingDependencyCheck.check_status.in_(
            [MatchingDependencyStatus.WARNING, MatchingDependencyStatus.BLOCKED]
        )
    )
    matching_warnings = int(await db.scalar(matching_stmt) or 0)

    recent_stmt = select(AuditEvent).where(
        AuditEvent.severity.in_([AuditSeverity.WARNING, AuditSeverity.CRITICAL])
    )
    recent_stmt = _apply_branch_visibility(
        recent_stmt,
        column=AuditEvent.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    recent_changes = (
        await db.execute(recent_stmt.order_by(AuditEvent.created_at.desc()).limit(6))
    ).scalars().all()

    return {
        "verification": {
            "pending": verification_pending,
            "overdue": verification_overdue,
        },
        "notifications": {
            "failed": notification_failed,
            "retrying": notification_retrying,
        },
        "pricing": {
            "active_prices": active_prices,
        },
        "matching": {
            "warning_count": matching_warnings,
        },
        "recent_changes": [
            {
                "id": item.id,
                "action": item.action,
                "entity": item.entity,
                "entity_id": item.entity_id,
                "severity": item.severity.value,
                "reason": item.reason,
                "diff_summary": item.diff_summary,
                "created_at": item.created_at.isoformat(),
            }
            for item in recent_changes
        ],
    }


def _filter_branch_scoped_items(
    items: list[dict[str, object]],
    *,
    requested_branch_id: str | None,
    visible_branch_ids: list[str] | None,
) -> list[dict[str, object]]:
    if requested_branch_id:
        return [item for item in items if item.get("branch_id") in {None, requested_branch_id}]
    if visible_branch_ids is None:
        return items
    allowed = set(visible_branch_ids)
    return [item for item in items if item.get("branch_id") in allowed]


async def _resolve_notification_target_path(
    db: AsyncSession,
    *,
    event: NotificationEvent,
) -> str:
    if event.source_domain == "verification" and event.source_entity_id:
        return f"/zones/verification?requestId={event.source_entity_id}"
    if event.source_domain == "supplier" and event.source_entity_id:
        return f"/suppliers?proposalId={event.source_entity_id}"
    if event.source_domain == "pricing":
        payload = event.payload_json or {}
        product_id = str(payload.get("product_id") or "").strip() or None
        canonical_group_id = str(payload.get("canonical_group_id") or "").strip() or None
        if not product_id and event.source_entity_type == "price_record" and event.source_entity_id:
            projection = await db.scalar(
                select(PriceSearchProjection).where(PriceSearchProjection.price_record_id == event.source_entity_id)
            )
            if projection is not None:
                product_id = projection.product_id
                canonical_group_id = projection.canonical_group_id
            else:
                record = await db.scalar(select(PriceRecord).where(PriceRecord.id == event.source_entity_id))
                if record is not None:
                    product_id = record.product_id
        if event.source_entity_type == "product" and event.source_entity_id:
            return f"/products?productId={event.source_entity_id}"
        if canonical_group_id:
            return f"/zones/search?view=compare&groupId={canonical_group_id}&quantity=1&mode=active"
        if product_id:
            return f"/zones/search?view=compare&productId={product_id}&quantity=1&mode=active"
    return "/zones/search"


@router.get("/landing", dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def zone_landing(user: User = Depends(get_current_user)):
    return {"role": user.role.value, "landing_path": _default_landing_for_role(user.role)}


@router.get("/owner/summary", dependencies=[Depends(require_roles([Role.OWNER]))])
async def owner_zone_summary(
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    base = await _base_summary(db, requested_branch_id=requested_branch_id, visible_branch_ids=visible_branch_ids)

    compare_stmt = select(func.count(func.distinct(PriceSearchProjection.canonical_group_id))).where(
        PriceSearchProjection.canonical_group_id.is_not(None),
        PriceSearchProjection.status == PriceRecordStatus.ACTIVE,
    )
    compare_stmt = _apply_branch_visibility(
        compare_stmt,
        column=PriceSearchProjection.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    group_count = int(await db.scalar(compare_stmt) or 0)

    return {
        "zone": "owner",
        "landing_path": _default_landing_for_role(user.role),
        **base,
        "comparison": {"active_group_count": group_count},
    }


@router.get("/dev/summary", dependencies=[Depends(require_roles([Role.DEV, Role.OWNER]))])
async def dev_zone_summary(
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    base = await _base_summary(db, requested_branch_id=requested_branch_id, visible_branch_ids=visible_branch_ids)

    my_queue_stmt = select(func.count()).select_from(VerificationQueueProjection).where(
        VerificationQueueProjection.assignee_user_id == user.id,
        VerificationQueueProjection.workflow_status == "pending",
    )
    my_queue_stmt = _apply_branch_visibility(
        my_queue_stmt,
        column=VerificationQueueProjection.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    return {
        "zone": "dev",
        "landing_path": _default_landing_for_role(user.role),
        **base,
        "verification": {
            **base["verification"],
            "assigned_to_me": int(await db.scalar(my_queue_stmt) or 0),
        },
    }


@router.get("/admin/summary", dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def admin_zone_summary(
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    base = await _base_summary(db, requested_branch_id=requested_branch_id, visible_branch_ids=visible_branch_ids)
    supplier_count_stmt = select(func.count()).select_from(Product).where(Product.supplier.is_not(None))
    supplier_count_stmt = _apply_branch_visibility(
        supplier_count_stmt,
        column=Product.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    return {
        "zone": "admin",
        "landing_path": _default_landing_for_role(user.role),
        **base,
        "suppliers": {"linked_products": int(await db.scalar(supplier_count_stmt) or 0)},
    }


@router.get("/stock/summary", dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def stock_zone_summary(
    branch_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    quick_products_stmt = select(func.count()).select_from(Product)
    quick_products_stmt = _apply_branch_visibility(
        quick_products_stmt,
        column=Product.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    return {
        "zone": "stock",
        "landing_path": _default_landing_for_role(user.role),
        "catalog": {"product_count": int(await db.scalar(quick_products_stmt) or 0)},
    }


@router.get("/search/quick", dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def zone_quick_search(
    q: str | None = Query(default=None),
    branch_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    supplier: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    statuses: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = _validate_optional_text(q, field_name="q", max_length=200)
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    category = _validate_optional_text(category, field_name="category")
    supplier = _validate_optional_text(supplier, field_name="supplier")
    tag = _validate_optional_text(tag, field_name="tag")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    items = await quick_search_catalog(
        db,
        query=q,
        branch_id=requested_branch_id,
        lifecycle_statuses=_csv_values(statuses),
        category=category,
        supplier_query=supplier,
        tag_query=tag,
        limit=limit,
    )
    return {
        "items": _filter_branch_scoped_items(
            items,
            requested_branch_id=requested_branch_id,
            visible_branch_ids=visible_branch_ids,
        )
    }


@router.get("/search/compare", dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def zone_compare_search(
    product_id: str | None = None,
    canonical_group_id: str | None = None,
    branch_id: str | None = None,
    quantity: int | None = Query(default=None, ge=1),
    mode: str = Query(default="active"),
    supplier_ids: str | None = None,
    delivery_modes: str | None = None,
    area_scopes: str | None = None,
    statuses: str | None = None,
    source_types: str | None = None,
    verified_supplier_only: bool = False,
    final_total_cost_min: float | None = None,
    final_total_cost_max: float | None = None,
    sort_by: str = "final_total_cost_thb",
    sort_direction: str = "asc",
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product_id = _validate_optional_id(product_id, field_name="product_id")
    canonical_group_id = _validate_optional_id(canonical_group_id, field_name="canonical_group_id")
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    response = await compare_prices(
        db,
        product_id=product_id,
        canonical_group_id=canonical_group_id,
        branch_id=requested_branch_id,
        quantity=quantity,
        selection_mode=mode,
        supplier_ids=_csv_values(supplier_ids),
        delivery_modes=_csv_values(delivery_modes),
        area_scopes=_csv_values(area_scopes),
        lifecycle_statuses=_csv_values(statuses),
        source_types=_csv_values(source_types),
        verified_supplier_only=verified_supplier_only,
        final_total_cost_min=final_total_cost_min,
        final_total_cost_max=final_total_cost_max,
        sort_by=sort_by,
        sort_direction=sort_direction,
        limit=limit,
    )
    response["rows"] = _filter_branch_scoped_items(
        list(response["rows"]),
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    response["row_count"] = len(response["rows"])
    return response


@router.get("/search/history", dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def zone_historical_search(
    product_id: str | None = None,
    canonical_group_id: str | None = None,
    supplier_id: str | None = None,
    branch_id: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    statuses: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    product_id = _validate_optional_id(product_id, field_name="product_id")
    canonical_group_id = _validate_optional_id(canonical_group_id, field_name="canonical_group_id")
    supplier_id = _validate_optional_id(supplier_id, field_name="supplier_id")
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    return {
        "items": _filter_branch_scoped_items(
            await search_price_history(
                db,
                product_id=product_id,
                canonical_group_id=canonical_group_id,
                supplier_id=supplier_id,
                branch_id=requested_branch_id,
                from_at=from_at,
                to_at=to_at,
                lifecycle_statuses=_csv_values(statuses),
                limit=limit,
            ),
            requested_branch_id=requested_branch_id,
            visible_branch_ids=visible_branch_ids,
        )
    }


@router.get("/verification/queue", dependencies=[Depends(require_roles([Role.ADMIN, Role.OWNER, Role.DEV]))])
async def zone_verification_queue(
    q: str | None = None,
    branch_id: str | None = None,
    statuses: str | None = None,
    risk_levels: str | None = None,
    subject_domains: str | None = None,
    assignee_user_id: str | None = None,
    overdue_only: bool = False,
    blocked_only: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = _validate_optional_text(q, field_name="q", max_length=200)
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    assignee_user_id = _validate_optional_id(assignee_user_id, field_name="assignee_user_id") if assignee_user_id != "me" else "me"
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)
    effective_assignee = assignee_user_id
    if user.role == Role.DEV and effective_assignee == "me":
        effective_assignee = user.id
    return {
        "items": _filter_branch_scoped_items(
            await search_verification_queue(
                db,
                query=q,
                branch_id=requested_branch_id,
                workflow_statuses=_csv_values(statuses),
                risk_levels=_csv_values(risk_levels),
                subject_domains=_csv_values(subject_domains),
                assignee_user_id=effective_assignee,
                overdue_only=overdue_only,
                has_blocking_dependency=blocked_only,
                limit=limit,
            ),
            requested_branch_id=requested_branch_id,
            visible_branch_ids=visible_branch_ids,
        )
    }


@router.get("/notifications/summary", dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def zone_notification_summary(
    branch_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch_id = _validate_optional_id(branch_id, field_name="branch_id")
    requested_branch_id, visible_branch_ids = await _resolve_requested_branch(db, user=user, branch_id=branch_id)

    recent_stmt = (
        select(NotificationOutbox, NotificationEvent)
        .join(NotificationEvent, NotificationEvent.id == NotificationOutbox.event_id)
        .order_by(NotificationOutbox.updated_at.desc(), NotificationOutbox.created_at.desc())
        .limit(limit)
    )
    recent_stmt = _apply_branch_visibility(
        recent_stmt,
        column=NotificationOutbox.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    rows = (await db.execute(recent_stmt)).all()

    pending_stmt = select(func.count()).select_from(NotificationOutbox).where(
        NotificationOutbox.status.in_(
            [NotificationOutboxStatus.PENDING, NotificationOutboxStatus.PROCESSING, NotificationOutboxStatus.RETRY_SCHEDULED]
        )
    )
    pending_stmt = _apply_branch_visibility(
        pending_stmt,
        column=NotificationOutbox.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    pending_total = int(await db.scalar(pending_stmt) or 0)

    failed_stmt = select(func.count()).select_from(NotificationOutbox).where(NotificationOutbox.status == NotificationOutboxStatus.FAILED)
    failed_stmt = _apply_branch_visibility(
        failed_stmt,
        column=NotificationOutbox.branch_id,
        requested_branch_id=requested_branch_id,
        visible_branch_ids=visible_branch_ids,
    )
    failed_total = int(await db.scalar(failed_stmt) or 0)

    items = []
    for outbox, event in rows:
        items.append(
            {
                "outbox_id": outbox.id,
                "event_id": event.id,
                "event_type": event.event_type,
                "source_domain": event.source_domain,
                "source_entity_type": event.source_entity_type,
                "source_entity_id": event.source_entity_id,
                "status": outbox.status.value,
                "severity": outbox.severity.value,
                "routing_role": outbox.routing_role,
                "recipient_user_id": outbox.recipient_user_id,
                "message_title": outbox.message_title,
                "target_path": await _resolve_notification_target_path(db, event=event),
                "updated_at": outbox.updated_at.isoformat(),
            }
        )

    return {
        "summary": {
            "pending_total": pending_total,
            "failed_total": failed_total,
        },
        "items": items,
    }
