from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user, require_roles
from server.api.schemas import UserCreateIn, UserListOut, UserOut, UserResetPasswordIn, UserUpdateIn
from server.db.database import get_db
from server.db.models import Role, User
from server.services.audit import write_audit_log
from server.services.security import hash_password


router = APIRouter(prefix="/users", tags=["users"])


def _to_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        display_name=u.display_name,
        role=u.role,
        is_active=u.is_active,
        language=u.language,
        has_secret_key=bool(u.totp_secret),
        created_at=u.created_at,
        updated_at=u.updated_at,
    )


@router.get("", response_model=UserListOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def list_users(
    db: AsyncSession = Depends(get_db),
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(User)
    if q:
        qs = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(qs), func.lower(User.display_name).like(qs)))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    res = await db.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset))
    items = res.scalars().all()
    return UserListOut(items=[_to_out(x) for x in items], total=int(total or 0))


@router.post("", response_model=UserOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def create_user(
    payload: UserCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="invalid_username")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="password_too_short")

    existing = await db.scalar(select(User).where(User.username == username))
    if existing:
        raise HTTPException(status_code=409, detail="username_exists")

    u = User(
        username=username,
        display_name=(payload.display_name or "").strip(),
        role=payload.role,
        is_active=True,
        language=(payload.language or "th").strip() or "th",
        password_hash=hash_password(payload.password),
        totp_secret=(payload.secret_key.strip() if payload.secret_key and payload.secret_key.strip() else None),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)

    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="USER_CREATE",
        entity="user",
        entity_id=u.id,
        success=True,
        message="created",
        before=None,
        after={"username": u.username, "role": u.role.value},
    )

    return _to_out(u)


@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def update_user(
    user_id: str,
    payload: UserUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    u = await db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    before = {"role": u.role.value, "is_active": u.is_active, "language": u.language, "display_name": u.display_name}

    if payload.username is not None:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="invalid_username")
        other = await db.scalar(select(User).where(User.username == username, User.id != u.id))
        if other:
            raise HTTPException(status_code=409, detail="username_exists")
        u.username = username
    if payload.display_name is not None:
        u.display_name = payload.display_name.strip()
    if payload.role is not None:
        u.role = payload.role
    if payload.is_active is not None:
        u.is_active = bool(payload.is_active)
    if payload.language is not None:
        u.language = payload.language.strip() or u.language
    u.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(u)

    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="USER_UPDATE",
        entity="user",
        entity_id=u.id,
        success=True,
        message="updated",
        before=before,
        after={"username": u.username, "role": u.role.value, "is_active": u.is_active, "language": u.language, "display_name": u.display_name},
    )

    return _to_out(u)


@router.post("/{user_id}/reset-password", response_model=UserOut, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def reset_password(
    user_id: str,
    payload: UserResetPasswordIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="password_too_short")

    u = await db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.password_hash = hash_password(payload.password)
    u.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(u)

    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="USER_RESET_PASSWORD",
        entity="user",
        entity_id=u.id,
        success=True,
        message="reset_password",
        before=None,
        after={"username": u.username},
    )

    return _to_out(u)


@router.delete("/{user_id}", response_model=dict, dependencies=[Depends(require_roles([Role.OWNER, Role.DEV]))])
async def delete_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    u = await db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if u.id == actor.id:
        raise HTTPException(status_code=400, detail="cannot_delete_self")

    username = u.username
    await db.delete(u)
    await db.commit()

    await write_audit_log(
        db,
        request=request,
        actor=actor,
        action="USER_DELETE",
        entity="user",
        entity_id=user_id,
        success=True,
        message="deleted",
        before={"username": username},
        after=None,
    )

    return {"ok": True}

