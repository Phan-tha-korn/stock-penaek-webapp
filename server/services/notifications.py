from __future__ import annotations

import asyncio
import hashlib
import logging
import smtplib
import ssl
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from server.config.settings import settings
from server.db.models import (
    NotificationAssignmentMode,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEvent,
    NotificationEventStatus,
    NotificationFailure,
    NotificationFailureType,
    NotificationOutbox,
    NotificationOutboxStatus,
    NotificationPreference,
    NotificationSeverity,
    NotificationTemplate,
    NotificationType,
    Role,
    User,
    UserBranchScope,
)
from server.services.line import send_line_notify


logger = logging.getLogger(__name__)

CRITICAL_NOTIFICATION_ROLES = {Role.DEV, Role.OWNER}
SEVERITY_PRIORITY_MAP = {
    NotificationSeverity.LOW: 25,
    NotificationSeverity.MEDIUM: 50,
    NotificationSeverity.HIGH: 75,
    NotificationSeverity.CRITICAL: 100,
}
DEFAULT_CHANNELS_BY_SEVERITY = {
    NotificationSeverity.LOW: (NotificationChannel.EMAIL,),
    NotificationSeverity.MEDIUM: (NotificationChannel.EMAIL,),
    NotificationSeverity.HIGH: (NotificationChannel.LINE, NotificationChannel.EMAIL),
    NotificationSeverity.CRITICAL: (NotificationChannel.LINE, NotificationChannel.EMAIL),
}
PENDING_OUTBOX_STATUSES = {
    NotificationOutboxStatus.PENDING,
    NotificationOutboxStatus.RETRY_SCHEDULED,
}


class NotificationDeliveryError(Exception):
    def __init__(self, failure_type: NotificationFailureType, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.retryable = retryable


@dataclass(slots=True)
class NotificationTarget:
    user_id: str | None
    role: str | None
    channel: NotificationChannel
    assignment_mode: NotificationAssignmentMode
    address: str | None


def _utc_now() -> datetime:
    return datetime.utcnow()


def map_notification_priority(severity: NotificationSeverity | str) -> int:
    resolved = _normalize_notification_severity(severity)
    return SEVERITY_PRIORITY_MAP[resolved]


def build_notification_dedupe_key(*parts: Any) -> str:
    normalized = "::".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
    if not normalized:
        normalized = "notification"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_notification_severity(value: NotificationSeverity | str | None) -> NotificationSeverity:
    if isinstance(value, NotificationSeverity):
        return value
    try:
        return NotificationSeverity(str(value or NotificationSeverity.LOW.value).strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_notification_severity") from exc


def _normalize_notification_type(value: NotificationType | str | None) -> NotificationType:
    if isinstance(value, NotificationType):
        return value
    try:
        return NotificationType(str(value or NotificationType.IMMEDIATE.value).strip().lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_notification_type") from exc


def _normalize_channels(values: Sequence[NotificationChannel | str] | None, *, severity: NotificationSeverity) -> list[NotificationChannel]:
    if not values:
        return list(DEFAULT_CHANNELS_BY_SEVERITY[severity])
    channels: list[NotificationChannel] = []
    seen: set[NotificationChannel] = set()
    for value in values:
        resolved = value if isinstance(value, NotificationChannel) else NotificationChannel(str(value).strip().lower())
        if resolved in seen:
            continue
        seen.add(resolved)
        channels.append(resolved)
    return channels


def _safe_string(value: Any, *, default: str = "") -> str:
    return str(value or default).strip()


def _role_email(role: str | None) -> str | None:
    if not role:
        return None
    return _safe_string(getattr(settings, f"notification_email_{role.lower()}", ""), default="") or None


def _retry_delay(attempt_no: int) -> timedelta:
    schedule = {
        1: timedelta(minutes=5),
        2: timedelta(minutes=15),
        3: timedelta(hours=1),
    }
    return schedule.get(attempt_no, timedelta(hours=4))


def _resolved_max_attempts(notification_type: NotificationType) -> int:
    configured = max(1, int(settings.notification_max_retry_attempts))
    if notification_type == NotificationType.DELAYED:
        return max(1, configured - 1)
    return configured


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


async def _load_template(
    db: AsyncSession,
    *,
    event_type: str,
    channel: NotificationChannel,
) -> NotificationTemplate | None:
    return await db.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.event_type == event_type,
            NotificationTemplate.channel == channel,
            NotificationTemplate.is_active.is_(True),
        )
    )


async def _render_message(
    db: AsyncSession,
    *,
    event_type: str,
    channel: NotificationChannel,
    payload: dict[str, Any],
    default_title: str,
    default_body: str,
) -> tuple[str, str]:
    template = await _load_template(db, event_type=event_type, channel=channel)
    if template is None:
        return default_title, default_body
    context = _SafeFormatDict(payload)
    title = template.title_template.format_map(context).strip() or default_title
    body = template.body_template.format_map(context).strip() or default_body
    return title, body


async def _user_can_view_branch(db: AsyncSession, *, user_id: str, role: Role, branch_id: str | None) -> bool:
    if branch_id is None or role == Role.OWNER:
        return True
    scopes = (
        await db.execute(select(UserBranchScope).where(UserBranchScope.user_id == user_id))
    ).scalars().all()
    if not scopes:
        return True
    return any(scope.branch_id == branch_id and scope.can_view for scope in scopes)


async def _resolve_users_for_roles(
    db: AsyncSession,
    *,
    roles: Iterable[str],
    branch_id: str | None,
) -> list[User]:
    normalized_roles = []
    for role in roles:
        cleaned = _safe_string(role)
        if not cleaned:
            continue
        try:
            normalized_roles.append(Role(cleaned.upper()))
        except ValueError:
            continue
    if not normalized_roles:
        return []
    users = (
        await db.execute(
            select(User).where(
                User.role.in_(normalized_roles),
                User.is_active.is_(True),
            )
        )
    ).scalars().all()
    resolved: list[User] = []
    for user in users:
        if await _user_can_view_branch(db, user_id=user.id, role=user.role, branch_id=branch_id):
            resolved.append(user)
    return resolved


async def _resolve_user(db: AsyncSession, *, user_id: str) -> User | None:
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    return user


async def _preference_disabled(
    db: AsyncSession,
    *,
    user_id: str,
    channel: NotificationChannel,
    event_type: str,
    branch_id: str | None,
    severity: NotificationSeverity,
) -> bool:
    if severity in {NotificationSeverity.HIGH, NotificationSeverity.CRITICAL}:
        return False
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.channel == channel,
            NotificationPreference.event_type == event_type,
            NotificationPreference.branch_id == branch_id,
        )
    )
    return pref is not None and not pref.is_enabled


async def _resolve_targets(
    db: AsyncSession,
    *,
    event_type: str,
    branch_id: str | None,
    severity: NotificationSeverity,
    channels: Sequence[NotificationChannel],
    target_roles: Sequence[str] | None,
    target_user_ids: Sequence[str] | None,
    assignment_user_id: str | None,
    assignment_role: str | None,
) -> list[NotificationTarget]:
    targets: list[NotificationTarget] = []
    seen: set[tuple[str | None, str | None, NotificationChannel, str | None]] = set()

    resolved_roles = list(target_roles or [])
    if severity in {NotificationSeverity.HIGH, NotificationSeverity.CRITICAL}:
        for role in CRITICAL_NOTIFICATION_ROLES:
            if role.value not in resolved_roles:
                resolved_roles.append(role.value)
    if assignment_role and assignment_role not in resolved_roles and assignment_user_id is None:
        resolved_roles.append(assignment_role)

    users: list[User] = []
    for role_user in await _resolve_users_for_roles(db, roles=resolved_roles, branch_id=branch_id):
        users.append(role_user)
    for user_id in [item for item in [assignment_user_id, *(target_user_ids or [])] if item]:
        user = await _resolve_user(db, user_id=user_id)
        if user is not None and all(existing.id != user.id for existing in users):
            if await _user_can_view_branch(db, user_id=user.id, role=user.role, branch_id=branch_id):
                users.append(user)

    for user in users:
        for channel in channels:
            if await _preference_disabled(
                db,
                user_id=user.id,
                channel=channel,
                event_type=event_type,
                branch_id=branch_id,
                severity=severity,
            ):
                continue
            address = _role_email(user.role.value) if channel == NotificationChannel.EMAIL else None
            routing_role = user.role.value
            key = (user.id, routing_role, channel, address)
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                NotificationTarget(
                    user_id=user.id,
                    role=routing_role,
                    channel=channel,
                    assignment_mode=NotificationAssignmentMode.USER,
                    address=address,
                )
            )
    return targets


async def publish_notification_event(
    db: AsyncSession,
    *,
    event_type: str,
    source_domain: str,
    source_entity_type: str,
    source_entity_id: str | None,
    severity: NotificationSeverity | str,
    payload: dict[str, Any] | None,
    triggered_by_user_id: str | None,
    branch_id: str | None = None,
    notification_type: NotificationType | str | None = None,
    related_request_id: str | None = None,
    target_roles: Sequence[str] | None = None,
    target_user_ids: Sequence[str] | None = None,
    assignment_user_id: str | None = None,
    assignment_role: str | None = None,
    channels: Sequence[NotificationChannel | str] | None = None,
    dedupe_tokens: Sequence[Any] | None = None,
    default_title: str | None = None,
    default_body: str | None = None,
    scheduled_at: datetime | None = None,
) -> NotificationEvent:
    resolved_event_type = _safe_string(event_type)
    if not resolved_event_type:
        raise HTTPException(status_code=400, detail="notification_event_type_required")
    resolved_severity = _normalize_notification_severity(severity)
    resolved_type = _normalize_notification_type(notification_type)
    resolved_payload = dict(payload or {})
    event_dedupe_key = build_notification_dedupe_key(
        "event",
        resolved_event_type,
        source_domain,
        source_entity_type,
        source_entity_id,
        branch_id,
        related_request_id,
        *(dedupe_tokens or []),
    )
    existing = await db.scalar(
        select(NotificationEvent).where(NotificationEvent.dedupe_key == event_dedupe_key)
    )
    if existing is not None:
        return existing

    event = NotificationEvent(
        event_type=resolved_event_type,
        notification_type=resolved_type,
        source_domain=_safe_string(source_domain),
        source_entity_type=_safe_string(source_entity_type),
        source_entity_id=_safe_string(source_entity_id) or None,
        branch_id=branch_id,
        severity=resolved_severity,
        priority=map_notification_priority(resolved_severity),
        status=NotificationEventStatus.PENDING,
        payload_json=resolved_payload,
        dedupe_key=event_dedupe_key,
        triggered_by_user_id=triggered_by_user_id,
        related_request_id=related_request_id,
        occurred_at=_utc_now(),
        created_at=_utc_now(),
    )
    db.add(event)
    await db.flush()

    resolved_channels = _normalize_channels(channels, severity=resolved_severity)
    targets = await _resolve_targets(
        db,
        event_type=resolved_event_type,
        branch_id=branch_id,
        severity=resolved_severity,
        channels=resolved_channels,
        target_roles=target_roles,
        target_user_ids=target_user_ids,
        assignment_user_id=assignment_user_id,
        assignment_role=assignment_role,
    )
    for target in targets:
        title, body = await _render_message(
            db,
            event_type=resolved_event_type,
            channel=target.channel,
            payload=resolved_payload,
            default_title=default_title or resolved_event_type,
            default_body=default_body or resolved_payload.get("message") or resolved_event_type,
        )
        outbox_dedupe_key = build_notification_dedupe_key(
            "outbox",
            event.dedupe_key,
            target.channel.value,
            target.user_id,
            target.role,
            target.address,
        )
        if await db.scalar(select(NotificationOutbox).where(NotificationOutbox.dedupe_key == outbox_dedupe_key)):
            continue
        db.add(
            NotificationOutbox(
                event_id=event.id,
                channel=target.channel,
                assignment_mode=target.assignment_mode,
                recipient_user_id=target.user_id,
                recipient_address=target.address,
                routing_role=target.role,
                branch_id=branch_id,
                severity=resolved_severity,
                priority=map_notification_priority(resolved_severity),
                status=NotificationOutboxStatus.PENDING,
                message_title=title[:255],
                message_body=body,
                payload_json=resolved_payload,
                dedupe_key=outbox_dedupe_key,
                scheduled_at=scheduled_at or _utc_now(),
                max_attempts=_resolved_max_attempts(resolved_type),
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
        )
    await db.flush()
    await _refresh_notification_event_status(db, event_id=event.id)
    logger.info("notification_event_published:%s:%s", resolved_event_type, event.id)
    return event


async def publish_verification_notification(
    db: AsyncSession,
    *,
    event_type: str,
    request_id: str,
    request_code: str,
    branch_id: str | None,
    severity: NotificationSeverity | str,
    triggered_by_user_id: str | None,
    assignee_user_id: str | None = None,
    assignee_role: str | None = None,
    workflow_status: str | None = None,
    risk_level: str | None = None,
) -> NotificationEvent:
    payload = {
        "request_id": request_id,
        "request_code": request_code,
        "workflow_status": workflow_status or "",
        "risk_level": risk_level or "",
        "assignee_user_id": assignee_user_id or "",
        "assignee_role": assignee_role or "",
        "message": f"Verification {request_code} {event_type}",
    }
    return await publish_notification_event(
        db,
        event_type=event_type,
        source_domain="verification",
        source_entity_type="verification_request",
        source_entity_id=request_id,
        severity=severity,
        payload=payload,
        triggered_by_user_id=triggered_by_user_id,
        branch_id=branch_id,
        related_request_id=request_id,
        target_user_ids=[assignee_user_id] if assignee_user_id else None,
        target_roles=[assignee_role] if assignee_role else None,
        assignment_user_id=assignee_user_id,
        assignment_role=assignee_role,
        dedupe_tokens=[workflow_status, risk_level, assignee_user_id],
        default_title=f"Verification {request_code}",
        default_body=f"{event_type} ({workflow_status or 'pending'})",
    )


async def publish_supplier_verification_notification(
    db: AsyncSession,
    *,
    proposal_id: str,
    supplier_id: str | None,
    supplier_name: str,
    branch_id: str | None,
    triggered_by_user_id: str | None,
) -> NotificationEvent:
    return await publish_notification_event(
        db,
        event_type="supplier.verification_required",
        source_domain="supplier",
        source_entity_type="supplier_change_proposal",
        source_entity_id=proposal_id,
        severity=NotificationSeverity.HIGH,
        payload={
            "proposal_id": proposal_id,
            "supplier_id": supplier_id or "",
            "supplier_name": supplier_name,
            "message": f"Supplier change proposal pending: {supplier_name}",
        },
        triggered_by_user_id=triggered_by_user_id,
        branch_id=branch_id,
        target_roles=[Role.DEV.value, Role.OWNER.value],
        dedupe_tokens=[proposal_id],
        default_title="Supplier verification required",
        default_body=f"Supplier proposal pending for {supplier_name}",
    )


async def publish_pricing_notification(
    db: AsyncSession,
    *,
    event_type: str,
    price_record_id: str,
    branch_id: str | None,
    product_id: str,
    supplier_id: str,
    triggered_by_user_id: str | None,
    severity: NotificationSeverity | str,
    related_price_record_id: str | None = None,
) -> NotificationEvent:
    return await publish_notification_event(
        db,
        event_type=event_type,
        source_domain="pricing",
        source_entity_type="price_record",
        source_entity_id=price_record_id,
        severity=severity,
        payload={
            "price_record_id": price_record_id,
            "product_id": product_id,
            "supplier_id": supplier_id,
            "related_price_record_id": related_price_record_id or "",
            "message": f"Pricing event {event_type} for product {product_id}",
        },
        triggered_by_user_id=triggered_by_user_id,
        branch_id=branch_id,
        target_roles=[Role.DEV.value, Role.OWNER.value],
        dedupe_tokens=[price_record_id, related_price_record_id],
        default_title="Critical pricing change",
        default_body=f"{event_type} for price record {price_record_id}",
    )


async def claim_notification_outbox_batch(
    db: AsyncSession,
    *,
    worker_token: str,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[NotificationOutbox]:
    resolved_now = now or _utc_now()
    lease_cutoff = resolved_now - timedelta(seconds=max(10, int(settings.notification_lock_seconds)))
    resolved_limit = max(
        1,
        min(
            int(limit or settings.notification_worker_batch_size),
            max(1, int(settings.notification_max_batch_size)),
        ),
    )
    candidates = (
        await db.execute(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status.in_(list(PENDING_OUTBOX_STATUSES)),
                NotificationOutbox.scheduled_at <= resolved_now,
                or_(NotificationOutbox.next_retry_at.is_(None), NotificationOutbox.next_retry_at <= resolved_now),
                or_(NotificationOutbox.locked_at.is_(None), NotificationOutbox.locked_at < lease_cutoff),
            )
            .order_by(
                NotificationOutbox.priority.desc(),
                NotificationOutbox.scheduled_at.asc(),
                NotificationOutbox.created_at.asc(),
                NotificationOutbox.id.asc(),
            )
            .limit(resolved_limit)
        )
    ).scalars().all()
    claimed: list[NotificationOutbox] = []
    for row in candidates:
        result = await db.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.id == row.id,
                NotificationOutbox.status.in_(list(PENDING_OUTBOX_STATUSES)),
                or_(NotificationOutbox.locked_at.is_(None), NotificationOutbox.locked_at < lease_cutoff),
            )
            .values(
                status=NotificationOutboxStatus.PROCESSING,
                locked_at=resolved_now,
                worker_token=worker_token,
                last_attempt_at=resolved_now,
                updated_at=resolved_now,
            )
        )
        if int(result.rowcount or 0) != 1:
            continue
        claimed_row = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.id == row.id))
        if claimed_row is not None:
            claimed.append(claimed_row)
    await db.flush()
    logger.info("notification_outbox_claimed:%s", len(claimed))
    return claimed


async def _send_email_message(*, to_address: str, title: str, body: str) -> str:
    if not settings.smtp_host or not settings.smtp_from_email or not to_address:
        raise NotificationDeliveryError(NotificationFailureType.CONFIG_ERROR, "email_configuration_missing", retryable=False)

    def _send() -> str:
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = settings.smtp_from_email
        message["To"] = to_address
        message.set_content(body)
        context = ssl.create_default_context()
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=max(1, int(settings.notification_delivery_timeout_seconds)),
        ) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls(context=context)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return f"email:{uuid.uuid4().hex[:16]}"

    try:
        return await asyncio.to_thread(_send)
    except NotificationDeliveryError:
        raise
    except smtplib.SMTPException as exc:
        raise NotificationDeliveryError(NotificationFailureType.PROVIDER_ERROR, str(exc), retryable=True) from exc
    except OSError as exc:
        raise NotificationDeliveryError(NotificationFailureType.NETWORK_ERROR, str(exc), retryable=True) from exc


async def _deliver_outbox_message(outbox: NotificationOutbox) -> str:
    if outbox.channel == NotificationChannel.LINE:
        role = _safe_string(outbox.routing_role).lower()
        if not role:
            raise NotificationDeliveryError(NotificationFailureType.CONFIG_ERROR, "line_routing_role_missing", retryable=False)
        sent = await asyncio.wait_for(
            send_line_notify(role, f"{outbox.message_title}\n{outbox.message_body}".strip()),
            timeout=max(1, int(settings.notification_delivery_timeout_seconds)),
        )
        if not sent:
            raise NotificationDeliveryError(NotificationFailureType.PROVIDER_ERROR, "line_delivery_failed", retryable=True)
        return f"line:{uuid.uuid4().hex[:16]}"
    if outbox.channel == NotificationChannel.EMAIL:
        address = _safe_string(outbox.recipient_address)
        if not address:
            address = _role_email(outbox.routing_role) or ""
        return await _send_email_message(to_address=address, title=outbox.message_title, body=outbox.message_body)
    if outbox.channel == NotificationChannel.DISCORD:
        raise NotificationDeliveryError(NotificationFailureType.CONFIG_ERROR, "discord_notifier_not_configured", retryable=False)
    raise NotificationDeliveryError(NotificationFailureType.UNEXPECTED_ERROR, "unsupported_notification_channel", retryable=False)


async def _refresh_notification_event_status(db: AsyncSession, *, event_id: str) -> None:
    rows = (
        await db.execute(select(NotificationOutbox.status).where(NotificationOutbox.event_id == event_id))
    ).scalars().all()
    event = await db.scalar(select(NotificationEvent).where(NotificationEvent.id == event_id))
    if event is None:
        return
    if not rows:
        event.status = NotificationEventStatus.CANCELLED
        event.processed_at = _utc_now()
    elif all(status in {NotificationOutboxStatus.SENT, NotificationOutboxStatus.CANCELLED, NotificationOutboxStatus.FAILED} for status in rows):
        event.status = NotificationEventStatus.PROCESSED
        event.processed_at = _utc_now()


async def mark_notification_sent(
    db: AsyncSession,
    *,
    outbox: NotificationOutbox,
    provider_message_id: str | None,
    response_code: str | None = None,
    response_summary: str = "",
) -> NotificationOutbox:
    now = _utc_now()
    outbox.status = NotificationOutboxStatus.SENT
    outbox.sent_at = now
    outbox.locked_at = None
    outbox.worker_token = None
    outbox.updated_at = now
    db.add(
        NotificationDelivery(
            outbox_id=outbox.id,
            event_id=outbox.event_id,
            channel=outbox.channel,
            delivery_status=NotificationDeliveryStatus.SENT,
            provider_message_id=provider_message_id,
            response_code=response_code,
            response_summary=response_summary,
            sent_at=now,
            created_at=now,
        )
    )
    await db.flush()
    await _refresh_notification_event_status(db, event_id=outbox.event_id)
    return outbox


async def record_notification_failure(
    db: AsyncSession,
    *,
    outbox: NotificationOutbox,
    failure_type: NotificationFailureType,
    failure_message: str,
    retryable: bool,
) -> NotificationOutbox:
    now = _utc_now()
    next_attempt_no = int(outbox.attempt_count or 0) + 1
    outbox.attempt_count = next_attempt_no
    outbox.updated_at = now
    outbox.locked_at = None
    outbox.worker_token = None
    if retryable and next_attempt_no < int(outbox.max_attempts or 1):
        outbox.status = NotificationOutboxStatus.RETRY_SCHEDULED
        outbox.next_retry_at = now + _retry_delay(next_attempt_no)
        delivery_status = NotificationDeliveryStatus.RETRY_SCHEDULED
    else:
        outbox.status = NotificationOutboxStatus.FAILED
        outbox.next_retry_at = None
        delivery_status = NotificationDeliveryStatus.FAILED
    db.add(
        NotificationFailure(
            outbox_id=outbox.id,
            event_id=outbox.event_id,
            failure_type=failure_type,
            failure_message=failure_message[:4000],
            retryable=retryable,
            attempt_no=next_attempt_no,
            created_at=now,
        )
    )
    db.add(
        NotificationDelivery(
            outbox_id=outbox.id,
            event_id=outbox.event_id,
            channel=outbox.channel,
            delivery_status=delivery_status,
            provider_message_id=None,
            response_code=failure_type.value,
            response_summary=failure_message[:4000],
            sent_at=None,
            created_at=now,
        )
    )
    await db.flush()
    await _refresh_notification_event_status(db, event_id=outbox.event_id)
    logger.warning(
        "notification_failure:%s:%s:%s/%s",
        outbox.id,
        failure_type.value,
        outbox.attempt_count,
        outbox.max_attempts,
    )
    return outbox


async def deliver_notification_outbox_item(
    db: AsyncSession,
    *,
    outbox_id: str,
    worker_token: str,
) -> NotificationOutbox:
    outbox = await db.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.id == outbox_id,
            NotificationOutbox.worker_token == worker_token,
            NotificationOutbox.status == NotificationOutboxStatus.PROCESSING,
        )
    )
    if outbox is None:
        raise HTTPException(status_code=404, detail="notification_outbox_not_claimed")
    try:
        provider_message_id = await asyncio.wait_for(
            _deliver_outbox_message(outbox),
            timeout=max(1, int(settings.notification_processing_timeout_seconds)),
        )
        return await mark_notification_sent(
            db,
            outbox=outbox,
            provider_message_id=provider_message_id,
            response_summary="notification_sent",
        )
    except asyncio.TimeoutError:
        logger.warning("notification_processing_timeout:%s", outbox.id)
        return await record_notification_failure(
            db,
            outbox=outbox,
            failure_type=NotificationFailureType.NETWORK_ERROR,
            failure_message="notification_processing_timeout",
            retryable=True,
        )
    except NotificationDeliveryError as exc:
        logger.warning("Notification delivery failed for %s: %s", outbox.id, exc)
        return await record_notification_failure(
            db,
            outbox=outbox,
            failure_type=exc.failure_type,
            failure_message=str(exc),
            retryable=exc.retryable,
        )


async def process_pending_notifications(
    db: AsyncSession,
    *,
    worker_token: str,
    limit: int | None = None,
) -> list[NotificationOutbox]:
    claimed = await claim_notification_outbox_batch(db, worker_token=worker_token, limit=limit)
    processed: list[NotificationOutbox] = []
    for outbox in claimed:
        processed.append(await deliver_notification_outbox_item(db, outbox_id=outbox.id, worker_token=worker_token))
    pending_count = int(
        await db.scalar(
            select(func.count(NotificationOutbox.id)).where(
                NotificationOutbox.status.in_(list(PENDING_OUTBOX_STATUSES))
            )
        )
        or 0
    )
    logger.info("notification_queue_processed:%s pending:%s", len(processed), pending_count)
    return processed
