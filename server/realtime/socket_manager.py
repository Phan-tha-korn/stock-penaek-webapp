from __future__ import annotations

from collections import defaultdict
from typing import Any
import logging

import socketio

from server.services.security import decode_token

logger = logging.getLogger(__name__)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[])
online_by_user: dict[str, int] = defaultdict(int)
sid_to_user: dict[str, str] = {}


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None):
    user_id = None
    if auth and isinstance(auth, dict):
        token = auth.get("token") or auth.get("access_token") or ""
        if token:
            try:
                payload = decode_token(str(token))
                user_id = payload.get("sub") or payload.get("user_id")
            except Exception:
                logger.debug("WebSocket auth failed for sid=%s", sid)
        if not user_id:
            user_id = auth.get("user_id")
    if not user_id:
        return False
    uid = str(user_id)
    sid_to_user[sid] = uid
    online_by_user[uid] += 1


@sio.event
async def disconnect(sid: str):
    uid = sid_to_user.pop(sid, None)
    if not uid:
        return
    online_by_user[uid] = max(0, online_by_user[uid] - 1)
    if online_by_user[uid] == 0:
        online_by_user.pop(uid, None)


async def broadcast(event: str, data: Any):
    await sio.emit(event, data)


def online_count() -> int:
    return sum(online_by_user.values())

