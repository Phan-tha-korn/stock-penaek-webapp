from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.database import get_db


router = APIRouter(tags=["health"])
STARTED_AT = datetime.now(timezone.utc)


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    uptime_seconds = max(0, int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()))
    return {
        "status": "ok",
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": uptime_seconds,
    }

