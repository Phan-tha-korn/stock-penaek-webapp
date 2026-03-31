from __future__ import annotations

from typing import Any

import orjson
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import AuditLog, Role, User


def _to_json(v: Any) -> str | None:
    if v is None:
        return None
    return orjson.dumps(v).decode("utf-8")


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
) -> None:
    ip = None
    ua = None
    if request is not None:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        ip=ip,
        user_agent=ua,
        success=success,
        before_json=_to_json(before),
        after_json=_to_json(after),
        message=message,
    )
    db.add(log)
    await db.commit()

