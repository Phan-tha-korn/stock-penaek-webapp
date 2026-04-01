from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from server.api.deps import require_roles
from server.config.config_loader import load_master_config, write_master_config
from server.db.models import Role
from server.services.gsheets import (
    get_client,
    _ensure_tab,
    _style_sheet,
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
)
from server.config.settings import settings


router = APIRouter(prefix="/dev/sheets", tags=["dev-sheets"])


class DevSheetsConfigOut(BaseModel):
    enabled: bool
    sheet_id: str
    key_path: str
    sheet_url: str
    download_xlsx_url: str
    stock_tab_url: str
    accounting_tab_url: str
    logs_tab_url: str
    stock_download_url: str
    accounting_download_url: str
    logs_download_url: str


class DevSheetsCreateIn(BaseModel):
    title: str
    share_emails: list[str] = []
    set_as_default: bool = True


class DevSheetsCreateOut(BaseModel):
    sheet_id: str
    sheet_url: str
    download_xlsx_url: str


@router.get("/config", response_model=DevSheetsConfigOut, dependencies=[Depends(require_roles([Role.DEV, Role.OWNER, Role.ADMIN, Role.ACCOUNTANT]))])
async def get_sheets_config():
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    key_path = str(cfg.get("google_service_account_key_path") or cfg.get("google_sheets", {}).get("service_account_key_path") or settings.google_service_account_key_path or "")
    enabled = bool(sheet_id)
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""
    download_xlsx_url = f"{sheet_url}/export?format=xlsx" if sheet_url else ""
    stock_tab_url = sheet_url
    accounting_tab_url = sheet_url
    logs_tab_url = sheet_url
    if enabled:
        client = get_client()
        if client:
            try:
                sheet = client.open_by_key(sheet_id)
                stock_tab_url = f"{sheet_url}#gid={_ensure_tab(sheet, TAB_STOCK).id}"
                accounting_tab_url = f"{sheet_url}#gid={_ensure_tab(sheet, TAB_ACCOUNTING).id}"
                logs_tab_url = f"{sheet_url}#gid={_ensure_tab(sheet, TAB_AUDIT_LOG).id}"
            except Exception:
                pass
    return DevSheetsConfigOut(
        enabled=enabled,
        sheet_id=sheet_id,
        key_path=key_path,
        sheet_url=sheet_url,
        download_xlsx_url=download_xlsx_url,
        stock_tab_url=stock_tab_url,
        accounting_tab_url=accounting_tab_url,
        logs_tab_url=logs_tab_url,
        stock_download_url="/api/dev/sheets/export/stock" if enabled else "",
        accounting_download_url="/api/dev/sheets/export/accounting" if enabled else "",
        logs_download_url="/api/dev/sheets/export/logs" if enabled else "",
    )


@router.post("/create", response_model=DevSheetsCreateOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def create_new_sheet(payload: DevSheetsCreateIn):
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title_required")

    client = get_client()
    if not client:
        raise HTTPException(status_code=400, detail="gsheets_not_configured")

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

        for e in payload.share_emails or []:
            email = str(e).strip()
            if not email:
                continue
            try:
                sheet.share(email, perm_type="user", role="writer", notify=False)
            except Exception:
                pass

        sheet_id = str(getattr(sheet, "id", "") or "")
        if not sheet_id:
            raise HTTPException(status_code=500, detail="create_failed")

        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        download_xlsx_url = f"{sheet_url}/export?format=xlsx"

        if payload.set_as_default:
            cfg = load_master_config()
            cfg["google_sheets_id"] = sheet_id
            if isinstance(cfg.get("google_sheets"), dict):
                cfg["google_sheets"]["sheet_id"] = sheet_id
            write_master_config(cfg)

        return DevSheetsCreateOut(sheet_id=sheet_id, sheet_url=sheet_url, download_xlsx_url=download_xlsx_url)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="create_failed")


@router.get("/export/{kind}", dependencies=[Depends(require_roles([Role.DEV, Role.OWNER, Role.ADMIN, Role.ACCOUNTANT]))])
async def export_sheet(kind: str):
    mapping = {
        "stock": TAB_STOCK,
        "accounting": TAB_ACCOUNTING,
        "logs": TAB_AUDIT_LOG,
    }
    tab = mapping.get((kind or "").strip().lower())
    if not tab:
        raise HTTPException(status_code=400, detail="invalid_export_kind")
    client = get_client()
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    if not client or not sheet_id:
        raise HTTPException(status_code=400, detail="gsheets_not_configured")
    try:
        sheet = client.open_by_key(sheet_id)
        ws = _ensure_tab(sheet, tab)
        rows = ws.get_all_values()
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows:
            writer.writerow(row)
        buffer = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        file_name = f"{kind}-{sheet_id[:8]}.csv"
        return StreamingResponse(buffer, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="sheet_export_failed")
