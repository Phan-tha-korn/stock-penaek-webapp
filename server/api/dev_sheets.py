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
    TAB_ACCOUNTING,
    TAB_AUDIT_LOG,
    TAB_STOCK,
    TAB_USERS,
    _find_existing_tab,
    _ensure_tab,
    create_stock_workbook,
    get_client,
)
from server.config.settings import settings


router = APIRouter(prefix="/dev/sheets", tags=["dev-sheets"])


class DevSheetsConfigOut(BaseModel):
    enabled: bool
    usable: bool = False
    error: str = ""
    sheet_id: str
    key_path: str
    sheet_url: str
    download_xlsx_url: str
    stock_tab_url: str
    accounting_tab_url: str
    logs_tab_url: str
    users_tab_url: str
    stock_download_url: str
    accounting_download_url: str
    logs_download_url: str
    users_download_url: str


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
    users_tab_url = sheet_url
    usable = False
    err = ""
    if enabled:
        client = get_client()
        if client:
            try:
                sheet = client.open_by_key(sheet_id)
                stock_ws = _find_existing_tab(sheet, TAB_STOCK)
                accounting_ws = _find_existing_tab(sheet, TAB_ACCOUNTING)
                logs_ws = _find_existing_tab(sheet, TAB_AUDIT_LOG)
                users_ws = _find_existing_tab(sheet, TAB_USERS)
                stock_tab_url = f"{sheet_url}#gid={stock_ws.id}" if stock_ws else sheet_url
                accounting_tab_url = f"{sheet_url}#gid={accounting_ws.id}" if accounting_ws else sheet_url
                logs_tab_url = f"{sheet_url}#gid={logs_ws.id}" if logs_ws else sheet_url
                users_tab_url = f"{sheet_url}#gid={users_ws.id}" if users_ws else sheet_url
                usable = True
            except Exception:
                err = "sheet_open_failed"
        else:
            err = "google_client_not_ready"
    else:
        err = "sheet_missing"
    return DevSheetsConfigOut(
        enabled=enabled,
        usable=usable,
        error=err,
        sheet_id=sheet_id,
        key_path=key_path,
        sheet_url=sheet_url,
        download_xlsx_url=download_xlsx_url,
        stock_tab_url=stock_tab_url,
        accounting_tab_url=accounting_tab_url,
        logs_tab_url=logs_tab_url,
        users_tab_url=users_tab_url,
        stock_download_url="/api/dev/sheets/export/stock" if enabled else "",
        accounting_download_url="/api/dev/sheets/export/accounting" if enabled else "",
        logs_download_url="/api/dev/sheets/export/logs" if enabled else "",
        users_download_url="/api/dev/sheets/export/users" if enabled else "",
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
        sheet = create_stock_workbook(client, title)

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
        "users": TAB_USERS,
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
        ws = _ensure_tab(sheet, tab, write_header=False)
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
