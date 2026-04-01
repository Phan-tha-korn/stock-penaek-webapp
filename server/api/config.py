from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user
from server.api.schemas import ConfigUpdateIn, GoogleSetupIn, GoogleSetupOut, PublicConfig
from server.config.config_loader import load_master_config, write_master_config
from server.config.settings import settings
from server.db.database import get_db
from server.db.models import Role, User
from server.services.audit import write_audit_log
from server.services.gsheets import (
    TAB_ACCOUNTING,
    TAB_ADD_LOG,
    TAB_AUDIT_LOG,
    TAB_EDIT_LOG,
    TAB_EXPENSE_LOG,
    TAB_INCOME_LOG,
    TAB_OVERVIEW,
    TAB_SELL_LOG,
    TAB_STOCK,
    TAB_STOCK_ALERTS,
    _ensure_tab,
    _style_sheet,
    get_client,
    sync_all_to_sheets,
)
import asyncio


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


def _norm_int(value: int, fallback: int, min_value: int, max_value: int) -> int:
    try:
        n = int(value)
    except Exception:
        return fallback
    return max(min_value, min(max_value, n))



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
        background_gradient_from=_norm_hex(str(cfg.get("background_gradient_from") or "#0D0D0D"), "#0D0D0D"),
        background_gradient_to=_norm_hex(str(cfg.get("background_gradient_to") or "#101826"), "#101826"),
        background_gradient_accent=_norm_hex(str(cfg.get("background_gradient_accent") or "#1E6FD9"), "#1E6FD9"),
        background_blur_px=_norm_int(int(cfg.get("background_blur_px") or 0), 0, 0, 48),
        background_overlay_opacity=_norm_int(int(cfg.get("background_overlay_opacity") or 35), 35, 0, 95),
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
    cfg["background_gradient_from"] = _norm_hex(payload.background_gradient_from, str(cfg.get("background_gradient_from") or "#0D0D0D"))
    cfg["background_gradient_to"] = _norm_hex(payload.background_gradient_to, str(cfg.get("background_gradient_to") or "#101826"))
    cfg["background_gradient_accent"] = _norm_hex(payload.background_gradient_accent, str(cfg.get("background_gradient_accent") or "#1E6FD9"))
    cfg["background_blur_px"] = _norm_int(payload.background_blur_px, int(cfg.get("background_blur_px") or 0), 0, 48)
    cfg["background_overlay_opacity"] = _norm_int(payload.background_overlay_opacity, int(cfg.get("background_overlay_opacity") or 35), 0, 95)

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


@router.get("/config/google-setup", response_model=GoogleSetupOut)
async def get_google_setup(user: User = Depends(get_current_user)):
    if user.role not in (Role.OWNER, Role.DEV):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""
    return GoogleSetupOut(
        configured=bool(sheet_id and (cfg.get("google_service_account_key_path") or cfg.get("google_sheets", {}).get("service_account_key_path"))),
        workspace_email=str(cfg.get("google_workspace_email") or ""),
        drive_folder_name=str(cfg.get("google_drive_folder_name") or ""),
        default_sheet_title=str(cfg.get("google_default_sheet_title") or ""),
        service_account_key_path=str(cfg.get("google_service_account_key_path") or cfg.get("google_sheets", {}).get("service_account_key_path") or ""),
        current_sheet_id=sheet_id,
        current_sheet_url=sheet_url,
    )


@router.put("/config/google-setup", response_model=GoogleSetupOut)
async def update_google_setup(
    payload: GoogleSetupIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in (Role.OWNER, Role.DEV):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    before = load_master_config()
    cfg = dict(before)
    google_sheets = dict(cfg.get("google_sheets") or {})
    cfg["google_workspace_email"] = (payload.workspace_email or "").strip()
    cfg["google_drive_folder_name"] = (payload.drive_folder_name or "").strip()
    cfg["google_default_sheet_title"] = (payload.default_sheet_title or "").strip() or "Stock Penaek"
    key_path = (payload.service_account_key_path or "").strip()
    if key_path:
        cfg["google_service_account_key_path"] = key_path
        google_sheets["service_account_key_path"] = key_path

    new_sheet_id = str(cfg.get("google_sheets_id") or google_sheets.get("sheet_id") or "")
    if payload.create_new_sheet:
        if key_path:
            settings.google_service_account_key_path = key_path
        client = get_client()
        if not client:
            raise HTTPException(status_code=400, detail="google_not_ready")
        title = cfg["google_default_sheet_title"]
        try:
            sheet = client.create(title)
            tabs = [
                _ensure_tab(sheet, TAB_OVERVIEW),
                _ensure_tab(sheet, TAB_STOCK),
                _ensure_tab(sheet, TAB_STOCK_ALERTS),
                _ensure_tab(sheet, TAB_ACCOUNTING),
                _ensure_tab(sheet, TAB_AUDIT_LOG),
                _ensure_tab(sheet, TAB_EDIT_LOG),
                _ensure_tab(sheet, TAB_ADD_LOG),
                _ensure_tab(sheet, TAB_SELL_LOG),
                _ensure_tab(sheet, TAB_INCOME_LOG),
                _ensure_tab(sheet, TAB_EXPENSE_LOG),
            ]
            _style_sheet(sheet, tabs)
            new_sheet_id = str(getattr(sheet, "id", "") or "")
        except Exception:
            raise HTTPException(status_code=500, detail="google_sheet_create_failed")
        cfg["google_sheets_id"] = new_sheet_id
        google_sheets["sheet_id"] = new_sheet_id

    cfg["google_sheets"] = google_sheets
    write_master_config(cfg)

    settings.google_sheets_id = str(cfg.get("google_sheets_id") or google_sheets.get("sheet_id") or "")
    settings.google_service_account_key_path = str(cfg.get("google_service_account_key_path") or google_sheets.get("service_account_key_path") or settings.google_service_account_key_path)

    if payload.migrate_existing_data and settings.google_sheets_id:
        try:
            await sync_all_to_sheets()
        except Exception:
            pass

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CONFIG_GOOGLE_SETUP",
        entity="config",
        entity_id=None,
        success=True,
        message="updated_google_setup",
        before=before,
        after=cfg,
    )
    return await get_google_setup(user)

