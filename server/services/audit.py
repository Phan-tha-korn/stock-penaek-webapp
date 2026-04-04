from __future__ import annotations

from typing import Any

import orjson
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import AuditEvent, AuditLog, AuditSeverity, User


def _to_json(v: Any) -> str | None:
    if v is None:
        return None
    return orjson.dumps(v).decode("utf-8")


def _extract_branch_id(value: Any) -> str | None:
    if isinstance(value, dict):
        candidate = value.get("branch_id")
        if candidate:
            return str(candidate)
    return None


async def write_audit_log(
    db: AsyncSession,
    *,
    request: Request | None,
    actor: User | None,
    action: str,
    entity: str,
    entity_id: str | None,
    success: bool,
    message: str,
    before: Any = None,
    after: Any = None,
    branch_id: str | None = None,
    severity: AuditSeverity = AuditSeverity.INFO,
    reason: str = "",
    diff_summary: str = "",
    metadata: Any = None,
    commit: bool = False,
) -> AuditLog:
    ip = None
    ua = None
    if request is not None:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

    resolved_branch_id = branch_id or _extract_branch_id(after) or _extract_branch_id(before)

    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        branch_id=resolved_branch_id,
        ip=ip,
        user_agent=ua,
        success=success,
        before_json=_to_json(before),
        after_json=_to_json(after),
        message=message,
    )
    db.add(log)
    await db.flush()

    db.add(
        AuditEvent(
            audit_log_id=log.id,
            actor_user_id=actor.id if actor else None,
            actor_username=actor.username if actor else None,
            actor_role=actor.role if actor else None,
            branch_id=resolved_branch_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            severity=severity,
            reason=reason or message,
            diff_summary=diff_summary,
            metadata_json=_to_json(metadata),
            before_json=_to_json(before),
            after_json=_to_json(after),
            success=success,
        )
    )

    if commit:
        await db.commit()

    return log
