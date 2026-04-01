from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.api.deps import require_roles
from server.config.config_loader import load_master_config, write_master_config
from server.db.models import Role
from server.services.gsheets import get_client, _ensure_tab, TAB_ADD_LOG, TAB_EDIT_LOG, TAB_EXPENSE_LOG, TAB_INCOME_LOG, TAB_SELL_LOG, TAB_STOCK
from server.config.settings import settings


router = APIRouter(prefix="/dev/sheets", tags=["dev-sheets"])


class DevSheetsConfigOut(BaseModel):
    enabled: bool
    sheet_id: str
    key_path: str


class DevSheetsCreateIn(BaseModel):
    title: str
    share_emails: list[str] = []
    set_as_default: bool = True


class DevSheetsCreateOut(BaseModel):
    sheet_id: str
    sheet_url: str
    download_xlsx_url: str


@router.get("/config", response_model=DevSheetsConfigOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def get_sheets_config():
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    key_path = str(cfg.get("google_service_account_key_path") or cfg.get("google_sheets", {}).get("service_account_key_path") or settings.google_service_account_key_path or "")
    enabled = bool(sheet_id)
    return DevSheetsConfigOut(enabled=enabled, sheet_id=sheet_id, key_path=key_path)


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
        _ensure_tab(sheet, TAB_STOCK)
        _ensure_tab(sheet, TAB_EDIT_LOG)
        _ensure_tab(sheet, TAB_ADD_LOG)
        _ensure_tab(sheet, TAB_SELL_LOG)
        _ensure_tab(sheet, TAB_INCOME_LOG)
        _ensure_tab(sheet, TAB_EXPENSE_LOG)

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
