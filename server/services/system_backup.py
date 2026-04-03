from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import orjson
from sqlalchemy import delete, select

from server.config.config_loader import load_master_config, write_master_config
from server.config.paths import app_db_path, backups_root, media_root, repo_root
from server.db.database import SessionLocal
from server.db.models import AuditLog, LoginLock, Product, RefreshSession, Role, StockAlertState, StockStatus, StockTransaction, TxnType, User


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


async def build_backup_payload() -> dict:
    cfg = load_master_config()
    async with SessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        products = (await db.execute(select(Product))).scalars().all()
        txns = (await db.execute(select(StockTransaction))).scalars().all()
        alerts = (await db.execute(select(StockAlertState))).scalars().all()
        audit_logs = (await db.execute(select(AuditLog))).scalars().all()

    return {
        "meta": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "format": "stock-penaek-backup-v2",
            "database": {
                "engine": "sqlite",
                "file_name": app_db_path().name,
            },
            "counts": {
                "users": len(users),
                "products": len(products),
                "transactions": len(txns),
                "alert_states": len(alerts),
                "audit_logs": len(audit_logs),
            },
        },
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role.value,
                "is_active": u.is_active,
                "language": u.language,
                "password_hash": u.password_hash,
                "totp_secret": u.totp_secret,
                "created_at": _dt(u.created_at),
                "updated_at": _dt(u.updated_at),
            }
            for u in users
        ],
        "products": [
            {
                "id": p.id,
                "sku": p.sku,
                "category_id": p.category_id,
                "last_category_id": p.last_category_id,
                "name_th": p.name_th,
                "name_en": p.name_en,
                "category": p.category,
                "type": p.type,
                "unit": p.unit,
                "cost_price": str(p.cost_price),
                "selling_price": str(p.selling_price) if p.selling_price is not None else None,
                "stock_qty": str(p.stock_qty),
                "min_stock": str(p.min_stock),
                "max_stock": str(p.max_stock),
                "status": p.status.value,
                "is_test": p.is_test,
                "supplier": p.supplier,
                "barcode": p.barcode,
                "image_url": p.image_url,
                "notes": p.notes,
                "created_by": p.created_by,
                "created_at": _dt(p.created_at),
                "updated_at": _dt(p.updated_at),
            }
            for p in products
        ],
        "transactions": [
            {
                "id": t.id,
                "type": t.type.value,
                "product_id": t.product_id,
                "sku": t.sku,
                "qty": str(t.qty),
                "unit_cost": str(t.unit_cost) if t.unit_cost is not None else None,
                "unit_price": str(t.unit_price) if t.unit_price is not None else None,
                "reason": t.reason,
                "approval_required": t.approval_required,
                "approved_by": t.approved_by,
                "created_by": t.created_by,
                "created_at": _dt(t.created_at),
            }
            for t in txns
        ],
        "alert_states": [
            {
                "id": a.id,
                "product_id": a.product_id,
                "last_low_level_pct": a.last_low_level_pct,
                "last_high_level_pct": a.last_high_level_pct,
                "last_pct": str(a.last_pct) if a.last_pct is not None else None,
                "updated_at": _dt(a.updated_at),
            }
            for a in alerts
        ],
        "audit_logs": [
            {
                "id": a.id,
                "actor_user_id": a.actor_user_id,
                "actor_username": a.actor_username,
                "actor_role": a.actor_role.value if a.actor_role else None,
                "action": a.action,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "ip": a.ip,
                "user_agent": a.user_agent,
                "success": a.success,
                "before_json": a.before_json,
                "after_json": a.after_json,
                "message": a.message,
                "created_at": _dt(a.created_at),
            }
            for a in audit_logs
        ],
        "settings": cfg,
    }


async def create_backup_archive(label: str = "manual") -> dict:
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-") or "backup"
    filename = f"stock-penaek-backup-{safe_label}-{ts}.zip"
    path = backups_root() / filename
    payload = await build_backup_payload()
    payload_bytes = orjson.dumps(payload)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("backup/data.json", payload_bytes)
        zf.writestr(
            "backup/manifest.json",
            json.dumps(
                {
                    "format": "stock-penaek-backup-v2",
                    "database_file": app_db_path().name,
                    "created_at": payload["meta"]["created_at"],
                    "label": safe_label,
                    "counts": payload["meta"]["counts"],
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        zf.writestr("backup/config.json", json.dumps(load_master_config(), ensure_ascii=False, indent=2))

        media = media_root()
        if media.exists():
            for file_path in media.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=str(Path("backup/media") / file_path.relative_to(media)))

    return {
        "file_name": filename,
        "file_path": str(path),
        "size_bytes": path.stat().st_size,
        "counts": payload["meta"]["counts"],
    }


def _extract_backup_json(zip_bytes: bytes) -> tuple[dict, dict | None, list[tuple[str, bytes]]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
        data_name = "backup/data.json" if "backup/data.json" in names else "data.json"
        config_name = "backup/config.json" if "backup/config.json" in names else "config.json"
        if data_name not in names:
            raise ValueError("backup_data_missing")
        payload = orjson.loads(zf.read(data_name))
        config = None
        if config_name in names:
            config = json.loads(zf.read(config_name).decode("utf-8"))

        media_files: list[tuple[str, bytes]] = []
        for name in zf.namelist():
            if not name.startswith("backup/media/") or name.endswith("/"):
                continue
            media_files.append((name[len("backup/media/") :], zf.read(name)))
        return payload, config, media_files


def preview_backup_archive(zip_bytes: bytes) -> dict:
    payload, config, media_files = _extract_backup_json(zip_bytes)
    meta = dict(payload.get("meta") or {})
    counts = dict(meta.get("counts") or {})
    return {
        "created_at": str(meta.get("created_at") or ""),
        "counts": {
            "users": int(counts.get("users") or len(payload.get("users") or [])),
            "products": int(counts.get("products") or len(payload.get("products") or [])),
            "transactions": int(counts.get("transactions") or len(payload.get("transactions") or [])),
            "alert_states": int(counts.get("alert_states") or len(payload.get("alert_states") or [])),
            "audit_logs": int(counts.get("audit_logs") or len(payload.get("audit_logs") or [])),
            "media_files": int(len(media_files)),
        },
        "sheet_id": str((config or {}).get("google_sheets_id") or ((config or {}).get("google_sheets") or {}).get("sheet_id") or ""),
        "app_name": str((config or {}).get("app_name") or ""),
    }


async def restore_backup_archive(zip_bytes: bytes) -> dict:
    payload, config, media_files = _extract_backup_json(zip_bytes)
    users = payload.get("users") or []
    products = payload.get("products") or []
    transactions = payload.get("transactions") or []
    alert_states = payload.get("alert_states") or []
    audit_logs = payload.get("audit_logs") or []

    async with SessionLocal() as db:
        await db.execute(delete(LoginLock))
        await db.execute(delete(RefreshSession))
        await db.execute(delete(StockAlertState))
        await db.execute(delete(StockTransaction))
        await db.execute(delete(Product))
        await db.execute(delete(AuditLog))
        await db.execute(delete(User))

        for raw in users:
            db.add(
                User(
                    id=str(raw["id"]),
                    username=str(raw.get("username") or ""),
                    display_name=str(raw.get("display_name") or ""),
                    role=Role(str(raw.get("role") or Role.STOCK.value)),
                    is_active=bool(raw.get("is_active", True)),
                    language=str(raw.get("language") or "th"),
                    password_hash=str(raw.get("password_hash") or ""),
                    totp_secret=raw.get("totp_secret"),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in products:
            db.add(
                Product(
                    id=str(raw["id"]),
                    sku=str(raw.get("sku") or ""),
                    category_id=raw.get("category_id"),
                    last_category_id=raw.get("last_category_id"),
                    name_th=str(raw.get("name_th") or ""),
                    name_en=str(raw.get("name_en") or ""),
                    category=str(raw.get("category") or ""),
                    type=str(raw.get("type") or ""),
                    unit=str(raw.get("unit") or ""),
                    cost_price=float(raw.get("cost_price") or 0),
                    selling_price=float(raw["selling_price"]) if raw.get("selling_price") not in (None, "") else None,
                    stock_qty=float(raw.get("stock_qty") or 0),
                    min_stock=float(raw.get("min_stock") or 0),
                    max_stock=float(raw.get("max_stock") or 0),
                    status=StockStatus(str(raw.get("status") or StockStatus.NORMAL.value)),
                    is_test=bool(raw.get("is_test", False)),
                    supplier=str(raw.get("supplier") or ""),
                    barcode=str(raw.get("barcode") or ""),
                    image_url=raw.get("image_url"),
                    notes=str(raw.get("notes") or ""),
                    created_by=str(raw.get("created_by") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in transactions:
            db.add(
                StockTransaction(
                    id=str(raw["id"]),
                    type=TxnType(str(raw.get("type") or TxnType.ADJUST.value)),
                    product_id=str(raw.get("product_id") or ""),
                    sku=str(raw.get("sku") or ""),
                    qty=float(raw.get("qty") or 0),
                    unit_cost=float(raw["unit_cost"]) if raw.get("unit_cost") not in (None, "") else None,
                    unit_price=float(raw["unit_price"]) if raw.get("unit_price") not in (None, "") else None,
                    reason=str(raw.get("reason") or ""),
                    approval_required=bool(raw.get("approval_required", False)),
                    approved_by=raw.get("approved_by"),
                    created_by=str(raw.get("created_by") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                )
            )

        for raw in alert_states:
            db.add(
                StockAlertState(
                    id=str(raw["id"]),
                    product_id=str(raw.get("product_id") or ""),
                    last_low_level_pct=raw.get("last_low_level_pct"),
                    last_high_level_pct=raw.get("last_high_level_pct"),
                    last_pct=float(raw["last_pct"]) if raw.get("last_pct") not in (None, "") else None,
                    updated_at=_parse_dt(raw.get("updated_at")) or datetime.utcnow(),
                )
            )

        for raw in audit_logs:
            role_value = raw.get("actor_role")
            db.add(
                AuditLog(
                    id=str(raw["id"]),
                    actor_user_id=raw.get("actor_user_id"),
                    actor_username=raw.get("actor_username"),
                    actor_role=Role(str(role_value)) if role_value else None,
                    action=str(raw.get("action") or ""),
                    entity=str(raw.get("entity") or ""),
                    entity_id=raw.get("entity_id"),
                    ip=raw.get("ip"),
                    user_agent=raw.get("user_agent"),
                    success=bool(raw.get("success", True)),
                    before_json=raw.get("before_json"),
                    after_json=raw.get("after_json"),
                    message=str(raw.get("message") or ""),
                    created_at=_parse_dt(raw.get("created_at")) or datetime.utcnow(),
                )
            )

        await db.commit()

    media = media_root()
    if media.exists():
        shutil.rmtree(media, ignore_errors=True)
    media.mkdir(parents=True, exist_ok=True)
    for rel_path, data in media_files:
        target = media / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    if isinstance(config, dict):
        write_master_config(config)

    return {
        "users": len(users),
        "products": len(products),
        "transactions": len(transactions),
        "alert_states": len(alert_states),
        "audit_logs": len(audit_logs),
        "media_files": len(media_files),
    }
