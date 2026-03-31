from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user
from server.api.schemas import ConfigUpdateIn, PublicConfig
from server.config.config_loader import load_master_config, write_master_config
from server.db.database import get_db
from server.db.models import Role, User
from server.services.audit import write_audit_log


router = APIRouter(tags=["config"])

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _norm_hex(v: str, fallback: str) -> str:
    s = (v or "").strip()
    if not _HEX.match(s):
        return fallback
    if not s.startswith("#"):
        s = "#" + s
    return s.upper()

def _norm_web_url(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    s = s.rstrip("/")
    if not (s.startswith("http://") or s.startswith("https://")):
        return ""
    return s

def _norm_bg_mode(v: str) -> str:
    mode = (v or "").strip().lower()
    if mode in ("plain", "image"):
        return mode
    return "gradient"



@router.get("/config", response_model=PublicConfig)
async def get_public_config():
    cfg = load_master_config()
    return PublicConfig(
        app_name=str(cfg.get("app_name") or "Enterprise Stock Platform"),
        app_logo_url=str(cfg.get("app_logo_url") or ""),
        web_url=_norm_web_url(str(cfg.get("web_url") or "")),
        primary_color=str(cfg.get("primary_color") or "#FF6B00"),
        secondary_color=str(cfg.get("secondary_color") or "#1E6FD9"),
        default_language=str(cfg.get("default_language") or "th"),
        currency=str(cfg.get("currency") or "THB"),
        timezone=str(cfg.get("timezone") or "Asia/Bangkok"),
        session_max_per_user=int(cfg.get("session_max_per_user") or 3),
        min_stock_threshold=int(cfg.get("min_stock_threshold") or 10),
        max_backup_files=int(cfg.get("max_backup_files") or 30),
        backup_interval_hours=int(cfg.get("backup_interval_hours") or 6),
        background_mode=_norm_bg_mode(str(cfg.get("background_mode") or "gradient")),
        background_color=_norm_hex(str(cfg.get("background_color") or "#0D0D0D"), "#0D0D0D"),
        background_image_url=str(cfg.get("background_image_url") or "").strip(),
    )


@router.put("/config", response_model=PublicConfig)
async def update_config(
    payload: ConfigUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in (Role.OWNER, Role.DEV):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    before = load_master_config()
    cfg = dict(before)

    cfg["app_name"] = payload.app_name.strip() or cfg.get("app_name") or "Enterprise Stock Platform"
    cfg["app_logo_url"] = payload.app_logo_url.strip()
    cfg["web_url"] = _norm_web_url(payload.web_url)
    cfg["primary_color"] = _norm_hex(payload.primary_color, str(cfg.get("primary_color") or "#FF6B00"))
    cfg["secondary_color"] = _norm_hex(payload.secondary_color, str(cfg.get("secondary_color") or "#1E6FD9"))

    lng = (payload.default_language or "th").strip().lower()
    cfg["default_language"] = "en" if lng == "en" else "th"
    cfg["currency"] = (payload.currency or "THB").strip().upper()
    cfg["timezone"] = (payload.timezone or "Asia/Bangkok").strip()

    cfg["session_max_per_user"] = int(payload.session_max_per_user)
    cfg["min_stock_threshold"] = int(payload.min_stock_threshold)
    cfg["max_backup_files"] = int(payload.max_backup_files)
    cfg["backup_interval_hours"] = int(payload.backup_interval_hours)
    cfg["background_mode"] = _norm_bg_mode(payload.background_mode)
    cfg["background_color"] = _norm_hex(payload.background_color, str(cfg.get("background_color") or "#0D0D0D"))
    cfg["background_image_url"] = (payload.background_image_url or "").strip()

    write_master_config(cfg)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CONFIG_UPDATE",
        entity="config",
        entity_id=None,
        success=True,
        message="updated",
        before=before,
        after=cfg,
    )

    return await get_public_config()

