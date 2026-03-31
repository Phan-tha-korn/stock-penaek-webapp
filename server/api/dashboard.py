from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import require_roles
from server.api.schemas import ActivityItemOut, ActivityListOut, KpisOut, TransactionListOut, TransactionOut
from server.db.database import get_db
from server.db.models import AuditLog, Product, Role, StockTransaction, TxnType, User
from server.realtime.socket_manager import online_count


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DELETED_PREFIX = "__DELETED__:"


def _d(v) -> str:
    if v is None:
        return "0"
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)


@router.get("/kpis", response_model=KpisOut, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def kpis(db: AsyncSession = Depends(get_db)):
    total_products = await db.scalar(select(func.count()).select_from(Product).where(~Product.notes.like(f"{DELETED_PREFIX}%")))

    stock_value = await db.scalar(
        select(func.coalesce(func.sum(Product.stock_qty * Product.cost_price), 0)).where(~Product.notes.like(f"{DELETED_PREFIX}%"))
    )

    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    daily_revenue = await db.scalar(
        select(func.coalesce(func.sum(StockTransaction.qty * StockTransaction.unit_price), 0)).where(
            StockTransaction.type == TxnType.STOCK_OUT,
            StockTransaction.created_at >= start.replace(tzinfo=None),
            StockTransaction.created_at < end.replace(tzinfo=None),
        )
    )

    daily_expense = await db.scalar(
        select(func.coalesce(func.sum(StockTransaction.qty * func.coalesce(StockTransaction.unit_cost, 0)), 0)).where(
            StockTransaction.type == TxnType.STOCK_IN,
            StockTransaction.created_at >= start.replace(tzinfo=None),
            StockTransaction.created_at < end.replace(tzinfo=None),
        )
    )

    return KpisOut(
        total_products=int(total_products or 0),
        stock_value=_d(stock_value),
        daily_revenue=_d(daily_revenue),
        daily_expense=_d(daily_expense),
        active_users_online=online_count(),
    )


@router.get("/activity", response_model=ActivityListOut, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def activity(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50))
    logs = res.scalars().all()
    items = [
        ActivityItemOut(
            id=x.id,
            created_at=x.created_at,
            actor_username=x.actor_username,
            actor_role=x.actor_role,
            action=x.action,
            message=x.message,
        )
        for x in logs
    ]
    return ActivityListOut(items=items)


@router.get(
    "/transactions",
    response_model=TransactionListOut,
    dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))],
)
async def transactions(
    db: AsyncSession = Depends(get_db),
    sku: str | None = None,
    type: TxnType | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(StockTransaction, Product, User)
        .join(Product, Product.id == StockTransaction.product_id)
        .join(User, User.id == StockTransaction.created_by, isouter=True)
    )
    if sku:
        stmt = stmt.where(StockTransaction.sku == sku)
    if type:
        stmt = stmt.where(StockTransaction.type == type)
    if date_from:
        try:
            stmt = stmt.where(StockTransaction.created_at >= datetime.fromisoformat(date_from))
        except Exception:
            pass
    if date_to:
        try:
            stmt = stmt.where(StockTransaction.created_at <= datetime.fromisoformat(date_to))
        except Exception:
            pass

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    res = await db.execute(stmt.order_by(StockTransaction.created_at.desc()).limit(limit).offset(offset))
    rows = res.all()

    items = []
    for txn, p, u in rows:
        items.append(
            TransactionOut(
                id=txn.id,
                created_at=txn.created_at,
                type=txn.type,
                sku=txn.sku,
                product_name=p.name_th,
                qty=_d(txn.qty),
                unit=p.unit,
                note=txn.reason or "",
                actor_username=(u.username if u else None),
            )
        )

    return TransactionListOut(items=items, total=int(total or 0))

