from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.api.schemas import (
    ProductCategoryCreateIn,
    ProductCategoryListOut,
    ProductCategoryOut,
    ProductCategoryUpdateIn,
    ProductRuleSettingsIn,
    ProductRuleSettingsOut,
)
from server.config.config_loader import load_master_config, write_master_config
from server.db.database import get_db
from server.db.models import Product, ProductCategory, Role, User
from server.realtime.socket_manager import broadcast
from server.services.audit import write_audit_log


router = APIRouter(prefix="/product-categories", tags=["product-categories"])


def _to_out(category: ProductCategory) -> ProductCategoryOut:
    return ProductCategoryOut(
        id=category.id,
        name=category.name,
        description=category.description or "",
        is_deleted=bool(category.is_deleted),
        sort_order=int(category.sort_order or 0),
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _load_rule_settings() -> ProductRuleSettingsOut:
    cfg = load_master_config()
    inventory = dict(cfg.get("inventory_rules") or {})
    try:
        max_multiplier = float(inventory.get("max_multiplier") or 2)
    except Exception:
        max_multiplier = 2
    try:
        min_divisor = float(inventory.get("min_divisor") or 3)
    except Exception:
        min_divisor = 3
    if max_multiplier <= 0:
        max_multiplier = 2
    if min_divisor <= 0:
        min_divisor = 3
    return ProductRuleSettingsOut(max_multiplier=max_multiplier, min_divisor=min_divisor)


async def _broadcast_patch(stage: str, category_id: str | None = None) -> None:
    try:
        await broadcast("catalog_patch", {"stage": stage, "category_id": category_id, "ts": datetime.utcnow().isoformat()})
    except Exception:
        pass


@router.get("", response_model=ProductCategoryListOut, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def list_categories(
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ProductCategory)
    if not include_deleted:
        stmt = stmt.where(ProductCategory.is_deleted.is_(False))
    stmt = stmt.order_by(ProductCategory.sort_order.asc(), func.lower(ProductCategory.name).asc())
    rows = (await db.execute(stmt)).scalars().all()
    return ProductCategoryListOut(items=[_to_out(row) for row in rows])


@router.get("/settings", response_model=ProductRuleSettingsOut, dependencies=[Depends(require_roles([Role.STOCK, Role.ADMIN, Role.ACCOUNTANT, Role.OWNER, Role.DEV]))])
async def get_rule_settings():
    return _load_rule_settings()


@router.put("/settings", response_model=ProductRuleSettingsOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def update_rule_settings(
    payload: ProductRuleSettingsIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if payload.max_multiplier <= 0 or payload.min_divisor <= 0:
        raise HTTPException(status_code=400, detail="invalid_inventory_rules")
    cfg = load_master_config()
    cfg["inventory_rules"] = {
        "max_multiplier": float(payload.max_multiplier),
        "min_divisor": float(payload.min_divisor),
    }
    write_master_config(cfg)
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CATEGORY_RULES_UPDATE",
        entity="inventory_rules",
        entity_id=None,
        success=True,
        message="updated",
        before=None,
        after=cfg["inventory_rules"],
    )
    return _load_rule_settings()


@router.post("", response_model=ProductCategoryOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def create_category(
    payload: ProductCategoryCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="invalid_category_name")
    existing = await db.scalar(select(ProductCategory).where(func.lower(ProductCategory.name) == name.lower()))
    if existing and not existing.is_deleted:
        raise HTTPException(status_code=409, detail="category_exists")

    await _broadcast_patch("started", existing.id if existing else None)
    if existing and existing.is_deleted:
        existing.is_deleted = False
        existing.name = name
        existing.description = (payload.description or "").strip()
        existing.sort_order = int(payload.sort_order or 0)
        existing.updated_at = datetime.utcnow()
        category = existing
    else:
        category = ProductCategory(
            name=name,
            description=(payload.description or "").strip(),
            sort_order=int(payload.sort_order or 0),
            created_by=user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(category)
    await db.commit()
    await db.refresh(category)
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CATEGORY_CREATE",
        entity="product_category",
        entity_id=category.id,
        success=True,
        message="created",
        before=None,
        after={"name": category.name},
    )
    await _broadcast_patch("completed", category.id)
    return _to_out(category)


@router.patch("/{category_id}", response_model=ProductCategoryOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def update_category(
    category_id: str,
    payload: ProductCategoryUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = await db.scalar(select(ProductCategory).where(ProductCategory.id == category_id))
    if not category:
        raise HTTPException(status_code=404, detail="category_not_found")

    before = {"name": category.name, "description": category.description, "sort_order": category.sort_order}
    await _broadcast_patch("started", category.id)
    renamed = False
    if payload.name is not None:
        next_name = payload.name.strip()
        if not next_name:
            raise HTTPException(status_code=400, detail="invalid_category_name")
        other = await db.scalar(
            select(ProductCategory).where(
                and_(func.lower(ProductCategory.name) == next_name.lower(), ProductCategory.id != category.id)
            )
        )
        if other and not other.is_deleted:
            raise HTTPException(status_code=409, detail="category_exists")
        renamed = next_name != category.name
        category.name = next_name
    if payload.description is not None:
        category.description = payload.description.strip()
    if payload.sort_order is not None:
        category.sort_order = int(payload.sort_order)
    category.updated_at = datetime.utcnow()

    if renamed:
        res = await db.execute(select(Product).where(Product.category_id == category.id))
        for product in res.scalars().all():
            product.category = category.name
            product.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(category)
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CATEGORY_UPDATE",
        entity="product_category",
        entity_id=category.id,
        success=True,
        message="updated",
        before=before,
        after={"name": category.name, "description": category.description, "sort_order": category.sort_order},
    )
    await _broadcast_patch("completed", category.id)
    return _to_out(category)


@router.delete("/{category_id}", response_model=dict, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def delete_category(
    category_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = await db.scalar(select(ProductCategory).where(ProductCategory.id == category_id))
    if not category or category.is_deleted:
        raise HTTPException(status_code=404, detail="category_not_found")

    await _broadcast_patch("started", category.id)
    category.is_deleted = True
    category.updated_at = datetime.utcnow()
    products = (await db.execute(select(Product).where(Product.category_id == category.id))).scalars().all()
    for product in products:
        product.last_category_id = category.id
        product.category_id = None
        product.category = ""
        product.updated_at = datetime.utcnow()
    await db.commit()
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CATEGORY_DELETE",
        entity="product_category",
        entity_id=category.id,
        success=True,
        message="deleted",
        before={"name": category.name},
        after={"detached_products": len(products)},
    )
    await _broadcast_patch("completed", category.id)
    return {"ok": True}


@router.post("/{category_id}/restore", response_model=ProductCategoryOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def restore_category(
    category_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    category = await db.scalar(select(ProductCategory).where(ProductCategory.id == category_id))
    if not category:
        raise HTTPException(status_code=404, detail="category_not_found")

    await _broadcast_patch("started", category.id)
    category.is_deleted = False
    category.updated_at = datetime.utcnow()
    products = (
        await db.execute(
            select(Product).where(
                and_(
                    Product.category_id.is_(None),
                    Product.last_category_id == category.id,
                    or_(Product.notes.is_(None), ~Product.notes.like("__DELETED__:%")),
                )
            )
        )
    ).scalars().all()
    for product in products:
        product.category_id = category.id
        product.category = category.name
        product.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(category)
    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="CATEGORY_RESTORE",
        entity="product_category",
        entity_id=category.id,
        success=True,
        message="restored",
        before=None,
        after={"restored_products": len(products)},
    )
    await _broadcast_patch("completed", category.id)
    return _to_out(category)
