from __future__ import annotations

import asyncio
import json
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path

import gspread
from gspread.utils import rowcol_to_a1

from server.config.config_loader import load_master_config
from server.config.paths import backups_root
from server.services.gsheets import get_client, sync_all_to_sheets
from server.services.system_backup import create_backup_archive, restore_backup_archive


logger = logging.getLogger(__name__)

_SNAPSHOT_DIRNAME = "sheet-operation-snapshots"
_SNAPSHOT_FILE_RE = re.compile(r"^sheet-op-(?P<snapshot_id>[a-z0-9-]+)\.zip$")
_MAX_SNAPSHOTS = 20


def sheet_operation_snapshots_root() -> Path:
    root = backups_root() / _SNAPSHOT_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_token(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower())
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "snapshot"


def _capture_sheet_tabs_blocking(sheet_id: str) -> list[dict[str, object]]:
    client = get_client()
    if not client or not sheet_id:
        return []

    sheet = client.open_by_key(sheet_id)
    out: list[dict[str, object]] = []
    for ws in sheet.worksheets():
        values = ws.get_all_values()
        out.append(
            {
                "title": str(ws.title or ""),
                "values": values,
            }
        )
    return out


def _restore_sheet_tabs_blocking(sheet_id: str, tabs: list[dict[str, object]]) -> None:
    client = get_client()
    if not client:
        raise RuntimeError("gsheets_not_configured")
    if not sheet_id:
        raise RuntimeError("sheet_missing")

    sheet = client.open_by_key(sheet_id)
    for raw in tabs:
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        values = raw.get("values") if isinstance(raw.get("values"), list) else []
        ws = None
        try:
            ws = sheet.worksheet(title)
        except Exception:
            ws = sheet.add_worksheet(title=title, rows=2000, cols=20)

        rows = [row if isinstance(row, list) else [str(row)] for row in values]
        if not rows:
            ws.clear()
            continue

        col_count = max(len(row) for row in rows) if rows else 1
        end_col = rowcol_to_a1(1, max(1, col_count)).split("1")[0]
        ws.clear()
        ws.update(f"A1:{end_col}{len(rows)}", rows)


def _snapshot_archive_path(snapshot_id: str) -> Path:
    safe_id = _sanitize_token(snapshot_id)
    path = sheet_operation_snapshots_root() / f"sheet-op-{safe_id}.zip"
    if not path.exists():
        raise FileNotFoundError("sheet_snapshot_not_found")
    return path


def _load_snapshot_archive(snapshot_id: str) -> tuple[Path, dict[str, object], list[dict[str, object]]]:
    path = _snapshot_archive_path(snapshot_id)
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        tabs: list[dict[str, object]] = []
        if "sheet-values.json" in zf.namelist():
            raw_tabs = json.loads(zf.read("sheet-values.json").decode("utf-8"))
            if isinstance(raw_tabs, list):
                tabs = [item for item in raw_tabs if isinstance(item, dict)]
    return path, manifest if isinstance(manifest, dict) else {}, tabs


def _cleanup_old_snapshots() -> None:
    archives = sorted(
        [path for path in sheet_operation_snapshots_root().glob("sheet-op-*.zip") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in archives[_MAX_SNAPSHOTS:]:
        try:
            stale.unlink()
        except Exception:
            logger.warning("Failed to prune stale sheet snapshot archive: %s", stale)


def _manifest_summary(manifest: dict[str, object], archive_path: Path) -> dict[str, object]:
    backup_file_name = str(manifest.get("backup_file_name") or "")
    backup_path = backups_root() / backup_file_name if backup_file_name else None
    tab_titles = manifest.get("tab_titles")
    if not isinstance(tab_titles, list):
        tab_titles = []
    return {
        "id": str(manifest.get("id") or ""),
        "created_at": str(manifest.get("created_at") or ""),
        "operation": str(manifest.get("operation") or ""),
        "note": str(manifest.get("note") or ""),
        "sheet_id": str(manifest.get("sheet_id") or ""),
        "has_sheet_snapshot": bool(manifest.get("has_sheet_snapshot")),
        "tab_count": int(manifest.get("tab_count") or 0),
        "tab_titles": [str(title or "") for title in tab_titles if str(title or "").strip()],
        "backup_file_name": backup_file_name,
        "backup_exists": bool(backup_path and backup_path.exists()),
        "archive_file_name": archive_path.name,
    }


async def create_sheet_operation_snapshot(operation: str, *, note: str = "") -> dict[str, object]:
    created_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    snapshot_id = _sanitize_token(f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}-{operation}")
    archive_path = sheet_operation_snapshots_root() / f"sheet-op-{snapshot_id}.zip"

    backup = await create_backup_archive(f"before-{operation}")

    cfg = load_master_config()
    sheet_id = str(cfg.get("google_sheets_id") or (cfg.get("google_sheets") or {}).get("sheet_id") or "")
    tabs: list[dict[str, object]] = []
    if sheet_id:
        try:
            tabs = await asyncio.to_thread(_capture_sheet_tabs_blocking, sheet_id)
        except Exception:
            logger.exception("Failed to capture Google Sheets snapshot for operation %s", operation)

    manifest: dict[str, object] = {
        "id": snapshot_id,
        "created_at": created_at,
        "operation": _sanitize_token(operation),
        "note": str(note or ""),
        "sheet_id": sheet_id,
        "has_sheet_snapshot": bool(tabs),
        "tab_count": len(tabs),
        "tab_titles": [str(item.get("title") or "") for item in tabs],
        "backup_file_name": str(backup.get("file_name") or ""),
        "backup_size_bytes": int(backup.get("size_bytes") or 0),
    }

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if tabs:
            zf.writestr("sheet-values.json", json.dumps(tabs, ensure_ascii=False))

    _cleanup_old_snapshots()
    return _manifest_summary(manifest, archive_path)


def list_sheet_operation_snapshots(limit: int = 10) -> list[dict[str, object]]:
    archives = sorted(
        [path for path in sheet_operation_snapshots_root().glob("sheet-op-*.zip") if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    out: list[dict[str, object]] = []
    for archive_path in archives[: max(1, limit)]:
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            if isinstance(manifest, dict):
                out.append(_manifest_summary(manifest, archive_path))
        except Exception:
            logger.exception("Failed to read sheet snapshot manifest: %s", archive_path)
    return out


async def rollback_to_sheet_operation_snapshot(snapshot_id: str) -> dict[str, object]:
    archive_path, manifest, tabs = _load_snapshot_archive(snapshot_id)

    rollback_backup = await create_backup_archive("before-sheet-rollback")

    backup_file_name = str(manifest.get("backup_file_name") or "")
    if not backup_file_name:
        raise FileNotFoundError("sheet_snapshot_backup_missing")

    backup_path = backups_root() / backup_file_name
    if not backup_path.exists():
        raise FileNotFoundError("sheet_snapshot_backup_missing")

    restored = await restore_backup_archive(backup_path.read_bytes())

    sheet_restored = False
    sheet_resynced = False
    sheet_error = ""
    snapshot_sheet_id = str(manifest.get("sheet_id") or "")

    if tabs and snapshot_sheet_id:
        try:
            await asyncio.to_thread(_restore_sheet_tabs_blocking, snapshot_sheet_id, tabs)
            sheet_restored = True
        except Exception as exc:
            sheet_error = str(exc)
            logger.exception("Failed to restore Google Sheets snapshot %s", snapshot_id)

    if not sheet_restored and snapshot_sheet_id:
        try:
            await sync_all_to_sheets(fail_if_busy=True)
            sheet_resynced = True
        except Exception as exc:
            if sheet_error:
                sheet_error = f"{sheet_error}; {exc}"
            else:
                sheet_error = str(exc)

    return {
        "ok": True,
        "snapshot_id": str(manifest.get("id") or snapshot_id),
        "snapshot_created_at": str(manifest.get("created_at") or ""),
        "snapshot_operation": str(manifest.get("operation") or ""),
        "snapshot_archive_file_name": archive_path.name,
        "rollback_backup_file_name": str(rollback_backup.get("file_name") or ""),
        "rollback_backup_download_url": f"/api/dev/backup/download/{rollback_backup.get('file_name')}" if rollback_backup.get("file_name") else "",
        "restored_counts": {str(key): int(value or 0) for key, value in restored.items()},
        "sheet_restored": sheet_restored,
        "sheet_resynced": sheet_resynced,
        "sheet_error": sheet_error or None,
    }
