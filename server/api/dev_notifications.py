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


def _mask_token(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"


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
        line_token_status={
            "OWNER": _mask_token(str(cfg.get("line_token_owner") or "")),
            "ADMIN": _mask_token(str(cfg.get("line_token_admin") or "")),
            "STOCK": _mask_token(str(cfg.get("line_token_stock") or "")),
            "ACCOUNTANT": _mask_token(str(cfg.get("line_token_accountant") or "")),
            "DEV": _mask_token(str(cfg.get("line_token_dev") or "")),
        },
        include_name=bool(cfg.get("notification_include_name", True)),
        include_sku=bool(cfg.get("notification_include_sku", True)),
        include_status=bool(cfg.get("notification_include_status", True)),
        include_current_qty=bool(cfg.get("notification_include_current_qty", True)),
        include_target_qty=bool(cfg.get("notification_include_target_qty", True)),
        include_restock_qty=bool(cfg.get("notification_include_restock_qty", True)),
        include_actor=bool(cfg.get("notification_include_actor", True)),
        include_reason=bool(cfg.get("notification_include_reason", True)),
        include_image_url=bool(cfg.get("notification_include_image_url", False)),
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
    for role in ("owner", "admin", "stock", "accountant", "dev"):
        provided = (payload.line_tokens or {}).get(role.upper())
        if provided is not None:
            cfg[f"line_token_{role}"] = str(provided).strip()
    cfg["notification_include_name"] = bool(payload.include_name)
    cfg["notification_include_sku"] = bool(payload.include_sku)
    cfg["notification_include_status"] = bool(payload.include_status)
    cfg["notification_include_current_qty"] = bool(payload.include_current_qty)
    cfg["notification_include_target_qty"] = bool(payload.include_target_qty)
    cfg["notification_include_restock_qty"] = bool(payload.include_restock_qty)
    cfg["notification_include_actor"] = bool(payload.include_actor)
    cfg["notification_include_reason"] = bool(payload.include_reason)
    cfg["notification_include_image_url"] = bool(payload.include_image_url)
    write_master_config(cfg)

    return NotificationConfigOut(
        enabled=bool(payload.enabled),
        low_levels_pct=sorted(low, reverse=True),
        high_levels_pct=sorted(high),
        roles=roles,
        line_token_status={
            "OWNER": _mask_token(str(cfg.get("line_token_owner") or "")),
            "ADMIN": _mask_token(str(cfg.get("line_token_admin") or "")),
            "STOCK": _mask_token(str(cfg.get("line_token_stock") or "")),
            "ACCOUNTANT": _mask_token(str(cfg.get("line_token_accountant") or "")),
            "DEV": _mask_token(str(cfg.get("line_token_dev") or "")),
        },
        include_name=bool(cfg.get("notification_include_name", True)),
        include_sku=bool(cfg.get("notification_include_sku", True)),
        include_status=bool(cfg.get("notification_include_status", True)),
        include_current_qty=bool(cfg.get("notification_include_current_qty", True)),
        include_target_qty=bool(cfg.get("notification_include_target_qty", True)),
        include_restock_qty=bool(cfg.get("notification_include_restock_qty", True)),
        include_actor=bool(cfg.get("notification_include_actor", True)),
        include_reason=bool(cfg.get("notification_include_reason", True)),
        include_image_url=bool(cfg.get("notification_include_image_url", False)),
    )

