from __future__ import annotations

import gzip
from datetime import datetime
from pathlib import Path

import orjson
from sqlalchemy import select

from server.config.config_loader import load_master_config
from server.db.database import SessionLocal
from server.db.models import Product, StockTransaction, User


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


async def run_backup() -> dict:
    root = repo_root()
    backups_dir = root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    cfg = load_master_config()
    max_files = int(cfg.get("max_backup_files") or 30)

    async with SessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        products = (await db.execute(select(Product))).scalars().all()
        txns = (await db.execute(select(StockTransaction))).scalars().all()

    payload = {
        "meta": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "counts": {"users": len(users), "products": len(products), "transactions": len(txns)},
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
                "created_at": u.created_at.isoformat(),
                "updated_at": u.updated_at.isoformat(),
            }
            for u in users
        ],
        "products": [
            {
                "id": p.id,
                "sku": p.sku,
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
                "created_at": p.created_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
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
                "created_at": t.created_at.isoformat(),
            }
            for t in txns
        ],
        "settings": cfg,
    }

    raw = orjson.dumps(payload)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = backups_dir / f"backup-{ts}.json.gz"
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(raw)

    files = sorted(backups_dir.glob("backup-*.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max_files:]:
        old.unlink(missing_ok=True)

    return {"file": str(path), "size_bytes": path.stat().st_size, "counts": payload["meta"]["counts"]}


if __name__ == "__main__":
    import asyncio

    print(asyncio.run(run_backup()))

