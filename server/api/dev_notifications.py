from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from server.api.deps import require_roles
from server.api.schemas import NotificationConfigOut, NotificationConfigUpdateIn
from server.config.config_loader import load_master_config, write_master_config
from server.db.models import Role


router = APIRouter(prefix="/dev/notifications", tags=["dev-notifications"])


def _clean_levels(levels: list[int]) -> list[int]:
    out: list[int] = []
    for x in levels:
        try:
            n = int(x)
        except Exception:
            continue
        if n < 0 or n > 100:
            continue
        if n not in out:
            out.append(n)
    return out


def _clean_roles(roles: list[str]) -> list[str]:
    allowed = {r.value for r in Role}
    out: list[str] = []
    for x in roles:
        v = str(x).strip().upper()
        if v in allowed and v not in out:
            out.append(v)
    return out


@router.get("/config", response_model=NotificationConfigOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def get_notification_config():
    cfg = load_master_config()
    enabled = bool(cfg.get("notification_enabled") or False)
    low_levels = cfg.get("notification_low_levels_pct", [50, 20, 10, 0])
    high_levels = cfg.get("notification_high_levels_pct", [80, 90, 100])
    roles = cfg.get("notification_roles", ["OWNER"])
    if not isinstance(low_levels, list):
        low_levels = [50, 20, 10, 0]
    if not isinstance(high_levels, list):
        high_levels = [80, 90, 100]
    if not isinstance(roles, list):
        roles = ["OWNER"]
    return NotificationConfigOut(
        enabled=enabled,
        low_levels_pct=_clean_levels(low_levels),
        high_levels_pct=_clean_levels(high_levels),
        roles=_clean_roles(roles),
    )


@router.put("/config", response_model=NotificationConfigOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def update_notification_config(payload: NotificationConfigUpdateIn):
    low = _clean_levels(payload.low_levels_pct)
    high = _clean_levels(payload.high_levels_pct)
    roles = _clean_roles(payload.roles)
    if not roles:
        raise HTTPException(status_code=400, detail="roles_required")

    cfg = load_master_config()
    cfg["notification_enabled"] = bool(payload.enabled)
    cfg["notification_low_levels_pct"] = sorted(low, reverse=True)
    cfg["notification_high_levels_pct"] = sorted(high)
    cfg["notification_roles"] = roles
    write_master_config(cfg)

    return NotificationConfigOut(
        enabled=bool(payload.enabled),
        low_levels_pct=sorted(low, reverse=True),
        high_levels_pct=sorted(high),
        roles=roles,
    )

