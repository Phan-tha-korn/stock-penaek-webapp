from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import require_roles
from server.api.schemas import (
    ActivityItemOut,
    ActivityListOut,
    KpisOut,
    OwnerStatusSliceOut,
    OwnerSummaryOut,
    OwnerTimelinePointOut,
    StockSummaryOut,
    TransactionListOut,
    TransactionOut,
)
from server.db.database import get_db
from server.db.models import AuditLog, Product, Role, StockStatus, StockTransaction, TxnType, User
from server.realtime.socket_manager import online_count


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DELETED_PREFIX = "__DELETED__:"


def _d(v) -> str:
    if v is None:
        return "0"
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)


def _period_bounds(period: str) -> tuple[datetime, datetime, list[tuple[datetime, datetime, str, str]]]:
    now = datetime.now()
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        buckets = []
        for hour in range(24):
            bucket_start = start + timedelta(hours=hour)
            bucket_end = bucket_start + timedelta(hours=1)
            buckets.append((bucket_start, bucket_end, f"{hour:02d}", f"{hour:02d}:00"))
        return start, end, buckets

    if period == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        buckets = []
        for offset in range(7):
            bucket_start = start + timedelta(days=offset)
            bucket_end = bucket_start + timedelta(days=1)
            buckets.append((bucket_start, bucket_end, bucket_start.strftime("%Y-%m-%d"), bucket_start.strftime("%a")))
        return start, end, buckets

    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_in_month = monthrange(start.year, start.month)[1]
        end = start + timedelta(days=days_in_month)
        buckets = []
        for day in range(days_in_month):
            bucket_start = start + timedelta(days=day)
            bucket_end = bucket_start + timedelta(days=1)
            buckets.append((bucket_start, bucket_end, bucket_start.strftime("%Y-%m-%d"), str(bucket_start.day)))
        return start, end, buckets

    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1)
    buckets = []
    for month in range(1, 13):
        bucket_start = start.replace(month=month)
        bucket_end = start.replace(year=start.year + 1) if month == 12 else start.replace(month=month + 1)
        buckets.append((bucket_start, bucket_end, f"{bucket_start.year}-{bucket_start.month:02d}", bucket_start.strftime("%b")))
    return start, end, buckets


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


@router.get("/stock_summary", response_model=StockSummaryOut, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def stock_summary(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Product.status, func.count())
        .where(~Product.notes.like(f"{DELETED_PREFIX}%"))
        .group_by(Product.status)
    )
    res = await db.execute(stmt)
    rows = res.all()
    by_status: dict[str, int] = {}
    for st, cnt in rows:
        key = st.value if isinstance(st, StockStatus) else str(st)
        by_status[key] = int(cnt or 0)

    total_products = int(sum(by_status.values()))
    return StockSummaryOut(
        total_products=total_products,
        full=int(by_status.get(StockStatus.FULL.value, 0)),
        normal=int(by_status.get(StockStatus.NORMAL.value, 0)),
        low=int(by_status.get(StockStatus.LOW.value, 0)),
        critical=int(by_status.get(StockStatus.CRITICAL.value, 0)),
        out=int(by_status.get(StockStatus.OUT.value, 0)),
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


@router.get(
    "/owner_summary",
    response_model=OwnerSummaryOut,
    dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))],
)
async def owner_summary(
    db: AsyncSession = Depends(get_db),
    period: str = Query(default="week", pattern="^(day|week|month|year)$"),
):
    products = (await db.execute(select(Product).where(~Product.notes.like(f"{DELETED_PREFIX}%")))).scalars().all()
    total_products = len(products)
    stock_value = sum(float(product.stock_qty or 0) * float(product.cost_price or 0) for product in products)
    sales_value = sum(
        float(product.stock_qty or 0) * float(product.selling_price or 0)
        for product in products
        if product.selling_price is not None
    )
    user_total = int(await db.scalar(select(func.count()).select_from(User)) or 0)

    status_map: dict[str, int] = {}
    category_map: dict[str, int] = {}
    for product in products:
        status_key = product.status.value if isinstance(product.status, StockStatus) else str(product.status or "NORMAL")
        status_map[status_key] = status_map.get(status_key, 0) + 1
        category_key = (product.category or "").strip() or (product.type or "").strip() or "ไม่ระบุหมวด"
        category_map[category_key] = category_map.get(category_key, 0) + 1

    status_chart = [
        OwnerStatusSliceOut(name=name, value=value)
        for name, value in sorted(status_map.items(), key=lambda item: (-item[1], item[0]))
    ]
    category_chart = [
        OwnerStatusSliceOut(name=name, value=value)
        for name, value in sorted(category_map.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]

    start, end, buckets = _period_bounds(period)
    activity_logs = (
        await db.execute(
            select(AuditLog).where(AuditLog.created_at >= start, AuditLog.created_at < end).order_by(AuditLog.created_at.asc())
        )
    ).scalars().all()
    transactions = (
        await db.execute(
            select(StockTransaction).where(StockTransaction.created_at >= start, StockTransaction.created_at < end).order_by(StockTransaction.created_at.asc())
        )
    ).scalars().all()

    timeline: list[OwnerTimelinePointOut] = []
    for bucket_start, bucket_end, key, label in buckets:
        bucket_logs = [log for log in activity_logs if bucket_start <= log.created_at < bucket_end]
        bucket_txns = [txn for txn in transactions if bucket_start <= txn.created_at < bucket_end]
        stock_in_qty = sum(float(txn.qty or 0) for txn in bucket_txns if txn.type == TxnType.STOCK_IN)
        stock_out_qty = sum(float(txn.qty or 0) for txn in bucket_txns if txn.type == TxnType.STOCK_OUT)
        adjust_qty = sum(float(txn.qty or 0) for txn in bucket_txns if txn.type == TxnType.ADJUST)
        timeline.append(
            OwnerTimelinePointOut(
                key=key,
                label=label,
                activity_count=len(bucket_logs),
                transaction_count=len(bucket_txns),
                stock_in_qty=_d(stock_in_qty),
                stock_out_qty=_d(stock_out_qty),
                adjust_qty=_d(adjust_qty),
            )
        )

    return OwnerSummaryOut(
        period=period,
        total_products=total_products,
        stock_value=_d(stock_value),
        sales_value=_d(sales_value),
        user_total=user_total,
        active_users_online=online_count(),
        activity_total=len(activity_logs),
        transaction_total=len(transactions),
        status_chart=status_chart,
        category_chart=category_chart,
        timeline=timeline,
    )

