from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import (
    AuditSeverity,
    CanonicalGroupLockState,
    CanonicalGroupMember,
    CanonicalProductGroup,
    MatchingDependencyCheck,
    MatchingDependencyStatus,
    MatchingDependencyType,
    MatchingGroupStatus,
    MatchingOperation,
    MatchingOperationGroupState,
    MatchingOperationMembershipState,
    MatchingOperationStatus,
    MatchingOperationType,
    MatchingSnapshotSide,
    PriceRecord,
    Product,
    Role,
    User,
)
from server.services.audit import write_audit_log
from server.services.search import sync_search_projections_for_matching_products


STRUCTURAL_OPERATION_TYPES = {
    MatchingOperationType.ADD_PRODUCT,
    MatchingOperationType.REMOVE_PRODUCT,
    MatchingOperationType.MOVE_PRODUCT,
    MatchingOperationType.MERGE_GROUPS,
    MatchingOperationType.SPLIT_GROUP,
    MatchingOperationType.REVERSE_OPERATION,
}
MATCHING_MANAGER_ROLES = {Role.DEV, Role.OWNER}


def _utc_now() -> datetime:
    return datetime.utcnow()


async def _run_in_single_transaction(
    db: AsyncSession,
    callback: Callable[[], Awaitable[Any]],
) -> Any:
    if db.in_transaction():
        return await callback()
    async with db.begin():
        return await callback()


def _normalize_group_code(value: str) -> str:
    code = str(value or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="matching_group_code_required")
    return code[:64]


def _normalize_group_name(value: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="matching_group_name_required")
    return name[:255]


def _normalize_group_system_name(value: str | None, *, fallback: str) -> str:
    system_name = str(value or "").strip()
    if not system_name:
        system_name = fallback
    return system_name[:255]


def _normalize_group_description(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_lock_state(value: str | CanonicalGroupLockState) -> CanonicalGroupLockState:
    try:
        return value if isinstance(value, CanonicalGroupLockState) else CanonicalGroupLockState(str(value or "editable"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_matching_lock_state") from exc


def _require_reason(value: str) -> str:
    reason = str(value or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="matching_reason_required")
    return reason


def _normalize_note(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_ids(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        resolved = str(value or "").strip()
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def _ensure_matching_manager(actor: User | None) -> User:
    if actor is None or actor.role not in MATCHING_MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="matching_permission_denied")
    return actor


def _ensure_group_active(group: CanonicalProductGroup) -> None:
    if group.status != MatchingGroupStatus.ACTIVE or group.archived_at is not None:
        raise HTTPException(status_code=409, detail="matching_group_inactive")


def _ensure_group_editable(group: CanonicalProductGroup) -> None:
    _ensure_group_active(group)
    if group.lock_state != CanonicalGroupLockState.EDITABLE:
        raise HTTPException(status_code=409, detail="matching_group_locked")


def _ensure_lock_change_allowed(
    *,
    actor: User,
    group: CanonicalProductGroup,
    new_lock_state: CanonicalGroupLockState,
) -> None:
    _ensure_group_active(group)
    if actor.role != Role.OWNER and (
        group.lock_state == CanonicalGroupLockState.OWNER_LOCKED or new_lock_state == CanonicalGroupLockState.OWNER_LOCKED
    ):
        raise HTTPException(status_code=403, detail="matching_owner_lock_requires_owner")


def _structural_operation(operation_type: MatchingOperationType) -> bool:
    return operation_type in STRUCTURAL_OPERATION_TYPES


async def _get_group(db: AsyncSession, group_id: str) -> CanonicalProductGroup:
    group = await db.scalar(select(CanonicalProductGroup).where(CanonicalProductGroup.id == group_id))
    if not group:
        raise HTTPException(status_code=404, detail="matching_group_not_found")
    return group


async def _get_product(db: AsyncSession, product_id: str) -> Product:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="matching_product_not_found")
    if product.deleted_at is not None or product.archived_at is not None:
        raise HTTPException(status_code=409, detail="matching_product_inactive")
    return product


async def _get_active_membership_for_product(db: AsyncSession, product_id: str) -> CanonicalGroupMember | None:
    return await db.scalar(
        select(CanonicalGroupMember).where(
            CanonicalGroupMember.product_id == product_id,
            CanonicalGroupMember.removed_at.is_(None),
            CanonicalGroupMember.archived_at.is_(None),
        )
    )


async def _get_active_memberships_for_group(db: AsyncSession, group_id: str) -> list[CanonicalGroupMember]:
    return (
        await db.execute(
            select(CanonicalGroupMember).where(
                CanonicalGroupMember.group_id == group_id,
                CanonicalGroupMember.removed_at.is_(None),
                CanonicalGroupMember.archived_at.is_(None),
            )
        )
    ).scalars().all()


async def _get_active_primary_for_group(db: AsyncSession, group_id: str) -> CanonicalGroupMember | None:
    return await db.scalar(
        select(CanonicalGroupMember).where(
            CanonicalGroupMember.group_id == group_id,
            CanonicalGroupMember.is_primary.is_(True),
            CanonicalGroupMember.removed_at.is_(None),
            CanonicalGroupMember.archived_at.is_(None),
        )
    )


async def _ensure_group_code_available(db: AsyncSession, code: str, *, exclude_group_id: str | None = None) -> None:
    stmt = select(CanonicalProductGroup).where(CanonicalProductGroup.code == code)
    if exclude_group_id:
        stmt = stmt.where(CanonicalProductGroup.id != exclude_group_id)
    existing = await db.scalar(stmt)
    if existing:
        raise HTTPException(status_code=409, detail="matching_group_code_exists")


def _minimal_snapshot(
    *,
    operation_type: MatchingOperationType,
    group_states: Sequence[dict[str, Any]],
    membership_states: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "operation_type": operation_type.value,
        "group_ids": sorted({str(item["group_id"]) for item in group_states if item.get("group_id")}),
        "product_ids": sorted({str(item["product_id"]) for item in membership_states if item.get("product_id")}),
        "membership_ids": sorted({str(item["membership_id"]) for item in membership_states if item.get("membership_id")}),
        "group_count": len(group_states),
        "membership_count": len(membership_states),
    }


async def _collect_group_states(db: AsyncSession, group_ids: Iterable[str]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for group_id in {group_id for group_id in group_ids if group_id}:
        group = await db.scalar(select(CanonicalProductGroup).where(CanonicalProductGroup.id == group_id))
        if not group:
            continue
        member_count = await db.scalar(
            select(func.count(CanonicalGroupMember.id)).where(
                CanonicalGroupMember.group_id == group.id,
                CanonicalGroupMember.removed_at.is_(None),
                CanonicalGroupMember.archived_at.is_(None),
            )
        )
        states.append(
            {
                "group_id": group.id,
                "display_name": group.display_name,
                "status": group.status.value,
                "lock_state": group.lock_state.value,
                "version_no": int(group.version_no or 1),
                "merged_into_group_id": group.merged_into_group_id,
                "member_count": int(member_count or 0),
            }
        )
    return states


async def _collect_membership_states(db: AsyncSession, product_ids: Iterable[str]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for product_id in {item for item in product_ids if item}:
        membership = await _get_active_membership_for_product(db, product_id)
        if membership:
            states.append(
                {
                    "membership_id": membership.id,
                    "product_id": membership.product_id,
                    "group_id": membership.group_id,
                    "is_primary": membership.is_primary,
                    "assigned_at": membership.assigned_at,
                    "assigned_by": membership.assigned_by,
                    "removed_at": membership.removed_at,
                    "removed_by": membership.removed_by,
                    "active_flag": True,
                }
            )
            continue
        states.append(
            {
                "membership_id": None,
                "product_id": product_id,
                "group_id": None,
                "is_primary": False,
                "assigned_at": None,
                "assigned_by": None,
                "removed_at": None,
                "removed_by": None,
                "active_flag": False,
            }
        )
    return states


async def _create_operation(
    db: AsyncSession,
    *,
    actor: User,
    operation_type: MatchingOperationType,
    reason: str,
    note: str = "",
    source_group_id: str | None = None,
    target_group_id: str | None = None,
    reversal_of_operation_id: str | None = None,
) -> MatchingOperation:
    operation = MatchingOperation(
        operation_type=operation_type,
        status=MatchingOperationStatus.COMPLETED,
        source_group_id=source_group_id,
        target_group_id=target_group_id,
        actor_user_id=actor.id,
        reason=str(reason or "").strip(),
        note=str(note or "").strip(),
        before_snapshot_json={},
        after_snapshot_json={},
        reversal_of_operation_id=reversal_of_operation_id,
        dependency_status=MatchingDependencyStatus.CLEAR,
        created_at=_utc_now(),
    )
    db.add(operation)
    await db.flush()
    return operation


async def _write_snapshot_rows(
    db: AsyncSession,
    *,
    operation_id: str,
    before_group_states: Sequence[dict[str, Any]],
    after_group_states: Sequence[dict[str, Any]],
    before_membership_states: Sequence[dict[str, Any]],
    after_membership_states: Sequence[dict[str, Any]],
) -> None:
    for side, items in (
        (MatchingSnapshotSide.BEFORE, before_group_states),
        (MatchingSnapshotSide.AFTER, after_group_states),
    ):
        for item in items:
            db.add(
                MatchingOperationGroupState(
                    operation_id=operation_id,
                    snapshot_side=side,
                    group_id=item["group_id"],
                    display_name=item["display_name"],
                    status=MatchingGroupStatus(item["status"]),
                    lock_state=CanonicalGroupLockState(item["lock_state"]),
                    version_no=int(item["version_no"] or 1),
                    merged_into_group_id=item.get("merged_into_group_id"),
                    member_count=int(item.get("member_count") or 0),
                    created_at=_utc_now(),
                )
            )
    for side, items in (
        (MatchingSnapshotSide.BEFORE, before_membership_states),
        (MatchingSnapshotSide.AFTER, after_membership_states),
    ):
        for item in items:
            db.add(
                MatchingOperationMembershipState(
                    operation_id=operation_id,
                    snapshot_side=side,
                    membership_id=item.get("membership_id"),
                    product_id=item["product_id"],
                    group_id=item.get("group_id"),
                    is_primary=bool(item.get("is_primary", False)),
                    assigned_at=item.get("assigned_at"),
                    assigned_by=item.get("assigned_by"),
                    removed_at=item.get("removed_at"),
                    removed_by=item.get("removed_by"),
                    active_flag=bool(item.get("active_flag", False)),
                    created_at=_utc_now(),
                )
            )


async def _record_dependency_checks(
    db: AsyncSession,
    *,
    operation: MatchingOperation,
    product_ids: Iterable[str],
) -> MatchingDependencyStatus:
    affected_product_ids = [product_id for product_id in {item for item in product_ids if item}]
    pricing_count = 0
    if affected_product_ids:
        pricing_count = int(
            await db.scalar(
                select(func.count(PriceRecord.id)).where(
                    PriceRecord.product_id.in_(affected_product_ids),
                    PriceRecord.archived_at.is_(None),
                )
            )
            or 0
        )
    checks = [
        (
            MatchingDependencyType.PRICING,
            MatchingDependencyStatus.WARNING if pricing_count > 0 else MatchingDependencyStatus.CLEAR,
            pricing_count,
            {"affected_product_ids": affected_product_ids[:50]},
        ),
        (
            MatchingDependencyType.SEARCH,
            MatchingDependencyStatus.CLEAR,
            0,
            {"integration": "pending_phase6"},
        ),
        (
            MatchingDependencyType.REPORTING,
            MatchingDependencyStatus.CLEAR,
            0,
            {"integration": "pending_phase9"},
        ),
    ]
    overall = MatchingDependencyStatus.CLEAR
    for dependency_type, status, count, detail in checks:
        db.add(
            MatchingDependencyCheck(
                operation_id=operation.id,
                dependency_type=dependency_type,
                check_status=status,
                affected_entity_count=count,
                detail_json=detail,
                created_at=_utc_now(),
            )
        )
        if status == MatchingDependencyStatus.BLOCKED:
            overall = MatchingDependencyStatus.BLOCKED
        elif status == MatchingDependencyStatus.WARNING and overall == MatchingDependencyStatus.CLEAR:
            overall = MatchingDependencyStatus.WARNING
    operation.dependency_status = overall
    return overall


def _validate_primary_conflict(
    *,
    existing_primary: CanonicalGroupMember | None,
    requested_primary: bool,
    ignore_membership_id: str | None = None,
) -> None:
    if requested_primary and existing_primary and existing_primary.id != ignore_membership_id:
        raise HTTPException(status_code=409, detail="matching_group_primary_conflict")


def _bump_group_versions(
    groups: Iterable[CanonicalProductGroup],
    *,
    operation_type: MatchingOperationType,
    skip_group_ids: Iterable[str] | None = None,
) -> None:
    if not _structural_operation(operation_type):
        return
    skipped = {group_id for group_id in (skip_group_ids or []) if group_id}
    seen: set[str] = set()
    for group in groups:
        if group.id in seen or group.id in skipped:
            continue
        seen.add(group.id)
        group.version_no = int(group.version_no or 1) + 1
        group.updated_at = _utc_now()


async def _complete_operation(
    db: AsyncSession,
    *,
    actor: User,
    request: Request | None,
    operation: MatchingOperation,
    action: str,
    entity: str,
    entity_id: str | None,
    touched_group_ids: Iterable[str],
    touched_product_ids: Iterable[str],
    before_group_states: Sequence[dict[str, Any]],
    before_membership_states: Sequence[dict[str, Any]],
    diff_summary: str,
) -> MatchingOperation:
    await db.flush()
    after_group_states = await _collect_group_states(db, touched_group_ids)
    after_membership_states = await _collect_membership_states(db, touched_product_ids)
    operation.before_snapshot_json = _minimal_snapshot(
        operation_type=operation.operation_type,
        group_states=before_group_states,
        membership_states=before_membership_states,
    )
    operation.after_snapshot_json = _minimal_snapshot(
        operation_type=operation.operation_type,
        group_states=after_group_states,
        membership_states=after_membership_states,
    )
    await _write_snapshot_rows(
        db,
        operation_id=operation.id,
        before_group_states=before_group_states,
        after_group_states=after_group_states,
        before_membership_states=before_membership_states,
        after_membership_states=after_membership_states,
    )
    await _record_dependency_checks(db, operation=operation, product_ids=touched_product_ids)
    await sync_search_projections_for_matching_products(db, product_ids=touched_product_ids)
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        success=True,
        message=operation.reason or action.lower(),
        before=operation.before_snapshot_json,
        after=operation.after_snapshot_json,
        severity=AuditSeverity.INFO,
        reason=operation.reason,
        diff_summary=diff_summary,
    )
    return operation


async def _prepare_snapshots(
    db: AsyncSession,
    *,
    group_ids: Iterable[str],
    product_ids: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    before_group_states = await _collect_group_states(db, group_ids)
    before_membership_states = await _collect_membership_states(db, product_ids)
    return before_group_states, before_membership_states


async def create_canonical_group(
    db: AsyncSession,
    *,
    actor: User | None,
    code: str,
    display_name: str,
    system_name: str | None = None,
    description: str | None = None,
    request: Request | None = None,
) -> CanonicalProductGroup:
    async def _callback() -> CanonicalProductGroup:
        resolved_actor = _ensure_matching_manager(actor)
        normalized_code = _normalize_group_code(code)
        normalized_name = _normalize_group_name(display_name)
        normalized_system_name = _normalize_group_system_name(system_name, fallback=normalized_name)
        await _ensure_group_code_available(db, normalized_code)
        now = _utc_now()
        group = CanonicalProductGroup(
            code=normalized_code,
            display_name=normalized_name,
            system_name=normalized_system_name,
            description=_normalize_group_description(description),
            status=MatchingGroupStatus.ACTIVE,
            lock_state=CanonicalGroupLockState.EDITABLE,
            version_no=1,
            created_by=resolved_actor.id,
            created_at=now,
            updated_at=now,
            archive_reason="",
        )
        db.add(group)
        await db.flush()
        await write_audit_log(
            db,
            request=request,
            actor=resolved_actor,
            action="MATCHING_GROUP_CREATE",
            entity="canonical_product_group",
            entity_id=group.id,
            success=True,
            message=f"Created matching group {group.display_name}",
            before=None,
            after={"group_id": group.id, "code": group.code, "version_no": group.version_no},
            severity=AuditSeverity.INFO,
            reason="create_group",
            diff_summary="matching group created",
        )
        return group

    return await _run_in_single_transaction(db, _callback)


async def change_group_lock_state(
    db: AsyncSession,
    *,
    actor: User | None,
    group_id: str,
    lock_state: str | CanonicalGroupLockState,
    reason: str,
    note: str | None = None,
    request: Request | None = None,
) -> MatchingOperation:
    async def _callback() -> MatchingOperation:
        resolved_actor = _ensure_matching_manager(actor)
        resolved_reason = _require_reason(reason)
        normalized_lock_state = _normalize_lock_state(lock_state)
        group = await _get_group(db, group_id)
        _ensure_lock_change_allowed(actor=resolved_actor, group=group, new_lock_state=normalized_lock_state)
        if group.lock_state == normalized_lock_state:
            raise HTTPException(status_code=409, detail="matching_group_lock_state_unchanged")
        active_memberships = await _get_active_memberships_for_group(db, group.id)
        product_ids = [membership.product_id for membership in active_memberships]
        before_group_states, before_membership_states = await _prepare_snapshots(
            db,
            group_ids=[group.id],
            product_ids=product_ids,
        )
        operation = await _create_operation(
            db,
            actor=resolved_actor,
            operation_type=MatchingOperationType.LOCK_CHANGE,
            reason=resolved_reason,
            note=_normalize_note(note),
            source_group_id=group.id,
            target_group_id=group.id,
        )
        previous_lock_state = group.lock_state
        group.lock_state = normalized_lock_state
        group.last_operation_id = operation.id
        group.updated_at = _utc_now()
        return await _complete_operation(
            db,
            actor=resolved_actor,
            request=request,
            operation=operation,
            action="MATCHING_GROUP_LOCK_CHANGE",
            entity="canonical_product_group",
            entity_id=group.id,
            touched_group_ids=[group.id],
            touched_product_ids=product_ids,
            before_group_states=before_group_states,
            before_membership_states=before_membership_states,
            diff_summary=f"lock_state: {previous_lock_state.value} -> {normalized_lock_state.value}",
        )

    return await _run_in_single_transaction(db, _callback)


async def add_product_to_group(
    db: AsyncSession,
    *,
    actor: User | None,
    group_id: str,
    product_id: str,
    reason: str,
    note: str | None = None,
    is_primary: bool = False,
    request: Request | None = None,
) -> MatchingOperation:
    async def _callback() -> MatchingOperation:
        resolved_actor = _ensure_matching_manager(actor)
        resolved_reason = _require_reason(reason)
        group = await _get_group(db, group_id)
        _ensure_group_editable(group)
        await _get_product(db, product_id)
        existing_membership = await _get_active_membership_for_product(db, product_id)
        if existing_membership:
            if existing_membership.group_id == group.id:
                raise HTTPException(status_code=409, detail="matching_product_already_in_group")
            raise HTTPException(status_code=409, detail="matching_product_already_grouped")
        existing_primary = await _get_active_primary_for_group(db, group.id)
        _validate_primary_conflict(existing_primary=existing_primary, requested_primary=bool(is_primary))
        before_group_states, before_membership_states = await _prepare_snapshots(
            db,
            group_ids=[group.id],
            product_ids=[product_id],
        )
        operation = await _create_operation(
            db,
            actor=resolved_actor,
            operation_type=MatchingOperationType.ADD_PRODUCT,
            reason=resolved_reason,
            note=_normalize_note(note),
            target_group_id=group.id,
        )
        now = _utc_now()
        db.add(
            CanonicalGroupMember(
                group_id=group.id,
                product_id=product_id,
                is_primary=bool(is_primary),
                assigned_at=now,
                assigned_by=resolved_actor.id,
                source_operation_id=operation.id,
                removal_reason="",
                created_by=resolved_actor.id,
                created_at=now,
                updated_at=now,
            )
        )
        group.last_operation_id = operation.id
        _bump_group_versions([group], operation_type=operation.operation_type)
        return await _complete_operation(
            db,
            actor=resolved_actor,
            request=request,
            operation=operation,
            action="MATCHING_GROUP_ADD_PRODUCT",
            entity="canonical_product_group",
            entity_id=group.id,
            touched_group_ids=[group.id],
            touched_product_ids=[product_id],
            before_group_states=before_group_states,
            before_membership_states=before_membership_states,
            diff_summary=f"added product {product_id} to group {group.id}",
        )

    return await _run_in_single_transaction(db, _callback)


async def remove_product_from_group(
    db: AsyncSession,
    *,
    actor: User | None,
    group_id: str,
    product_id: str,
    reason: str,
    note: str | None = None,
    request: Request | None = None,
) -> MatchingOperation:
    async def _callback() -> MatchingOperation:
        resolved_actor = _ensure_matching_manager(actor)
        resolved_reason = _require_reason(reason)
        group = await _get_group(db, group_id)
        _ensure_group_editable(group)
        await _get_product(db, product_id)
        membership = await _get_active_membership_for_product(db, product_id)
        if not membership or membership.group_id != group.id:
            raise HTTPException(status_code=404, detail="matching_membership_not_found")
        before_group_states, before_membership_states = await _prepare_snapshots(
            db,
            group_ids=[group.id],
            product_ids=[product_id],
        )
        operation = await _create_operation(
            db,
            actor=resolved_actor,
            operation_type=MatchingOperationType.REMOVE_PRODUCT,
            reason=resolved_reason,
            note=_normalize_note(note),
            source_group_id=group.id,
        )
        now = _utc_now()
        membership.removed_at = now
        membership.removed_by = resolved_actor.id
        membership.end_operation_id = operation.id
        membership.removal_reason = resolved_reason
        membership.updated_at = now
        group.last_operation_id = operation.id
        _bump_group_versions([group], operation_type=operation.operation_type)
        return await _complete_operation(
            db,
            actor=resolved_actor,
            request=request,
            operation=operation,
            action="MATCHING_GROUP_REMOVE_PRODUCT",
            entity="canonical_product_group",
            entity_id=group.id,
            touched_group_ids=[group.id],
            touched_product_ids=[product_id],
            before_group_states=before_group_states,
            before_membership_states=before_membership_states,
            diff_summary=f"removed product {product_id} from group {group.id}",
        )

    return await _run_in_single_transaction(db, _callback)


async def move_product_between_groups(
    db: AsyncSession,
    *,
    actor: User | None,
    source_group_id: str,
    target_group_id: str,
    product_id: str,
    reason: str,
    note: str | None = None,
    is_primary: bool | None = None,
    request: Request | None = None,
) -> MatchingOperation:
    async def _callback() -> MatchingOperation:
        resolved_actor = _ensure_matching_manager(actor)
        resolved_reason = _require_reason(reason)
        if source_group_id == target_group_id:
            raise HTTPException(status_code=400, detail="matching_move_requires_distinct_groups")
        source_group = await _get_group(db, source_group_id)
        target_group = await _get_group(db, target_group_id)
        _ensure_group_editable(source_group)
        _ensure_group_editable(target_group)
        await _get_product(db, product_id)
        membership = await _get_active_membership_for_product(db, product_id)
        if not membership or membership.group_id != source_group.id:
            raise HTTPException(status_code=404, detail="matching_membership_not_found")
        target_primary = await _get_active_primary_for_group(db, target_group.id)
        requested_primary = membership.is_primary if is_primary is None else bool(is_primary)
        _validate_primary_conflict(existing_primary=target_primary, requested_primary=requested_primary)
        before_group_states, before_membership_states = await _prepare_snapshots(
            db,
            group_ids=[source_group.id, target_group.id],
            product_ids=[product_id],
        )
        operation = await _create_operation(
            db,
            actor=resolved_actor,
            operation_type=MatchingOperationType.MOVE_PRODUCT,
            reason=resolved_reason,
            note=_normalize_note(note),
            source_group_id=source_group.id,
            target_group_id=target_group.id,
        )
        now = _utc_now()
        membership.removed_at = now
        membership.removed_by = resolved_actor.id
        membership.end_operation_id = operation.id
        membership.removal_reason = resolved_reason
        membership.updated_at = now
        db.add(
            CanonicalGroupMember(
                group_id=target_group.id,
                product_id=product_id,
                is_primary=requested_primary,
                assigned_at=now,
                assigned_by=resolved_actor.id,
                source_operation_id=operation.id,
                removal_reason="",
                created_by=resolved_actor.id,
                created_at=now,
                updated_at=now,
            )
        )
        source_group.last_operation_id = operation.id
        target_group.last_operation_id = operation.id
        _bump_group_versions([source_group, target_group], operation_type=operation.operation_type)
        return await _complete_operation(
            db,
            actor=resolved_actor,
            request=request,
            operation=operation,
            action="MATCHING_GROUP_MOVE_PRODUCT",
            entity="canonical_product_group",
            entity_id=target_group.id,
            touched_group_ids=[source_group.id, target_group.id],
            touched_product_ids=[product_id],
            before_group_states=before_group_states,
            before_membership_states=before_membership_states,
            diff_summary=f"moved product {product_id} from group {source_group.id} to {target_group.id}",
        )

    return await _run_in_single_transaction(db, _callback)


async def merge_groups(
    db: AsyncSession,
    *,
    actor: User | None,
    source_group_ids: Iterable[str],
    target_group_id: str,
    reason: str,
    note: str | None = None,
    request: Request | None = None,
) -> MatchingOperation:
    async def _callback() -> MatchingOperation:
        resolved_actor = _ensure_matching_manager(actor)
        resolved_reason = _require_reason(reason)
        unique_source_group_ids = _normalize_ids(source_group_ids)
        if not unique_source_group_ids:
            raise HTTPException(status_code=400, detail="matching_merge_source_groups_required")
        if target_group_id in unique_source_group_ids:
            raise HTTPException(status_code=400, detail="matching_merge_target_in_sources")
        target_group = await _get_group(db, target_group_id)
        _ensure_group_editable(target_group)
        source_groups = [await _get_group(db, group_id) for group_id in unique_source_group_ids]
        for source_group in source_groups:
            _ensure_group_editable(source_group)
        target_memberships = await _get_active_memberships_for_group(db, target_group.id)
        target_primary = next((membership for membership in target_memberships if membership.is_primary), None)
        source_memberships: list[CanonicalGroupMember] = []
        source_primaries: list[CanonicalGroupMember] = []
        for source_group in source_groups:
            memberships = await _get_active_memberships_for_group(db, source_group.id)
            source_memberships.extend(memberships)
            source_primaries.extend([membership for membership in memberships if membership.is_primary])
        if target_primary and source_primaries:
            raise HTTPException(status_code=409, detail="matching_group_primary_conflict")
        if len(source_primaries) > 1:
            raise HTTPException(status_code=409, detail="matching_group_primary_conflict")
        touched_group_ids = [target_group.id, *unique_source_group_ids]
        touched_product_ids = [membership.product_id for membership in target_memberships] + [
            membership.product_id for membership in source_memberships
        ]
        before_group_states, before_membership_states = await _prepare_snapshots(
            db,
            group_ids=touched_group_ids,
            product_ids=touched_product_ids,
        )
        operation = await _create_operation(
            db,
            actor=resolved_actor,
            operation_type=MatchingOperationType.MERGE_GROUPS,
            reason=resolved_reason,
            note=_normalize_note(note),
            source_group_id=unique_source_group_ids[0] if len(unique_source_group_ids) == 1 else None,
            target_group_id=target_group.id,
        )
        now = _utc_now()
        for membership in source_memberships:
            membership.removed_at = now
            membership.removed_by = resolved_actor.id
            membership.end_operation_id = operation.id
            membership.removal_reason = resolved_reason
            membership.updated_at = now
            db.add(
                CanonicalGroupMember(
                    group_id=target_group.id,
                    product_id=membership.product_id,
                    is_primary=membership.is_primary,
                    assigned_at=now,
                    assigned_by=resolved_actor.id,
                    source_operation_id=operation.id,
                    removal_reason="",
                    created_by=resolved_actor.id,
                    created_at=now,
                    updated_at=now,
                )
            )
        target_group.last_operation_id = operation.id
        target_group.updated_at = now
        for source_group in source_groups:
            source_group.status = MatchingGroupStatus.ARCHIVED
            source_group.archived_at = now
            source_group.archived_by = resolved_actor.id
            source_group.archive_reason = resolved_reason
            source_group.merged_into_group_id = target_group.id
            source_group.last_operation_id = operation.id
            source_group.updated_at = now
        _bump_group_versions([target_group, *source_groups], operation_type=operation.operation_type)
        return await _complete_operation(
            db,
            actor=resolved_actor,
            request=request,
            operation=operation,
            action="MATCHING_GROUP_MERGE",
            entity="canonical_product_group",
            entity_id=target_group.id,
            touched_group_ids=touched_group_ids,
            touched_product_ids=touched_product_ids,
            before_group_states=before_group_states,
            before_membership_states=before_membership_states,
            diff_summary=f"merged groups {', '.join(unique_source_group_ids)} into {target_group.id}",
        )

    return await _run_in_single_transaction(db, _callback)


async def split_group(
    db: AsyncSession,
    *,
    actor: User | None,
    source_group_id: str,
    product_ids: Iterable[str],
    new_group_code: str,
    new_group_name: str,
    reason: str,
    note: str | None = None,
    new_group_system_name: str | None = None,
    new_group_description: str | None = None,
    request: Request | None = None,
) -> MatchingOperation:
    async def _callback() -> MatchingOperation:
        resolved_actor = _ensure_matching_manager(actor)
        resolved_reason = _require_reason(reason)
        source_group = await _get_group(db, source_group_id)
        _ensure_group_editable(source_group)
        selected_product_ids = _normalize_ids(product_ids)
        if not selected_product_ids:
            raise HTTPException(status_code=400, detail="matching_split_products_required")
        normalized_code = _normalize_group_code(new_group_code)
        normalized_name = _normalize_group_name(new_group_name)
        normalized_system_name = _normalize_group_system_name(new_group_system_name, fallback=normalized_name)
        await _ensure_group_code_available(db, normalized_code)
        active_memberships = await _get_active_memberships_for_group(db, source_group.id)
        memberships_by_product = {membership.product_id: membership for membership in active_memberships}
        memberships_to_move: list[CanonicalGroupMember] = []
        for product_id in selected_product_ids:
            await _get_product(db, product_id)
            membership = memberships_by_product.get(product_id)
            if membership is None:
                raise HTTPException(status_code=404, detail="matching_membership_not_found")
            memberships_to_move.append(membership)
        before_group_states, before_membership_states = await _prepare_snapshots(
            db,
            group_ids=[source_group.id],
            product_ids=selected_product_ids,
        )
        now = _utc_now()
        new_group = CanonicalProductGroup(
            code=normalized_code,
            display_name=normalized_name,
            system_name=normalized_system_name,
            description=_normalize_group_description(new_group_description),
            status=MatchingGroupStatus.ACTIVE,
            lock_state=CanonicalGroupLockState.EDITABLE,
            version_no=1,
            created_by=resolved_actor.id,
            created_at=now,
            updated_at=now,
            archive_reason="",
        )
        db.add(new_group)
        await db.flush()
        touched_group_ids = [source_group.id, new_group.id]
        operation = await _create_operation(
            db,
            actor=resolved_actor,
            operation_type=MatchingOperationType.SPLIT_GROUP,
            reason=resolved_reason,
            note=_normalize_note(note),
            source_group_id=source_group.id,
            target_group_id=new_group.id,
        )
        for membership in memberships_to_move:
            membership.removed_at = now
            membership.removed_by = resolved_actor.id
            membership.end_operation_id = operation.id
            membership.removal_reason = resolved_reason
            membership.updated_at = now
            db.add(
                CanonicalGroupMember(
                    group_id=new_group.id,
                    product_id=membership.product_id,
                    is_primary=membership.is_primary,
                    assigned_at=now,
                    assigned_by=resolved_actor.id,
                    source_operation_id=operation.id,
                    removal_reason="",
                    created_by=resolved_actor.id,
                    created_at=now,
                    updated_at=now,
                )
            )
        source_group.last_operation_id = operation.id
        source_group.updated_at = now
        new_group.last_operation_id = operation.id
        new_group.updated_at = now
        _bump_group_versions(
            [source_group, new_group],
            operation_type=operation.operation_type,
            skip_group_ids=[new_group.id],
        )
        return await _complete_operation(
            db,
            actor=resolved_actor,
            request=request,
            operation=operation,
            action="MATCHING_GROUP_SPLIT",
            entity="canonical_product_group",
            entity_id=source_group.id,
            touched_group_ids=touched_group_ids,
            touched_product_ids=selected_product_ids,
            before_group_states=before_group_states,
            before_membership_states=before_membership_states,
            diff_summary=f"split {len(selected_product_ids)} product(s) from group {source_group.id} into {new_group.id}",
        )

    return await _run_in_single_transaction(db, _callback)
