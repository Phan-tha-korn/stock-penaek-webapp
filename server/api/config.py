from __future__ import annotations

import logging
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.api.schemas import ConfigUpdateIn, GoogleOAuthStartOut, GoogleSetupIn, GoogleSetupOut, PublicConfig
from server.config.config_loader import load_master_config, repo_root, resolve_repo_path, write_master_config
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
    TAB_USERS,
    _find_existing_tab,
    create_stock_workbook,
    get_client,
    sync_all_to_sheets,
)
import asyncio


router = APIRouter(tags=["config"])
logger = logging.getLogger(__name__)
_OAUTH_PENDING: dict[str, dict[str, str | float]] = {}
_GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

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


def _mask_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _allow_local_oauth_http(redirect_uri: str) -> None:
    parsed = urlsplit(redirect_uri)
    if parsed.scheme != "http":
        return
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        return
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def _relax_google_scope_warning() -> None:
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def _oauth_client_config(cfg: dict, request: Request | None = None) -> tuple[dict, str]:
    client_id = str(cfg.get("google_oauth_client_id") or "")
    client_secret = str(cfg.get("google_oauth_client_secret") or "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="google_oauth_not_ready")
    redirect_uri = str(cfg.get("google_oauth_redirect_uri") or "").strip()
    if request is not None:
        request_redirect_uri = str(request.base_url).rstrip("/") + "/api/config/google-oauth/callback"
        if not redirect_uri:
            redirect_uri = request_redirect_uri
        else:
            configured_origin = urlsplit(redirect_uri)
            request_origin = urlsplit(request_redirect_uri)
            same_origin = (
                configured_origin.scheme == request_origin.scheme
                and configured_origin.netloc == request_origin.netloc
            )
            if not same_origin:
                redirect_uri = request_redirect_uri
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="google_oauth_redirect_missing")
    _allow_local_oauth_http(redirect_uri)
    _relax_google_scope_warning()
    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return config, redirect_uri


def _safe_return_to(value: str, cfg: dict) -> str:
    candidate = (value or "").strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    web_url = str(cfg.get("web_url") or "").strip().rstrip("/")
    if web_url:
        return f"{web_url}/settings#google-setup"
    return "/settings#google-setup"


def _oauth_pending_cleanup(max_age_seconds: int = 900) -> None:
    now = time.time()
    stale_keys = [
        key
        for key, value in _OAUTH_PENDING.items()
        if now - float(value.get("created_at") or 0) > max_age_seconds
    ]
    for key in stale_keys:
        _OAUTH_PENDING.pop(key, None)



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


@router.put("/config", response_model=PublicConfig, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def update_config(
    payload: ConfigUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
        commit=True,
    )

    return await get_public_config()


@router.get("/config/google-setup", response_model=GoogleSetupOut)
async def get_google_setup(user: User = Depends(get_current_user)):
    if user.role not in (Role.OWNER, Role.DEV):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""
    raw_service_account_key_path = str(
        cfg.get("google_service_account_key_path")
        or cfg.get("google_sheets", {}).get("service_account_key_path")
        or ""
    )
    raw_oauth_token_path = str(cfg.get("google_oauth_token_path") or settings.google_oauth_token_path or "")
    resolved_service_account_key_path = resolve_repo_path(
        raw_service_account_key_path,
        fallback_relative="credentials/google_key.json",
    )
    resolved_oauth_token_path = resolve_repo_path(
        raw_oauth_token_path,
        fallback_relative="credentials/google_oauth_token.json",
    )
    usable = False
    err = ""
    if not sheet_id:
        err = "sheet_missing"
    else:
        client = get_client()
        if not client:
            err = "google_client_not_ready"
        else:
            try:
                sheet = client.open_by_key(sheet_id)
                _find_existing_tab(sheet, TAB_STOCK)
                usable = True
            except Exception:
                err = "sheet_open_failed"
    return GoogleSetupOut(
        configured=bool(
            sheet_id
            and (resolved_service_account_key_path.exists() or resolved_oauth_token_path.exists())
        ),
        usable=usable,
        error=err,
        workspace_email=str(cfg.get("google_workspace_email") or ""),
        drive_folder_name=str(cfg.get("google_drive_folder_name") or ""),
        default_sheet_title=str(cfg.get("google_default_sheet_title") or ""),
        service_account_key_path=(
            str(resolved_service_account_key_path)
            if raw_service_account_key_path or resolved_service_account_key_path.exists()
            else ""
        ),
        oauth_client_id=str(cfg.get("google_oauth_client_id") or ""),
        oauth_client_secret_masked=_mask_secret(str(cfg.get("google_oauth_client_secret") or "")),
        oauth_redirect_uri=str(cfg.get("google_oauth_redirect_uri") or ""),
        oauth_token_path=(
            str(resolved_oauth_token_path)
            if raw_oauth_token_path or resolved_oauth_token_path.exists()
            else ""
        ),
        oauth_connected=resolved_oauth_token_path.exists(),
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
    cfg["google_oauth_client_id"] = (payload.oauth_client_id or "").strip()
    if (payload.oauth_client_secret or "").strip():
        cfg["google_oauth_client_secret"] = (payload.oauth_client_secret or "").strip()
    cfg["google_oauth_redirect_uri"] = (payload.oauth_redirect_uri or "").strip()
    cfg["google_oauth_token_path"] = (payload.oauth_token_path or "").strip() or str(cfg.get("google_oauth_token_path") or settings.google_oauth_token_path)
    google_sheets["oauth_client_id"] = cfg["google_oauth_client_id"]
    google_sheets["oauth_client_secret"] = cfg.get("google_oauth_client_secret") or ""
    google_sheets["oauth_redirect_uri"] = cfg["google_oauth_redirect_uri"]
    google_sheets["oauth_token_path"] = cfg["google_oauth_token_path"]

    new_sheet_id = str(cfg.get("google_sheets_id") or google_sheets.get("sheet_id") or "")
    if payload.create_new_sheet:
        if key_path:
            settings.google_service_account_key_path = key_path
        client = get_client()
        if not client:
            raise HTTPException(status_code=400, detail="google_not_ready")
        title = cfg["google_default_sheet_title"]
        try:
            sheet = create_stock_workbook(client, title)
            new_sheet_id = str(getattr(sheet, "id", "") or "")
        except Exception:
            raise HTTPException(status_code=500, detail="google_sheet_create_failed")
        cfg["google_sheets_id"] = new_sheet_id
        google_sheets["sheet_id"] = new_sheet_id

    cfg["google_sheets"] = google_sheets
    write_master_config(cfg)

    settings.google_sheets_id = str(cfg.get("google_sheets_id") or google_sheets.get("sheet_id") or "")
    settings.google_service_account_key_path = str(cfg.get("google_service_account_key_path") or google_sheets.get("service_account_key_path") or settings.google_service_account_key_path)
    settings.google_oauth_client_id = str(cfg.get("google_oauth_client_id") or google_sheets.get("oauth_client_id") or "")
    settings.google_oauth_client_secret = str(cfg.get("google_oauth_client_secret") or google_sheets.get("oauth_client_secret") or "")
    settings.google_oauth_redirect_uri = str(cfg.get("google_oauth_redirect_uri") or google_sheets.get("oauth_redirect_uri") or "")
    settings.google_oauth_token_path = str(cfg.get("google_oauth_token_path") or google_sheets.get("oauth_token_path") or settings.google_oauth_token_path)

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
        commit=True,
    )
    return await get_google_setup(user)


@router.post("/config/google-oauth/start", response_model=GoogleOAuthStartOut)
async def start_google_oauth(request: Request, return_to: str = "", user: User = Depends(get_current_user)):
    if user.role not in (Role.OWNER, Role.DEV):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    cfg = load_master_config()
    client_config, redirect_uri = _oauth_client_config(cfg, request)
    _oauth_pending_cleanup()
    flow = Flow.from_client_config(
        client_config,
        scopes=_GOOGLE_OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )
    oauth_state = secrets.token_urlsafe(24)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=oauth_state,
    )
    _OAUTH_PENDING[oauth_state] = {
        "created_at": time.time(),
        "return_to": _safe_return_to(return_to, cfg),
        "code_verifier": str(getattr(flow, "code_verifier", "") or ""),
    }
    return GoogleOAuthStartOut(auth_url=auth_url)


@router.get("/config/google-oauth/callback")
async def google_oauth_callback(request: Request):
    cfg = load_master_config()
    oauth_state = str(request.query_params.get("state") or "")
    pending = _OAUTH_PENDING.pop(oauth_state, None)
    return_to = _safe_return_to(str((pending or {}).get("return_to") or ""), cfg)
    client_config, redirect_uri = _oauth_client_config(cfg, request)
    flow = Flow.from_client_config(
        client_config,
        scopes=_GOOGLE_OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )
    try:
        code_verifier = str((pending or {}).get("code_verifier") or "")
        if code_verifier:
            flow.code_verifier = code_verifier
        authorization_response = f"{redirect_uri}?{request.url.query}" if request.url.query else redirect_uri
        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials
        token_path = resolve_repo_path(
            str(cfg.get("google_oauth_token_path") or settings.google_oauth_token_path),
            fallback_relative="credentials/google_oauth_token.json",
        )
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        cfg["google_oauth_token_path"] = str(token_path)
        google_sheets = dict(cfg.get("google_sheets") or {})
        google_sheets["oauth_token_path"] = str(token_path)
        cfg["google_sheets"] = google_sheets
        settings.google_oauth_token_path = str(token_path)

        session = flow.authorized_session()
        try:
            profile = session.get("https://openidconnect.googleapis.com/v1/userinfo", timeout=20).json()
            cfg["google_workspace_email"] = str(profile.get("email") or cfg.get("google_workspace_email") or "")
        except Exception:
            pass

        write_master_config(cfg)

        if not str(cfg.get("google_sheets_id") or google_sheets.get("sheet_id") or ""):
            settings.google_sheets_id = ""
            client = get_client()
            if client:
                sheet = create_stock_workbook(client, str(cfg.get("google_default_sheet_title") or "Stock Penaek"))
                sheet_id = str(getattr(sheet, "id", "") or "")
                cfg["google_sheets_id"] = sheet_id
                google_sheets["sheet_id"] = sheet_id
                cfg["google_sheets"] = google_sheets
                settings.google_sheets_id = sheet_id
                write_master_config(cfg)

        try:
            await sync_all_to_sheets()
        except Exception:
            pass
    except HTTPException:
        raise
    except Exception:
        logger.exception("Google OAuth callback failed. redirect_uri=%s query=%s", redirect_uri, request.url.query)
        html = (
            "<html><head><meta charset='utf-8'></head>"
            "<body style='font-family:sans-serif;background:#111;color:#fff;display:flex;align-items:center;"
            "justify-content:center;height:100vh'>"
            "เชื่อม Google ไม่สำเร็จ กรุณากลับไปลองใหม่"
            f"<script>setTimeout(function(){{ window.location.href={return_to!r}; }}, 2200)</script>"
            "</body></html>"
        )
        return HTMLResponse(html, status_code=500)

    if return_to.startswith("http://") or return_to.startswith("https://"):
        return RedirectResponse(return_to, status_code=302)
    return RedirectResponse("/settings#google-setup", status_code=302)
