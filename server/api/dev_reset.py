from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.db.database import get_db
from server.db.models import Product, Role, StockAlertState, StockTransaction, User
from server.services.audit import write_audit_log


router = APIRouter(prefix="/dev/reset", tags=["dev-reset"])


class ResetStockOut(BaseModel):
    deleted_products: int
    deleted_transactions: int
    deleted_alert_states: int


@router.post("/stock", response_model=ResetStockOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def reset_stock(
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
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

    return ResetStockOut(
        deleted_products=deleted_products,
        deleted_transactions=deleted_txns,
        deleted_alert_states=deleted_alerts,
    )

