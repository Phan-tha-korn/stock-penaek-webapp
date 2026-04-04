from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.models import AuditLog, Branch, Product, Role, StockTransaction, User, UserBranchScope


DEFAULT_BRANCH_CODE = "MAIN"
DEFAULT_BRANCH_NAME = "Main Branch"


def _can_edit_for_role(role: Role) -> bool:
    return role in {Role.OWNER, Role.DEV, Role.ADMIN, Role.ACCOUNTANT}


async def get_default_branch(db: AsyncSession) -> Branch | None:
    result = await db.execute(select(Branch).where(Branch.is_default.is_(True)).limit(1))
    branch = result.scalar_one_or_none()
    if branch:
        return branch
    result = await db.execute(select(Branch).where(Branch.code == DEFAULT_BRANCH_CODE).limit(1))
    return result.scalar_one_or_none()


async def ensure_default_branch(db: AsyncSession) -> Branch:
    branch = await get_default_branch(db)
    if branch:
        if not branch.is_default:
            branch.is_default = True
            branch.updated_at = datetime.utcnow()
        return branch

    branch = Branch(
        code=DEFAULT_BRANCH_CODE,
        name=DEFAULT_BRANCH_NAME,
        description="System default branch for legacy stock data",
        is_default=True,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(branch)
    await db.flush()
    return branch


async def ensure_user_branch_scopes(db: AsyncSession, branch: Branch) -> int:
    users = (await db.execute(select(User))).scalars().all()
    existing_pairs = {
        (scope.user_id, scope.branch_id)
        for scope in (await db.execute(select(UserBranchScope))).scalars().all()
    }
    created = 0
    for user in users:
        key = (user.id, branch.id)
        if key in existing_pairs:
            continue
        db.add(
            UserBranchScope(
                user_id=user.id,
                branch_id=branch.id,
                can_view=True,
                can_edit=_can_edit_for_role(user.role),
                scope_source="bootstrap",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        created += 1
    if created:
        await db.flush()
    return created


async def backfill_branch_references(db: AsyncSession, branch: Branch) -> dict[str, int]:
    products = (await db.execute(select(Product).where(Product.branch_id.is_(None)))).scalars().all()
    transactions = (await db.execute(select(StockTransaction).where(StockTransaction.branch_id.is_(None)))).scalars().all()
    audit_logs = (await db.execute(select(AuditLog).where(AuditLog.branch_id.is_(None)))).scalars().all()

    for product in products:
        product.branch_id = branch.id
        product.updated_at = datetime.utcnow()

    for txn in transactions:
        txn.branch_id = branch.id

    for log in audit_logs:
        log.branch_id = branch.id

    if products or transactions or audit_logs:
        await db.flush()

    return {
        "products": len(products),
        "transactions": len(transactions),
        "audit_logs": len(audit_logs),
    }


async def bootstrap_branch_foundations(db: AsyncSession) -> dict[str, int | str]:
    branch = await ensure_default_branch(db)
    backfilled = await backfill_branch_references(db, branch)
    scopes_created = await ensure_user_branch_scopes(db, branch)
    await db.commit()
    return {
        "branch_id": branch.id,
        "products_backfilled": backfilled["products"],
        "transactions_backfilled": backfilled["transactions"],
        "audit_logs_backfilled": backfilled["audit_logs"],
        "user_scopes_created": scopes_created,
    }


async def resolve_visible_branch_ids(db: AsyncSession, user: User) -> list[str]:
    if user.role in {Role.OWNER, Role.DEV}:
        return [branch.id for branch in (await db.execute(select(Branch).where(Branch.is_active.is_(True)))).scalars().all()]

    scopes = (
        await db.execute(
            select(UserBranchScope).where(
                UserBranchScope.user_id == user.id,
                UserBranchScope.can_view.is_(True),
            )
        )
    ).scalars().all()
    if scopes:
        return [scope.branch_id for scope in scopes]

    branch = await ensure_default_branch(db)
    await db.commit()
    return [branch.id]
