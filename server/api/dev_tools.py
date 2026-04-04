from __future__ import annotations

from datetime import datetime, timedelta
from fnmatch import fnmatch
from pathlib import Path
import json
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.api.schemas import (
    GarbageDeleteIn,
    GarbageDeleteOut,
    GarbageFileOut,
    GarbageScanOut,
    GarbageWhitelistOut,
    GarbageWhitelistUpdateIn,
)
from server.db.database import get_db
from server.db.models import Role, User
from server.services.audit import write_audit_log


router = APIRouter(prefix="/dev/garbage", tags=["dev-garbage"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WHITELIST_FILE = PROJECT_ROOT / ".garbage-whitelist.json"
BACKUP_ROOT = PROJECT_ROOT / ".trash-backup"

TEMP_FILE_SUFFIXES = {".tmp", ".temp", ".log", ".cache", ".bak", ".old", ".orig", ".swp"}
GARBAGE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".parcel-cache",
    ".turbo",
    "coverage",
}


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(p.resolve()).replace("\\", "/")


def _load_whitelist() -> list[str]:
    if not WHITELIST_FILE.exists():
        return []
    try:
        data = json.loads(WHITELIST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        return []
    return []


def _save_whitelist(items: list[str]) -> None:
    cleaned = sorted(set([str(x).strip() for x in items if str(x).strip()]))
    WHITELIST_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_whitelisted(rel_path: str, rules: list[str]) -> bool:
    rp = rel_path.replace("\\", "/")
    for r in rules:
        rule = r.replace("\\", "/")
        if fnmatch(rp, rule) or rp == rule:
            return True
    return False


def _dir_size_bytes(p: Path) -> int:
    total = 0
    for root, _, files in os.walk(p):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat().st_size
            except Exception:
                pass
    return total


def _build_item(path: Path, category: str, file_type: str, whitelisted: bool) -> GarbageFileOut:
    stat = path.stat()
    size = stat.st_size if path.is_file() else _dir_size_bytes(path)
    return GarbageFileOut(
        id=uuid.uuid4().hex,
        path=_rel(path),
        absolute_path=str(path.resolve()),
        category=category,
        file_type=file_type,
        size_bytes=size,
        created_at=datetime.fromtimestamp(stat.st_ctime),
        modified_at=datetime.fromtimestamp(stat.st_mtime),
        whitelisted=whitelisted,
    )


def _scan_candidates() -> list[tuple[Path, str, str]]:
    now = datetime.utcnow()
    old_build_cutoff = now - timedelta(days=3)
    backup_cutoff = now - timedelta(days=30)
    out: list[tuple[Path, str, str]] = []
    root_nm = (PROJECT_ROOT / "node_modules").resolve()

    for root, dirs, files in os.walk(PROJECT_ROOT):
        root_path = Path(root)
        rel_root = _rel(root_path)
        if rel_root.startswith(".git"):
            dirs[:] = []
            continue

        for d in list(dirs):
            dp = root_path / d
            d_lower = d.lower()
            if d in GARBAGE_DIR_NAMES:
                out.append((dp, "cache", "directory"))
                dirs.remove(d)
                continue
            if d_lower == "node_modules":
                if dp.resolve() != root_nm:
                    out.append((dp, "duplicate_node_modules", "directory"))
                    dirs.remove(d)
                continue
            if d_lower in {"dist", "build"}:
                try:
                    mtime = datetime.fromtimestamp(dp.stat().st_mtime)
                    if mtime < old_build_cutoff:
                        out.append((dp, "old_build", "directory"))
                except Exception:
                    pass

        for f in files:
            fp = root_path / f
            suffix = fp.suffix.lower()
            name = f.lower()
            if suffix in TEMP_FILE_SUFFIXES:
                out.append((fp, "temp_or_log", "file"))
                continue
            if name.endswith(".backup") or name.endswith(".bak") or name.endswith(".old"):
                try:
                    if datetime.fromtimestamp(fp.stat().st_mtime) < backup_cutoff:
                        out.append((fp, "expired_backup", "file"))
                except Exception:
                    pass

    return out


@router.get("/whitelist", response_model=GarbageWhitelistOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def get_whitelist():
    return GarbageWhitelistOut(items=_load_whitelist())


@router.put("/whitelist", response_model=GarbageWhitelistOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def update_whitelist(payload: GarbageWhitelistUpdateIn):
    _save_whitelist(payload.items)
    return GarbageWhitelistOut(items=_load_whitelist())


@router.get("/scan", response_model=GarbageScanOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def scan_garbage(include_whitelisted: bool = False):
    rules = _load_whitelist()
    items: list[GarbageFileOut] = []
    for p, category, file_type in _scan_candidates():
        rel = _rel(p)
        is_white = _is_whitelisted(rel, rules)
        if is_white and not include_whitelisted:
            continue
        try:
            items.append(_build_item(p, category, file_type, is_white))
        except Exception:
            pass
    total_size = sum([x.size_bytes for x in items])
    return GarbageScanOut(items=items, total_files=len(items), total_size_bytes=total_size)


@router.post("/delete", response_model=GarbageDeleteOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def delete_garbage(
    payload: GarbageDeleteIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm_required")
    if not payload.paths:
        return GarbageDeleteOut(ok=True, deleted_count=0, failed_count=0, moved_to_backup=False, backup_path=None, errors=[])

    rules = _load_whitelist()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / timestamp if payload.mode == "backup" else None
    if backup_dir is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)

    deleted = 0
    failed = 0
    errors: list[str] = []

    for rel_path in payload.paths:
        rel_norm = str(rel_path).replace("\\", "/").strip().lstrip("/")
        if not rel_norm:
            continue
        if _is_whitelisted(rel_norm, rules):
            failed += 1
            errors.append(f"{rel_norm}: whitelisted")
            continue
        target = (PROJECT_ROOT / rel_norm).resolve()
        if not str(target).startswith(str(PROJECT_ROOT.resolve())):
            failed += 1
            errors.append(f"{rel_norm}: outside_project")
            continue
        if not target.exists():
            continue

        try:
            if payload.mode == "backup":
                assert backup_dir is not None
                dst = (backup_dir / rel_norm).resolve()
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(dst))
            else:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            deleted += 1
        except Exception as e:
            failed += 1
            errors.append(f"{rel_norm}: {e}")

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="DEV_GARBAGE_DELETE",
        entity="filesystem",
        entity_id=None,
        success=(failed == 0),
        message="garbage_delete",
        before=None,
        after={"deleted": deleted, "failed": failed, "mode": payload.mode},
        commit=True,
    )

    return GarbageDeleteOut(
        ok=(failed == 0),
        deleted_count=deleted,
        failed_count=failed,
        moved_to_backup=(payload.mode == "backup"),
        backup_path=(str(backup_dir) if backup_dir is not None else None),
        errors=errors,
    )

