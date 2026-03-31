from __future__ import annotations

from collections import defaultdict
from typing import Any

import socketio


sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
online_by_user: dict[str, int] = defaultdict(int)
sid_to_user: dict[str, str] = {}


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None):
    user_id = None
    if auth and isinstance(auth, dict):
        user_id = auth.get("user_id")
    if user_id:
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

