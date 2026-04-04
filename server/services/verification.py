from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any
import uuid

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import (
    AuditSeverity,
    Role,
    User,
    VerificationAction,
    VerificationActionType,
    VerificationApprovalStrategy,
    VerificationAssignment,
    VerificationAssignmentSource,
    VerificationDependencyWarning,
    VerificationEscalation,
    VerificationEscalationAlertState,
    VerificationEscalationType,
    VerificationRequest,
    VerificationRequestItem,
    VerificationRiskLevel,
    VerificationSafetyStatus,
    VerificationWorkflowStatus,
)
from server.services.audit import write_audit_log
from server.services.notifications import publish_verification_notification
from server.services.search import sync_verification_queue_projection
from server.services.snapshots import create_verification_approval_snapshot


VerificationApplyHandler = Callable[..., Awaitable[dict[str, Any] | None]]

VERIFYING_ROLES = {Role.DEV, Role.OWNER}
PROTECTED_CHANGE_CREATOR_ROLES = {Role.ADMIN, Role.DEV, Role.OWNER}
STRICT_STATUS_TRANSITIONS: dict[VerificationWorkflowStatus, set[VerificationWorkflowStatus]] = {
    VerificationWorkflowStatus.PENDING: {
        VerificationWorkflowStatus.APPROVED,
        VerificationWorkflowStatus.REJECTED,
        VerificationWorkflowStatus.RETURNED_FOR_REVISION,
        VerificationWorkflowStatus.CANCELLED,
    },
    VerificationWorkflowStatus.APPROVED: set(),
    VerificationWorkflowStatus.REJECTED: set(),
    VerificationWorkflowStatus.RETURNED_FOR_REVISION: set(),
    VerificationWorkflowStatus.CANCELLED: set(),
}
_APPROVAL_HANDLERS: dict[str, VerificationApplyHandler] = {}


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


def register_verification_handler(handler_key: str, handler: VerificationApplyHandler) -> None:
    key = _normalize_required_string(handler_key, field_name="verification_handler_key", max_length=128)
    _APPROVAL_HANDLERS[key] = handler


def clear_verification_handlers() -> None:
    _APPROVAL_HANDLERS.clear()


def map_risk_score_to_level(score: int) -> VerificationRiskLevel:
    if score < 0 or score > 100:
        raise HTTPException(status_code=400, detail="verification_risk_score_out_of_range")
    if score >= 75:
        return VerificationRiskLevel.CRITICAL
    if score >= 50:
        return VerificationRiskLevel.HIGH
    if score >= 25:
        return VerificationRiskLevel.MEDIUM
    return VerificationRiskLevel.LOW


def _normalize_risk_score(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid_verification_risk_score") from exc
    if score < 0 or score > 100:
        raise HTTPException(status_code=400, detail="verification_risk_score_out_of_range")
    return score


def _normalize_risk_level(value: Any, *, score: int | None = None) -> VerificationRiskLevel:
    if score is not None:
        mapped = map_risk_score_to_level(score)
        if value in (None, ""):
            return mapped
        try:
            candidate = VerificationRiskLevel(str(value).strip().lower())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid_verification_risk_level") from exc
        if candidate != mapped:
            raise HTTPException(status_code=400, detail="verification_risk_level_score_mismatch")
        return candidate
    try:
        return VerificationRiskLevel(str(value or VerificationRiskLevel.LOW.value).strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_verification_risk_level") from exc


def _normalize_safety_status(value: Any) -> VerificationSafetyStatus:
    try:
        return VerificationSafetyStatus(str(value or VerificationSafetyStatus.SAFE.value).strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_verification_safety_status") from exc


def _severity_rank(status: VerificationSafetyStatus) -> int:
    if status == VerificationSafetyStatus.BLOCKED:
        return 2
    if status == VerificationSafetyStatus.WARNING:
        return 1
    return 0


def _max_safety_status(values: Iterable[VerificationSafetyStatus]) -> VerificationSafetyStatus:
    resolved = VerificationSafetyStatus.SAFE
    for value in values:
        if _severity_rank(value) > _severity_rank(resolved):
            resolved = value
    return resolved


def _normalize_required_string(value: Any, *, field_name: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name}_required")
    return normalized[:max_length]


def _normalize_optional_string(value: Any, *, max_length: int) -> str:
    return str(value or "").strip()[:max_length]


def _normalize_reason(value: Any) -> str:
    return _normalize_required_string(value, field_name="verification_reason", max_length=2000)


def _normalize_role_value(value: Any, *, allow_none: bool = True) -> str | None:
    if value in (None, ""):
        if allow_none:
            return None
        raise HTTPException(status_code=400, detail="verification_role_required")
    try:
        role = Role(str(value).strip().upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_verification_role") from exc
    if role not in VERIFYING_ROLES:
        raise HTTPException(status_code=400, detail="verification_assignee_role_invalid")
    return role.value


def _normalize_approval_strategy(value: Any) -> VerificationApprovalStrategy:
    try:
        return VerificationApprovalStrategy(
            str(value or VerificationApprovalStrategy.DOMAIN_HANDLER.value).strip().lower()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_verification_approval_strategy") from exc


def _normalize_non_negative_int(value: Any, *, field_name: str) -> int:
    try:
        normalized = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid_{field_name}") from exc
    if normalized < 0:
        raise HTTPException(status_code=400, detail=f"{field_name}_non_negative_required")
    return normalized


def _normalize_sla_deadline(value: Any, *, now: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return now + timedelta(hours=2)


def _build_request_code() -> str:
    return f"VR-{uuid.uuid4().hex[:12].upper()}"


def _ensure_request_submitter(actor: User | None) -> User:
    if actor is None or actor.role not in PROTECTED_CHANGE_CREATOR_ROLES:
        raise HTTPException(status_code=403, detail="verification_submit_permission_denied")
    return actor


def _ensure_verifier(actor: User | None) -> User:
    if actor is None or actor.role not in VERIFYING_ROLES:
        raise HTTPException(status_code=403, detail="verification_permission_denied")
    return actor


def _ensure_transition_allowed(
    current_status: VerificationWorkflowStatus,
    target_status: VerificationWorkflowStatus,
) -> None:
    if target_status not in STRICT_STATUS_TRANSITIONS.get(current_status, set()):
        raise HTTPException(status_code=409, detail="verification_invalid_status_transition")


async def _get_request(db: AsyncSession, request_id: str) -> VerificationRequest:
    request_record = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
    if request_record is None:
        raise HTTPException(status_code=404, detail="verification_request_not_found")
    return request_record


async def _get_request_items(db: AsyncSession, request_id: str) -> list[VerificationRequestItem]:
    return (
        await db.execute(
            select(VerificationRequestItem)
            .where(VerificationRequestItem.request_id == request_id)
            .order_by(VerificationRequestItem.sequence_no.asc())
        )
    ).scalars().all()


async def _get_dependency_warnings(db: AsyncSession, request_id: str) -> list[VerificationDependencyWarning]:
    return (
        await db.execute(
            select(VerificationDependencyWarning).where(VerificationDependencyWarning.request_id == request_id)
        )
    ).scalars().all()


def serialize_verification_request(request_record: VerificationRequest) -> dict[str, Any]:
    return {
        "id": request_record.id,
        "request_code": request_record.request_code,
        "workflow_status": request_record.workflow_status.value,
        "risk_level": request_record.risk_level.value,
        "risk_score": request_record.risk_score,
        "subject_domain": request_record.subject_domain,
        "queue_key": request_record.queue_key,
        "priority_rank": request_record.priority_rank,
        "safety_status": request_record.safety_status.value,
        "branch_id": request_record.branch_id,
        "assignee_user_id": request_record.assignee_user_id,
        "item_count": request_record.item_count,
        "dependency_warning_count": request_record.dependency_warning_count,
        "current_escalation_level": request_record.current_escalation_level,
        "sla_deadline_at": request_record.sla_deadline_at.isoformat() if request_record.sla_deadline_at else None,
        "first_overdue_at": request_record.first_overdue_at.isoformat() if request_record.first_overdue_at else None,
        "last_escalated_at": request_record.last_escalated_at.isoformat() if request_record.last_escalated_at else None,
        "resolved_at": request_record.resolved_at.isoformat() if request_record.resolved_at else None,
        "cancelled_at": request_record.cancelled_at.isoformat() if request_record.cancelled_at else None,
    }


def serialize_verification_item(item: VerificationRequestItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "request_id": item.request_id,
        "sequence_no": item.sequence_no,
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "subject_key": item.subject_key,
        "change_type": item.change_type,
        "handler_key": item.handler_key,
        "entity_version_token": item.entity_version_token,
        "approval_strategy": item.approval_strategy.value,
        "branch_id": item.branch_id,
        "risk_level": item.risk_level.value,
        "safety_status": item.safety_status.value,
        "diff_summary": item.diff_summary,
    }


def _minimal_request_snapshot(
    request_record: VerificationRequest,
    *,
    item_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    snapshot = serialize_verification_request(request_record)
    if item_ids is not None:
        snapshot["item_ids"] = list(item_ids)
    return snapshot


async def _add_action(
    db: AsyncSession,
    *,
    request_record: VerificationRequest,
    action_type: VerificationActionType,
    actor: User | None,
    action_reason: str,
    comment: str = "",
    decision_summary: str = "",
    metadata: dict[str, Any] | None = None,
    from_status: VerificationWorkflowStatus | None = None,
    to_status: VerificationWorkflowStatus | None = None,
    request_item_id: str | None = None,
) -> VerificationAction:
    action = VerificationAction(
        request_id=request_record.id,
        request_item_id=request_item_id,
        action_type=action_type,
        actor_user_id=actor.id if actor else None,
        from_status=from_status,
        to_status=to_status,
        action_reason=action_reason,
        comment=comment,
        decision_summary=decision_summary,
        escalation_level_after=int(request_record.current_escalation_level or 0),
        metadata_json=metadata or {},
        created_at=_utc_now(),
    )
    db.add(action)
    await db.flush()
    return action


async def _replace_current_assignment(
    db: AsyncSession,
    *,
    request_record: VerificationRequest,
    assigned_to_user_id: str | None,
    assigned_role: str | None,
    actor: User | None,
    source: VerificationAssignmentSource,
    reason: str,
    now: datetime,
) -> tuple[VerificationAssignment | None, VerificationAssignment]:
    existing = await db.scalar(
        select(VerificationAssignment).where(
            VerificationAssignment.request_id == request_record.id,
            VerificationAssignment.is_current.is_(True),
            VerificationAssignment.ended_at.is_(None),
        )
    )
    if existing is not None:
        existing.is_current = False
        existing.ended_at = now
    assignment = VerificationAssignment(
        request_id=request_record.id,
        assigned_to_user_id=assigned_to_user_id,
        assigned_role=assigned_role,
        assigned_by_user_id=actor.id if actor else None,
        assignment_source=source,
        assignment_reason=reason,
        started_at=now,
        is_current=True,
    )
    db.add(assignment)
    request_record.assignee_user_id = assigned_to_user_id
    return existing, assignment


async def _write_dependency_warnings(
    db: AsyncSession,
    *,
    request_id: str,
    warnings: Sequence[dict[str, Any]],
    default_safety: VerificationSafetyStatus,
    created_at: datetime,
) -> list[VerificationDependencyWarning]:
    rows: list[VerificationDependencyWarning] = []
    for warning in warnings:
        row = VerificationDependencyWarning(
            request_id=request_id,
            request_item_id=warning.get("request_item_id"),
            dependency_type=_normalize_required_string(
                warning.get("dependency_type"),
                field_name="verification_dependency_type",
                max_length=64,
            ),
            dependency_entity_type=_normalize_optional_string(warning.get("dependency_entity_type"), max_length=64) or None,
            dependency_entity_id=_normalize_optional_string(warning.get("dependency_entity_id"), max_length=36) or None,
            safety_status=_normalize_safety_status(warning.get("safety_status") or default_safety.value),
            message=_normalize_required_string(
                warning.get("message"),
                field_name="verification_dependency_message",
                max_length=2000,
            ),
            detail_json=warning.get("detail_json") or {},
            created_at=created_at,
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


def _resolve_request_safety(
    request_safety: VerificationSafetyStatus,
    items: Sequence[dict[str, Any]],
    dependency_warnings: Sequence[dict[str, Any]],
) -> VerificationSafetyStatus:
    statuses = [request_safety]
    statuses.extend(
        _normalize_safety_status(item.get("safety_status") or VerificationSafetyStatus.SAFE.value) for item in items
    )
    statuses.extend(
        _normalize_safety_status(item.get("safety_status") or VerificationSafetyStatus.WARNING.value)
        for item in dependency_warnings
    )
    return _max_safety_status(statuses)


async def create_verification_request(
    db: AsyncSession,
    *,
    actor: User | None,
    payload: dict[str, Any],
    request: Request | None = None,
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_request_submitter(actor)
        now = _utc_now()
        items_payload = payload.get("items")
        if not isinstance(items_payload, list) or not items_payload:
            raise HTTPException(status_code=400, detail="verification_items_required")
        risk_score = _normalize_risk_score(payload.get("risk_score"))
        risk_level = _normalize_risk_level(payload.get("risk_level"), score=risk_score)
        request_safety = _normalize_safety_status(payload.get("safety_status"))
        dependency_payload = payload.get("dependency_warnings") or []
        if not isinstance(dependency_payload, list):
            raise HTTPException(status_code=400, detail="verification_dependency_warnings_invalid")
        resolved_safety = _resolve_request_safety(request_safety, items_payload, dependency_payload)
        dedupe_key = _normalize_optional_string(payload.get("dedupe_key"), max_length=255) or None
        if dedupe_key:
            existing = await db.scalar(
                select(VerificationRequest).where(
                    VerificationRequest.dedupe_key == dedupe_key,
                    VerificationRequest.workflow_status == VerificationWorkflowStatus.PENDING,
                )
            )
            if existing is not None:
                raise HTTPException(status_code=409, detail="verification_pending_dedupe_conflict")
        subject_domain = _normalize_required_string(
            payload.get("subject_domain"),
            field_name="verification_subject_domain",
            max_length=64,
        )
        request_record = VerificationRequest(
            request_code=_normalize_optional_string(payload.get("request_code"), max_length=32) or _build_request_code(),
            workflow_status=VerificationWorkflowStatus.PENDING,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_flags_json=payload.get("risk_flags_json") or [],
            subject_domain=subject_domain,
            queue_key=_normalize_optional_string(payload.get("queue_key"), max_length=64) or subject_domain,
            priority_rank=_normalize_non_negative_int(payload.get("priority_rank"), field_name="verification_priority_rank"),
            safety_status=resolved_safety,
            change_summary=_normalize_required_string(
                payload.get("change_summary"),
                field_name="verification_change_summary",
                max_length=4000,
            ),
            request_reason=_normalize_reason(payload.get("request_reason")),
            branch_id=_normalize_optional_string(payload.get("branch_id"), max_length=36) or None,
            requested_by_user_id=resolved_actor.id,
            submitted_by_user_id=resolved_actor.id,
            assignee_user_id=None,
            supersedes_request_id=_normalize_optional_string(payload.get("supersedes_request_id"), max_length=36) or None,
            origin_type=_normalize_optional_string(payload.get("origin_type"), max_length=64) or None,
            origin_id=_normalize_optional_string(payload.get("origin_id"), max_length=36) or None,
            dedupe_key=dedupe_key,
            item_count=len(items_payload),
            dependency_warning_count=len(dependency_payload),
            current_escalation_level=0,
            sla_deadline_at=_normalize_sla_deadline(payload.get("sla_deadline_at"), now=now),
            last_action_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(request_record)
        await db.flush()

        created_items: list[VerificationRequestItem] = []
        for index, item_payload in enumerate(items_payload, start=1):
            if not isinstance(item_payload, dict):
                raise HTTPException(status_code=400, detail="verification_item_payload_invalid")
            item = VerificationRequestItem(
                request_id=request_record.id,
                sequence_no=index,
                entity_type=_normalize_required_string(
                    item_payload.get("entity_type"),
                    field_name="verification_item_entity_type",
                    max_length=64,
                ),
                entity_id=_normalize_optional_string(item_payload.get("entity_id"), max_length=36) or None,
                subject_key=_normalize_optional_string(item_payload.get("subject_key"), max_length=128) or None,
                change_type=_normalize_required_string(
                    item_payload.get("change_type"),
                    field_name="verification_item_change_type",
                    max_length=64,
                ),
                handler_key=_normalize_required_string(
                    item_payload.get("handler_key"),
                    field_name="verification_item_handler_key",
                    max_length=128,
                ),
                entity_version_token=_normalize_optional_string(item_payload.get("entity_version_token"), max_length=128) or None,
                approval_strategy=_normalize_approval_strategy(item_payload.get("approval_strategy")),
                branch_id=_normalize_optional_string(item_payload.get("branch_id"), max_length=36) or request_record.branch_id,
                risk_level=_normalize_risk_level(item_payload.get("risk_level") or risk_level.value),
                safety_status=_normalize_safety_status(item_payload.get("safety_status") or VerificationSafetyStatus.SAFE.value),
                before_json=item_payload.get("before_json"),
                proposed_after_json=item_payload.get("proposed_after_json"),
                handler_payload_json=item_payload.get("handler_payload_json") or {},
                diff_summary=_normalize_required_string(
                    item_payload.get("diff_summary"),
                    field_name="verification_item_diff_summary",
                    max_length=4000,
                ),
                created_at=now,
            )
            db.add(item)
            created_items.append(item)
        await db.flush()

        warnings = await _write_dependency_warnings(
            db,
            request_id=request_record.id,
            warnings=dependency_payload,
            default_safety=VerificationSafetyStatus.WARNING,
            created_at=now,
        )

        initial_assignee_user_id = _normalize_optional_string(payload.get("assignee_user_id"), max_length=36) or None
        initial_assigned_role = _normalize_role_value(payload.get("assigned_role"), allow_none=True)
        if initial_assignee_user_id or initial_assigned_role:
            await _replace_current_assignment(
                db,
                request_record=request_record,
                assigned_to_user_id=initial_assignee_user_id,
                assigned_role=initial_assigned_role,
                actor=resolved_actor,
                source=VerificationAssignmentSource.QUEUE_DEFAULT,
                reason="initial_assignment",
                now=now,
            )

        item_ids = [item.id for item in created_items]
        metadata = {
            "item_ids": item_ids,
            "dependency_warning_ids": [warning.id for warning in warnings],
        }
        await _add_action(
            db,
            request_record=request_record,
            action_type=VerificationActionType.SUBMIT,
            actor=resolved_actor,
            action_reason=request_record.request_reason,
            decision_summary="verification_request_submitted",
            metadata=metadata,
            from_status=None,
            to_status=VerificationWorkflowStatus.PENDING,
        )
        await write_audit_log(
            db,
            request=request,
            actor=resolved_actor,
            action="VERIFICATION_REQUEST_CREATE",
            entity="verification_request",
            entity_id=request_record.id,
            success=True,
            message="verification_request_created",
            before=None,
            after=_minimal_request_snapshot(request_record, item_ids=item_ids),
            branch_id=request_record.branch_id,
            severity=AuditSeverity.INFO,
            reason=request_record.request_reason,
            diff_summary=request_record.change_summary,
            metadata=metadata,
        )
        await publish_verification_notification(
            db,
            event_type="verification.request_submitted",
            request_id=request_record.id,
            request_code=request_record.request_code,
            branch_id=request_record.branch_id,
            severity=request_record.risk_level.value,
            triggered_by_user_id=resolved_actor.id,
            assignee_user_id=request_record.assignee_user_id,
            assignee_role=initial_assigned_role,
            workflow_status=request_record.workflow_status.value,
            risk_level=request_record.risk_level.value,
        )
        await sync_verification_queue_projection(db, request_id=request_record.id)
        return request_record

    return await _run_in_single_transaction(db, _callback)


async def assign_verification_request(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None,
    assigned_to_user_id: str | None,
    assigned_role: str | None,
    reason: str,
    request: Request | None = None,
    source: VerificationAssignmentSource = VerificationAssignmentSource.MANUAL,
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_verifier(actor)
        request_record = await _get_request(db, request_id)
        if request_record.workflow_status != VerificationWorkflowStatus.PENDING:
            raise HTTPException(status_code=409, detail="verification_request_not_pending")
        now = _utc_now()
        normalized_reason = _normalize_reason(reason)
        target_role = _normalize_role_value(assigned_role, allow_none=True)
        before = _minimal_request_snapshot(request_record)
        existing, assignment = await _replace_current_assignment(
            db,
            request_record=request_record,
            assigned_to_user_id=_normalize_optional_string(assigned_to_user_id, max_length=36) or None,
            assigned_role=target_role,
            actor=resolved_actor,
            source=source,
            reason=normalized_reason,
            now=now,
        )
        request_record.last_action_at = now
        request_record.updated_at = now
        metadata = {
            "previous_assignment_id": existing.id if existing else None,
            "new_assignment_id": assignment.id,
            "assigned_to_user_id": assignment.assigned_to_user_id,
            "assigned_role": assignment.assigned_role,
        }
        await _add_action(
            db,
            request_record=request_record,
            action_type=VerificationActionType.REASSIGN if existing else VerificationActionType.ASSIGN,
            actor=resolved_actor,
            action_reason=normalized_reason,
            decision_summary="verification_request_assigned",
            metadata=metadata,
            from_status=request_record.workflow_status,
            to_status=request_record.workflow_status,
        )
        await write_audit_log(
            db,
            request=request,
            actor=resolved_actor,
            action="VERIFICATION_REQUEST_ASSIGN",
            entity="verification_request",
            entity_id=request_record.id,
            success=True,
            message="verification_request_assigned",
            before=before,
            after=_minimal_request_snapshot(request_record),
            branch_id=request_record.branch_id,
            severity=AuditSeverity.INFO,
            reason=normalized_reason,
            diff_summary="verification assignment updated",
            metadata=metadata,
        )
        await publish_verification_notification(
            db,
            event_type="verification.request_assigned",
            request_id=request_record.id,
            request_code=request_record.request_code,
            branch_id=request_record.branch_id,
            severity=request_record.risk_level.value,
            triggered_by_user_id=resolved_actor.id,
            assignee_user_id=assignment.assigned_to_user_id,
            assignee_role=assignment.assigned_role,
            workflow_status=request_record.workflow_status.value,
            risk_level=request_record.risk_level.value,
        )
        await sync_verification_queue_projection(db, request_id=request_record.id)
        return request_record

    return await _run_in_single_transaction(db, _callback)


async def escalate_verification_request(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None,
    reason: str,
    escalation_type: VerificationEscalationType = VerificationEscalationType.MANUAL_ESCALATE,
    target_role: str | None = None,
    new_assignee_user_id: str | None = None,
    request: Request | None = None,
    notification_hint_json: dict[str, Any] | None = None,
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_verifier(actor) if actor is not None else None
        request_record = await _get_request(db, request_id)
        if request_record.workflow_status != VerificationWorkflowStatus.PENDING:
            raise HTTPException(status_code=409, detail="verification_request_not_pending")
        now = _utc_now()
        normalized_reason = _normalize_reason(reason)
        before = _minimal_request_snapshot(request_record)
        previous_assignee = request_record.assignee_user_id
        request_record.current_escalation_level = int(request_record.current_escalation_level or 0) + 1
        request_record.last_escalated_at = now
        request_record.last_action_at = now
        request_record.updated_at = now
        if request_record.first_overdue_at is None and now > request_record.sla_deadline_at:
            request_record.first_overdue_at = now
        normalized_target_role = _normalize_role_value(target_role, allow_none=True)
        if new_assignee_user_id or normalized_target_role:
            await _replace_current_assignment(
                db,
                request_record=request_record,
                assigned_to_user_id=_normalize_optional_string(new_assignee_user_id, max_length=36) or None,
                assigned_role=normalized_target_role,
                actor=resolved_actor,
                source=VerificationAssignmentSource.ESCALATION,
                reason=normalized_reason,
                now=now,
            )
        escalation = VerificationEscalation(
            request_id=request_record.id,
            escalation_type=escalation_type,
            escalation_level=request_record.current_escalation_level,
            triggered_by_user_id=resolved_actor.id if resolved_actor else None,
            previous_assignee_user_id=previous_assignee,
            new_assignee_user_id=request_record.assignee_user_id,
            target_role=normalized_target_role,
            alert_state=VerificationEscalationAlertState.PENDING,
            notification_hint_json=notification_hint_json or {},
            triggered_at=now,
        )
        db.add(escalation)
        await db.flush()
        metadata = {
            "escalation_id": escalation.id,
            "escalation_type": escalation.escalation_type.value,
            "current_escalation_level": request_record.current_escalation_level,
        }
        await _add_action(
            db,
            request_record=request_record,
            action_type=VerificationActionType.ESCALATE,
            actor=resolved_actor,
            action_reason=normalized_reason,
            decision_summary="verification_request_escalated",
            metadata=metadata,
            from_status=request_record.workflow_status,
            to_status=request_record.workflow_status,
        )
        await write_audit_log(
            db,
            request=request,
            actor=resolved_actor,
            action="VERIFICATION_REQUEST_ESCALATE",
            entity="verification_request",
            entity_id=request_record.id,
            success=True,
            message="verification_request_escalated",
            before=before,
            after=_minimal_request_snapshot(request_record),
            branch_id=request_record.branch_id,
            severity=AuditSeverity.WARNING,
            reason=normalized_reason,
            diff_summary="verification escalation updated",
            metadata=metadata,
        )
        await publish_verification_notification(
            db,
            event_type="verification.request_escalated",
            request_id=request_record.id,
            request_code=request_record.request_code,
            branch_id=request_record.branch_id,
            severity="high" if request_record.risk_level != VerificationRiskLevel.CRITICAL else "critical",
            triggered_by_user_id=resolved_actor.id if resolved_actor else None,
            assignee_user_id=request_record.assignee_user_id,
            assignee_role=normalized_target_role,
            workflow_status=request_record.workflow_status.value,
            risk_level=request_record.risk_level.value,
        )
        await sync_verification_queue_projection(db, request_id=request_record.id)
        return request_record

    return await _run_in_single_transaction(db, _callback)


async def mark_verification_request_overdue(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None = None,
    request: Request | None = None,
    comment: str = "",
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        request_record = await _get_request(db, request_id)
        if request_record.workflow_status != VerificationWorkflowStatus.PENDING:
            raise HTTPException(status_code=409, detail="verification_request_not_pending")
        now = _utc_now()
        if now <= request_record.sla_deadline_at:
            raise HTTPException(status_code=409, detail="verification_request_not_overdue")
        before = _minimal_request_snapshot(request_record)
        if request_record.first_overdue_at is None:
            request_record.first_overdue_at = now
        request_record.last_action_at = now
        request_record.updated_at = now
        metadata = {"sla_deadline_at": request_record.sla_deadline_at.isoformat()}
        await _add_action(
            db,
            request_record=request_record,
            action_type=VerificationActionType.MARK_OVERDUE,
            actor=actor,
            action_reason="verification_request_overdue",
            comment=_normalize_optional_string(comment, max_length=2000),
            decision_summary="verification_request_marked_overdue",
            metadata=metadata,
            from_status=request_record.workflow_status,
            to_status=request_record.workflow_status,
        )
        await write_audit_log(
            db,
            request=request,
            actor=actor,
            action="VERIFICATION_REQUEST_OVERDUE",
            entity="verification_request",
            entity_id=request_record.id,
            success=True,
            message="verification_request_marked_overdue",
            before=before,
            after=_minimal_request_snapshot(request_record),
            branch_id=request_record.branch_id,
            severity=AuditSeverity.WARNING,
            reason="verification_request_overdue",
            diff_summary="verification marked overdue",
            metadata=metadata,
        )
        await publish_verification_notification(
            db,
            event_type="verification.request_overdue",
            request_id=request_record.id,
            request_code=request_record.request_code,
            branch_id=request_record.branch_id,
            severity="critical" if request_record.risk_level == VerificationRiskLevel.CRITICAL else "high",
            triggered_by_user_id=actor.id if actor else None,
            assignee_user_id=request_record.assignee_user_id,
            assignee_role=None,
            workflow_status=request_record.workflow_status.value,
            risk_level=request_record.risk_level.value,
        )
        await sync_verification_queue_projection(db, request_id=request_record.id)
        return request_record

    return await _run_in_single_transaction(db, _callback)


async def _resolve_request(
    db: AsyncSession,
    *,
    request_record: VerificationRequest,
    actor: User | None,
    target_status: VerificationWorkflowStatus,
    reason: str,
    action_type: VerificationActionType,
    request: Request | None,
    decision_summary: str,
    metadata: dict[str, Any] | None = None,
) -> VerificationRequest:
    previous_status = request_record.workflow_status
    _ensure_transition_allowed(previous_status, target_status)
    before = _minimal_request_snapshot(request_record)
    now = _utc_now()
    current_assignment = await db.scalar(
        select(VerificationAssignment).where(
            VerificationAssignment.request_id == request_record.id,
            VerificationAssignment.is_current.is_(True),
            VerificationAssignment.ended_at.is_(None),
        )
    )
    if current_assignment is not None:
        current_assignment.is_current = False
        current_assignment.ended_at = now
    if target_status == VerificationWorkflowStatus.CANCELLED:
        request_record.cancelled_at = now
        request_record.resolved_by_user_id = actor.id if actor else None
    else:
        request_record.resolved_at = now
        request_record.resolved_by_user_id = actor.id if actor else None
    request_record.workflow_status = target_status
    request_record.last_action_at = now
    request_record.updated_at = now
    await _add_action(
        db,
        request_record=request_record,
        action_type=action_type,
        actor=actor,
        action_reason=reason,
        decision_summary=decision_summary,
        metadata=metadata,
        from_status=previous_status,
        to_status=target_status,
    )
    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action=f"VERIFICATION_REQUEST_{target_status.value.upper()}",
        entity="verification_request",
        entity_id=request_record.id,
        success=True,
        message=decision_summary,
        before=before,
        after=_minimal_request_snapshot(request_record),
        branch_id=request_record.branch_id,
        severity=AuditSeverity.INFO if target_status != VerificationWorkflowStatus.REJECTED else AuditSeverity.WARNING,
        reason=reason,
        diff_summary=decision_summary,
        metadata=metadata,
    )
    notification_event_type = f"verification.request_{target_status.value}"
    await publish_verification_notification(
        db,
        event_type=notification_event_type,
        request_id=request_record.id,
        request_code=request_record.request_code,
        branch_id=request_record.branch_id,
        severity=request_record.risk_level.value,
        triggered_by_user_id=actor.id if actor else None,
        assignee_user_id=request_record.assignee_user_id,
        assignee_role=current_assignment.assigned_role if current_assignment else None,
        workflow_status=target_status.value,
        risk_level=request_record.risk_level.value,
    )
    await sync_verification_queue_projection(db, request_id=request_record.id)
    return request_record


def _approval_blocked(
    request_record: VerificationRequest,
    items: Sequence[VerificationRequestItem],
    warnings: Sequence[VerificationDependencyWarning],
) -> bool:
    if request_record.safety_status == VerificationSafetyStatus.BLOCKED:
        return True
    if any(item.safety_status == VerificationSafetyStatus.BLOCKED for item in items):
        return True
    return any(warning.safety_status == VerificationSafetyStatus.BLOCKED for warning in warnings)


async def approve_verification_request(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None,
    reason: str,
    request: Request | None = None,
    comment: str = "",
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_verifier(actor)
        request_record = await _get_request(db, request_id)
        items = await _get_request_items(db, request_record.id)
        warnings = await _get_dependency_warnings(db, request_record.id)
        if not items:
            raise HTTPException(status_code=409, detail="verification_request_has_no_items")
        if _approval_blocked(request_record, items, warnings):
            raise HTTPException(status_code=409, detail="verification_request_blocked")
        _ensure_transition_allowed(request_record.workflow_status, VerificationWorkflowStatus.APPROVED)
        apply_results: list[dict[str, Any]] = []
        for item in items:
            if item.approval_strategy == VerificationApprovalStrategy.MANUAL_FOLLOW_UP:
                apply_results.append({"item_id": item.id, "result": "manual_follow_up"})
                continue
            handler = _APPROVAL_HANDLERS.get(item.handler_key)
            if handler is None:
                raise HTTPException(status_code=409, detail=f"verification_handler_missing:{item.handler_key}")
            result = await handler(
                db=db,
                verification_request=request_record,
                item=item,
                actor=resolved_actor,
                request=request,
            )
            apply_results.append({"item_id": item.id, "result": result or {}})
        resolved = await _resolve_request(
            db,
            request_record=request_record,
            actor=resolved_actor,
            target_status=VerificationWorkflowStatus.APPROVED,
            reason=_normalize_reason(reason),
            action_type=VerificationActionType.APPROVE,
            request=request,
            decision_summary="verification_request_approved",
            metadata={
                "apply_results": apply_results,
                "comment": _normalize_optional_string(comment, max_length=2000),
            },
        )
        await create_verification_approval_snapshot(
            db,
            request_record=resolved,
            items=items,
            dependency_warnings=warnings,
            actor=resolved_actor,
            apply_results=apply_results,
            reason=reason,
        )
        return resolved

    return await _run_in_single_transaction(db, _callback)


async def reject_verification_request(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None,
    reason: str,
    request: Request | None = None,
    comment: str = "",
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_verifier(actor)
        request_record = await _get_request(db, request_id)
        return await _resolve_request(
            db,
            request_record=request_record,
            actor=resolved_actor,
            target_status=VerificationWorkflowStatus.REJECTED,
            reason=_normalize_reason(reason),
            action_type=VerificationActionType.REJECT,
            request=request,
            decision_summary="verification_request_rejected",
            metadata={"comment": _normalize_optional_string(comment, max_length=2000)},
        )

    return await _run_in_single_transaction(db, _callback)


async def return_verification_request_for_revision(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None,
    reason: str,
    request: Request | None = None,
    comment: str = "",
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_verifier(actor)
        request_record = await _get_request(db, request_id)
        return await _resolve_request(
            db,
            request_record=request_record,
            actor=resolved_actor,
            target_status=VerificationWorkflowStatus.RETURNED_FOR_REVISION,
            reason=_normalize_reason(reason),
            action_type=VerificationActionType.RETURN_FOR_REVISION,
            request=request,
            decision_summary="verification_request_returned_for_revision",
            metadata={"comment": _normalize_optional_string(comment, max_length=2000)},
        )

    return await _run_in_single_transaction(db, _callback)


async def cancel_verification_request(
    db: AsyncSession,
    *,
    request_id: str,
    actor: User | None,
    reason: str,
    request: Request | None = None,
) -> VerificationRequest:
    async def _callback() -> VerificationRequest:
        resolved_actor = _ensure_verifier(actor)
        request_record = await _get_request(db, request_id)
        return await _resolve_request(
            db,
            request_record=request_record,
            actor=resolved_actor,
            target_status=VerificationWorkflowStatus.CANCELLED,
            reason=_normalize_reason(reason),
            action_type=VerificationActionType.CANCEL_REQUEST,
            request=request,
            decision_summary="verification_request_cancelled",
            metadata={},
        )

    return await _run_in_single_transaction(db, _callback)
