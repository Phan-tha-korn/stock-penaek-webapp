from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from server.api.deps import require_roles
from server.db.models import Role
from server.services.gsheets import schedule_sheet_sync
from server.services.system_backup import backups_root, create_backup_archive, preview_backup_archive, restore_backup_archive


router = APIRouter(prefix="/dev/backup", tags=["dev-backup"])


def _check_password(password: str) -> None:
    from server.config.settings import settings
    expected = (settings.dev_backup_password or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="dev_backup_password_not_configured")
    if (password or "").strip() != expected:
        raise HTTPException(status_code=403, detail="invalid_dev_password")


class BackupCreateOut(BaseModel):
    ok: bool
    file_name: str
    size_bytes: int
    download_url: str
    counts: dict[str, int]


class BackupRestoreOut(BaseModel):
    ok: bool
    restored: dict[str, int]


class BackupPreviewOut(BaseModel):
    created_at: str
    counts: dict[str, int]
    sheet_id: str = ""
    app_name: str = ""


@router.post("/create", response_model=BackupCreateOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def create_backup(password: str = Form(...)):
    _check_password(password)
    res = await create_backup_archive("manual")
    return BackupCreateOut(
        ok=True,
        file_name=res["file_name"],
        size_bytes=int(res["size_bytes"] or 0),
        download_url=f"/api/dev/backup/download/{res['file_name']}",
        counts={str(k): int(v or 0) for k, v in dict(res.get("counts") or {}).items()},
    )


@router.get("/download/{file_name}", dependencies=[Depends(require_roles([Role.DEV]))])
async def download_backup(file_name: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.zip", file_name):
        raise HTTPException(status_code=400, detail="invalid_file_name")
    path = backups_root() / file_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="backup_not_found")
    return FileResponse(path=path, media_type="application/zip", filename=file_name)


@router.post("/restore", response_model=BackupRestoreOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def restore_backup(
    password: str = Form(...),
    file: UploadFile = File(...),
):
    _check_password(password)
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="backup_zip_required")
    raw = await file.read()
    try:
        restored = await restore_backup_archive(raw)
        try:
            schedule_sheet_sync()
        except Exception:
            pass
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="backup_restore_failed")
    return BackupRestoreOut(ok=True, restored={str(k): int(v or 0) for k, v in restored.items()})


@router.post("/preview", response_model=BackupPreviewOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def preview_backup(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="backup_zip_required")
    raw = await file.read()
    try:
        preview = preview_backup_archive(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="backup_preview_failed")
    return BackupPreviewOut(
        created_at=str(preview.get("created_at") or ""),
        counts={str(k): int(v or 0) for k, v in dict(preview.get("counts") or {}).items()},
        sheet_id=str(preview.get("sheet_id") or ""),
        app_name=str(preview.get("app_name") or ""),
    )
