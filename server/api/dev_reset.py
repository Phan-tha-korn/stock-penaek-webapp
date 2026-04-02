from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.db.database import get_db
from server.db.models import Product, Role, StockAlertState, StockTransaction, User
from server.services.audit import write_audit_log
from server.services.gsheets import schedule_sheet_sync
from server.services.system_backup import create_backup_archive


router = APIRouter(prefix="/dev/reset", tags=["dev-reset"])


class ResetStockOut(BaseModel):
    deleted_products: int
    deleted_transactions: int
    deleted_alert_states: int
    backup_file_name: str
    backup_download_url: str


class ResetStockIn(BaseModel):
    password: str


@router.post("/stock", response_model=ResetStockOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def reset_stock(
    request: Request,
    payload: ResetStockIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if (payload.password or "").strip() != "phanthakorn":
        raise HTTPException(status_code=403, detail="invalid_dev_password")

    backup = await create_backup_archive("before-reset-stock")
    before_products = int(await db.scalar(select(func.count()).select_from(Product)) or 0)
    before_txns = int(await db.scalar(select(func.count()).select_from(StockTransaction)) or 0)
    before_alerts = int(await db.scalar(select(func.count()).select_from(StockAlertState)) or 0)

    r1 = await db.execute(delete(StockAlertState))
    r2 = await db.execute(delete(StockTransaction))
    r3 = await db.execute(delete(Product))
    await db.commit()

    deleted_alerts = int(r1.rowcount or 0)
    deleted_txns = int(r2.rowcount or 0)
    deleted_products = int(r3.rowcount or 0)

    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="DEV_RESET_STOCK",
        entity="stock",
        entity_id=None,
        success=True,
        message=f"deleted products={deleted_products}, txns={deleted_txns}, alerts={deleted_alerts}",
        before={"products": before_products, "transactions": before_txns, "alert_states": before_alerts},
        after={"products": 0, "transactions": 0, "alert_states": 0},
    )
    try:
        schedule_sheet_sync()
    except Exception:
        pass
    return ResetStockOut(
        deleted_products=deleted_products,
        deleted_transactions=deleted_txns,
        deleted_alert_states=deleted_alerts,
        backup_file_name=str(backup["file_name"]),
        backup_download_url=f"/api/dev/backup/download/{backup['file_name']}",
    )
