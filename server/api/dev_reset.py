from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.db.database import get_db
from server.db.models import Product, Role, StockAlertState, StockTransaction, User
from server.services.audit import write_audit_log
from server.services.dev_permanent_delete import ALL_SCOPES, SAFE_SCOPES, execute_permanent_delete
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


class PermanentDeleteIn(BaseModel):
    password: str
    delete_all: bool = False
    scopes: list[str] = Field(default_factory=list)
    product_refs: list[str] = Field(default_factory=list)
    supplier_refs: list[str] = Field(default_factory=list)
    category_refs: list[str] = Field(default_factory=list)
    price_record_refs: list[str] = Field(default_factory=list)
    verification_refs: list[str] = Field(default_factory=list)
    attachment_refs: list[str] = Field(default_factory=list)


class PermanentDeleteOut(BaseModel):
    executed_scopes: list[str]
    deleted_counts: dict[str, int]
    filesystem_deleted: dict[str, int]
    unmatched_refs: dict[str, list[str]]
    warnings: list[str]
    session_invalidated: bool


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
        commit=True,
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


@router.post("/permanent-delete", response_model=PermanentDeleteOut, dependencies=[Depends(require_roles([Role.DEV]))])
async def permanent_delete(
    request: Request,
    payload: PermanentDeleteIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if (payload.password or "").strip() != "phanthakorn":
        raise HTTPException(status_code=403, detail="invalid_dev_password")

    has_scope = bool(payload.delete_all or payload.scopes)
    has_item_refs = any(
        [
            payload.product_refs,
            payload.supplier_refs,
            payload.category_refs,
            payload.price_record_refs,
            payload.verification_refs,
            payload.attachment_refs,
        ]
    )
    if not has_scope and not has_item_refs:
        raise HTTPException(status_code=400, detail="permanent_delete_requires_scope_or_refs")

    invalid_scopes = [scope for scope in payload.scopes if scope not in ALL_SCOPES]
    if invalid_scopes:
        raise HTTPException(status_code=400, detail=f"invalid_scopes:{','.join(invalid_scopes)}")

    try:
        result = await execute_permanent_delete(
            db,
            scopes=payload.scopes,
            delete_all=payload.delete_all,
            product_refs=payload.product_refs,
            supplier_refs=payload.supplier_refs,
            category_refs=payload.category_refs,
            price_record_refs=payload.price_record_refs,
            verification_refs=payload.verification_refs,
            attachment_refs=payload.attachment_refs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not payload.delete_all and "logs" not in payload.scopes:
        await write_audit_log(
            db,
            request=request,
            actor=None,
            action="DEV_PERMANENT_DELETE",
            entity="dev_tools",
            entity_id=None,
            success=True,
            message="dev_permanent_delete_completed",
            before={
                "delete_all": payload.delete_all,
                "requested_scopes": payload.scopes,
            },
            after=result,
            metadata={
                "actor_username": actor.username,
                "actor_role": actor.role.value,
                "safe_scopes": list(SAFE_SCOPES),
            },
            commit=True,
        )

    if not payload.delete_all:
        try:
            schedule_sheet_sync()
        except Exception:
            pass

    return PermanentDeleteOut(**result)
