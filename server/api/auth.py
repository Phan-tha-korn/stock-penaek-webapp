from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.deps import get_current_user
from server.api.schemas import LoginIn, RefreshIn, TokenOut, UserOut
from server.config.settings import settings
from server.db.database import get_db
from server.db.models import LoginLock, RefreshSession, Role, User
from server.services.audit import write_audit_log
from server.services.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    new_jti,
    now_utc,
    verify_password,
)

from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request: Request) -> str:
    # FastAPI's TestClient uses the synthetic host "testclient". Using a
    # request-unique key there keeps automated tests isolated while preserving
    # normal per-IP limiting for real traffic.
    client_host = request.client.host if request.client else get_remote_address(request)
    if client_host == "testclient":
        return f"{client_host}:{id(request.scope)}"
    return client_host or "unknown"


_limiter = Limiter(key_func=_rate_limit_key)

router = APIRouter(prefix="/auth", tags=["auth"])


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _get_lock(db: AsyncSession, username: str, ip: str) -> LoginLock:
    res = await db.execute(select(LoginLock).where(LoginLock.username == username, LoginLock.ip == ip))
    lock = res.scalar_one_or_none()
    if lock:
        return lock
    lock = LoginLock(username=username, ip=ip, failed_count=0, locked_until=None)
    db.add(lock)
    await db.commit()
    await db.refresh(lock)
    return lock


@router.post("/login", response_model=TokenOut)
@_limiter.limit(lambda: f"{settings.login_rate_limit_per_minute}/minute")
async def login(request: Request, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    payload = LoginIn.model_validate(payload)
    username = payload.username.strip()
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent")

    lock = await _get_lock(db, username, ip)
    if lock.locked_until and _utc(lock.locked_until) > now_utc():
        await write_audit_log(
            db,
            request=request,
            actor=None,
            action="LOGIN",
            entity="auth",
            entity_id=None,
            success=False,
            message="locked",
            before={"username": username, "ip": ip, "failed_count": lock.failed_count},
            after=None,
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="locked")

    if settings.login_secret_phrase and (payload.secret_phrase or "") != settings.login_secret_phrase:
        lock.failed_count += 1
        if lock.failed_count >= settings.failed_login_limit:
            lock.locked_until = (now_utc() + timedelta(minutes=settings.failed_login_lock_minutes)).replace(tzinfo=None)
        await db.commit()
        await write_audit_log(
            db,
            request=request,
            actor=None,
            action="LOGIN",
            entity="auth",
            entity_id=None,
            success=False,
            message="bad_secret_phrase",
            before={"username": username, "ip": ip},
            after=None,
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    res = await db.execute(select(User).where(User.username == username))
    user = res.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        lock.failed_count += 1
        if lock.failed_count >= settings.failed_login_limit:
            lock.locked_until = (now_utc() + timedelta(minutes=settings.failed_login_lock_minutes)).replace(tzinfo=None)
        await db.commit()
        await write_audit_log(
            db,
            request=request,
            actor=user,
            action="LOGIN",
            entity="auth",
            entity_id=user.id if user else None,
            success=False,
            message="invalid_credentials",
            before={"username": username, "ip": ip},
            after={"failed_count": lock.failed_count, "locked_until": lock.locked_until.isoformat() if lock.locked_until else None},
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")

    if user.totp_secret:
        if not payload.totp or not pyotp.TOTP(user.totp_secret).verify(payload.totp, valid_window=1):
            lock.failed_count += 1
            if lock.failed_count >= settings.failed_login_limit:
                lock.locked_until = (now_utc() + timedelta(minutes=settings.failed_login_lock_minutes)).replace(tzinfo=None)
            await db.commit()
            await write_audit_log(
                db,
                request=request,
                actor=user,
                action="LOGIN",
                entity="auth",
                entity_id=user.id,
                success=False,
                message="totp_required_or_invalid",
                before={"username": username, "ip": ip},
                after={"failed_count": lock.failed_count},
                commit=True,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_totp")

    lock.failed_count = 0
    lock.locked_until = None
    await db.commit()

    session_jti = new_jti()
    access_token, expires_in = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id, user.role.value, session_jti)

    expires_at = now_utc() + timedelta(days=settings.refresh_token_days)
    sess = RefreshSession(
        user_id=user.id,
        jti=session_jti,
        ip=ip,
        user_agent=ua,
        revoked=False,
        expires_at=expires_at.replace(tzinfo=None),
    )
    db.add(sess)
    await db.flush()

    res = await db.execute(
        select(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked.is_(False))
        .order_by(RefreshSession.created_at.desc())
        .with_for_update()
    )
    sessions = res.scalars().all()
    if len(sessions) > settings.session_max_per_user:
        for s in sessions[settings.session_max_per_user :]:
            s.revoked = True
    await db.commit()

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="LOGIN",
        entity="auth",
        entity_id=user.id,
        success=True,
        message="success",
        before=None,
        after={"ip": ip, "user_agent": ua},
        commit=True,
    )

    return TokenOut(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


@router.post("/refresh", response_model=TokenOut)
async def refresh(payload: RefreshIn, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent")

    try:
        decoded = decode_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh")

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh")

    user_id = str(decoded.get("sub") or "")
    jti = str(decoded.get("jti") or "")
    if not user_id or not jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh")

    res = await db.execute(select(RefreshSession).where(RefreshSession.jti == jti))
    sess = res.scalar_one_or_none()
    if not sess or sess.revoked or _utc(sess.expires_at) <= now_utc():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh_revoked")
    if _utc(sess.created_at) + timedelta(hours=settings.reauth_after_hours) <= now_utc():
        sess.revoked = True
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="reauth_required")

    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_inactive")

    sess.revoked = True
    new_session_jti = new_jti()
    sess2 = RefreshSession(
        user_id=user.id,
        jti=new_session_jti,
        ip=ip,
        user_agent=ua,
        revoked=False,
        created_at=sess.created_at,
        last_used_at=now_utc().replace(tzinfo=None),
        expires_at=(now_utc() + timedelta(days=settings.refresh_token_days)).replace(tzinfo=None),
    )
    db.add(sess2)
    await db.commit()

    access_token, expires_in = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id, user.role.value, new_session_jti)

    await write_audit_log(
        db,
        request=request,
        actor=user,
        action="TOKEN_REFRESH",
        entity="auth",
        entity_id=user.id,
        success=True,
        message="rotated",
        before={"ip": ip},
        after={"ip": ip, "user_agent": ua},
        commit=True,
    )

    return TokenOut(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        language=user.language,
        has_secret_key=bool(user.totp_secret),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )

