from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.api.schemas import SheetsRollbackIn, SheetsRollbackOut, SheetsSnapshotListOut, SheetsSnapshotOut, SheetsSyncOut
from server.config.config_loader import load_master_config, resolve_repo_path, write_master_config
from server.config.settings import refresh_runtime_settings_from_master_config, settings
from server.db.database import SessionLocal, get_db
from server.db.models import Role, User
from server.services.audit import write_audit_log
from server.services.gsheets import (
    TAB_ACCOUNTING,
    TAB_AUDIT_LOG,
    TAB_PRODUCT_IMPORT,
    TAB_STOCK,
    TAB_USERS,
    _build_import_template_rows,
    _collect_products_for_sheet_rows,
    _find_existing_tab,
    _ensure_tab,
    create_stock_workbook,
    get_client,
    sync_product_import_template_to_sheet,
)
from server.services.sheets_snapshots import (
    create_sheet_operation_snapshot,
    list_sheet_operation_snapshots,
    rollback_to_sheet_operation_snapshot,
)


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
    import_tab_url: str
    accounting_tab_url: str
    logs_tab_url: str
    users_tab_url: str
    stock_download_url: str
    import_download_url: str
    accounting_download_url: str
    logs_download_url: str
    users_download_url: str
    product_import_template_download_url: str


class DevSheetsCreateIn(BaseModel):
    title: str
    share_emails: list[str] = []
    set_as_default: bool = True


class DevSheetsCreateOut(BaseModel):
    sheet_id: str
    sheet_url: str
    download_xlsx_url: str


def _snapshot_fields(snapshot: dict | None) -> dict[str, str | None]:
    if not isinstance(snapshot, dict):
        return {
            "snapshot_id": None,
            "snapshot_created_at": None,
            "snapshot_backup_file_name": None,
        }
    return {
        "snapshot_id": str(snapshot.get("id") or "") or None,
        "snapshot_created_at": str(snapshot.get("created_at") or "") or None,
        "snapshot_backup_file_name": str(snapshot.get("backup_file_name") or "") or None,
    }


def _csv_stream(rows: list[list[object]], file_name: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    buffer = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return StreamingResponse(
        buffer,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/config", response_model=DevSheetsConfigOut, dependencies=[Depends(require_roles([Role.DEV, Role.OWNER, Role.ADMIN, Role.ACCOUNTANT]))])
async def get_sheets_config():
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    key_path = str(
        resolve_repo_path(
            str(
                cfg.get("google_service_account_key_path")
                or cfg.get("google_sheets", {}).get("service_account_key_path")
                or settings.google_service_account_key_path
                or ""
            ),
            fallback_relative="credentials/google_key.json",
        )
    )
    enabled = bool(sheet_id)
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}" if sheet_id else ""
    download_xlsx_url = f"{sheet_url}/export?format=xlsx" if sheet_url else ""
    stock_tab_url = sheet_url
    import_tab_url = sheet_url
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
                import_ws = _find_existing_tab(sheet, TAB_PRODUCT_IMPORT)
                accounting_ws = _find_existing_tab(sheet, TAB_ACCOUNTING)
                logs_ws = _find_existing_tab(sheet, TAB_AUDIT_LOG)
                users_ws = _find_existing_tab(sheet, TAB_USERS)
                stock_tab_url = f"{sheet_url}#gid={stock_ws.id}" if stock_ws else sheet_url
                import_tab_url = f"{sheet_url}#gid={import_ws.id}" if import_ws else sheet_url
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
        import_tab_url=import_tab_url,
        accounting_tab_url=accounting_tab_url,
        logs_tab_url=logs_tab_url,
        users_tab_url=users_tab_url,
        stock_download_url="/api/dev/sheets/export/stock" if enabled else "",
        import_download_url="/api/dev/sheets/export/import" if enabled else "",
        accounting_download_url="/api/dev/sheets/export/accounting" if enabled else "",
        logs_download_url="/api/dev/sheets/export/logs" if enabled else "",
        users_download_url="/api/dev/sheets/export/users" if enabled else "",
        product_import_template_download_url="/api/dev/sheets/export/product-import-template",
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
            refresh_runtime_settings_from_master_config()

        return DevSheetsCreateOut(sheet_id=sheet_id, sheet_url=sheet_url, download_xlsx_url=download_xlsx_url)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="create_failed")


@router.post("/prepare-import-tab", response_model=SheetsSyncOut, dependencies=[Depends(require_roles([Role.DEV, Role.OWNER]))])
async def prepare_import_tab(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    snapshot = await create_sheet_operation_snapshot("prepare-import-tab", note="before refresh import tab")
    try:
        ok = await sync_product_import_template_to_sheet(fail_if_busy=True)
        if not ok:
            return SheetsSyncOut(ok=False, error="sync_skipped", **_snapshot_fields(snapshot))
        await write_audit_log(
            db,
            request=request,
            actor=user,
            action="SHEETS_IMPORT_TEMPLATE_PREPARE",
            entity="sheets",
            entity_id=None,
            success=True,
            message="prepare_import_tab",
            before=None,
            after={"ok": True, **_snapshot_fields(snapshot)},
            commit=True,
        )
        return SheetsSyncOut(ok=True, **_snapshot_fields(snapshot))
    except Exception as exc:
        return SheetsSyncOut(ok=False, error=str(exc), **_snapshot_fields(snapshot))


@router.get("/snapshots", response_model=SheetsSnapshotListOut, dependencies=[Depends(require_roles([Role.DEV, Role.OWNER]))])
async def get_sheet_snapshots():
    items = [SheetsSnapshotOut(**item) for item in list_sheet_operation_snapshots(limit=12)]
    return SheetsSnapshotListOut(items=items)


@router.post("/rollback", response_model=SheetsRollbackOut, dependencies=[Depends(require_roles([Role.DEV, Role.OWNER]))])
async def rollback_sheet_snapshot(
    payload: SheetsRollbackIn,
    request: Request,
    user: User = Depends(get_current_user),
):
    try:
        result = await rollback_to_sheet_operation_snapshot(payload.snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    async with SessionLocal() as audit_db:
        await write_audit_log(
            audit_db,
            request=request,
            actor=user,
            action="SHEETS_ROLLBACK",
            entity="sheets",
            entity_id=payload.snapshot_id,
            success=True,
            message="rollback_sheet_snapshot",
            before=None,
            after=result,
            commit=True,
        )

    return SheetsRollbackOut(
        ok=True,
        snapshot_id=str(result.get("snapshot_id") or payload.snapshot_id),
        snapshot_created_at=str(result.get("snapshot_created_at") or ""),
        snapshot_operation=str(result.get("snapshot_operation") or ""),
        snapshot_archive_file_name=str(result.get("snapshot_archive_file_name") or ""),
        rollback_backup_file_name=str(result.get("rollback_backup_file_name") or ""),
        rollback_backup_download_url=str(result.get("rollback_backup_download_url") or ""),
        restored_counts={str(key): int(value or 0) for key, value in dict(result.get("restored_counts") or {}).items()},
        sheet_restored=bool(result.get("sheet_restored")),
        sheet_resynced=bool(result.get("sheet_resynced")),
        sheet_error=str(result.get("sheet_error") or "") or None,
    )


@router.get("/export/{kind}", dependencies=[Depends(require_roles([Role.DEV, Role.OWNER, Role.ADMIN, Role.ACCOUNTANT]))])
async def export_sheet(kind: str):
    kind_key = (kind or "").strip().lower()
    if kind_key in ("product-import-template", "template", "product-template"):
        rows = _build_import_template_rows(await _collect_products_for_sheet_rows())
        return _csv_stream(rows, "product-import-template.csv")

    mapping = {
        "stock": TAB_STOCK,
        "import": TAB_PRODUCT_IMPORT,
        "product-import": TAB_PRODUCT_IMPORT,
        "accounting": TAB_ACCOUNTING,
        "logs": TAB_AUDIT_LOG,
        "users": TAB_USERS,
    }
    tab = mapping.get(kind_key)
    if not tab:
        raise HTTPException(status_code=400, detail="invalid_export_kind")
    client = get_client()
    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or cfg.get("google_sheets", {}).get("sheet_id") or "")
    if not client or not sheet_id:
        raise HTTPException(status_code=400, detail="gsheets_not_configured")
    try:
        sheet = client.open_by_key(sheet_id)
        ws = _ensure_tab(sheet, tab, write_header=(tab == TAB_PRODUCT_IMPORT))
        rows = ws.get_all_values()
        file_name = f"{kind_key}-{sheet_id[:8]}.csv"
        return _csv_stream(rows, file_name)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="sheet_export_failed")
