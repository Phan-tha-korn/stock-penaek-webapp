from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.api import auth, config, dashboard, dev_notifications, dev_reset, dev_sheets, dev_tools, health, products, users
from server.db.database import SessionLocal
from server.db.init_db import create_all, seed_if_empty
from server.middleware.https import EnforceHTTPSMiddleware
from server.realtime.socket_manager import sio
from server.services.media_store import ensure_media_root, media_public_root


fastapi_app = FastAPI(title="Enterprise Stock Platform API", version="2.0.0")

fastapi_app.add_middleware(EnforceHTTPSMiddleware)
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(health.router, prefix="/api")
fastapi_app.include_router(config.router, prefix="/api")
fastapi_app.include_router(auth.router, prefix="/api")
fastapi_app.include_router(products.router, prefix="/api")
fastapi_app.include_router(dashboard.router, prefix="/api")
fastapi_app.include_router(users.router, prefix="/api")
fastapi_app.include_router(dev_tools.router, prefix="/api")
fastapi_app.include_router(dev_notifications.router, prefix="/api")
fastapi_app.include_router(dev_sheets.router, prefix="/api")
fastapi_app.include_router(dev_reset.router, prefix="/api")

ensure_media_root()
media_dir = media_public_root()
if media_dir.exists():
    fastapi_app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

dist_dir = Path(__file__).resolve().parents[1] / "dist"
if dist_dir.exists():
    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                response = await super().get_response(path, scope)
            except StarletteHTTPException as e:
                if e.status_code == 404 and not Path(path).suffix:
                    return await super().get_response("index.html", scope)
                raise
            if response.status_code == 404 and not Path(path).suffix:
                return await super().get_response("index.html", scope)
            return response

    fastapi_app.mount("/", SPAStaticFiles(directory=str(dist_dir), html=True), name="frontend")


from server.services.gsheets import init_sheets, start_import_loop, start_sync_loop

@fastapi_app.on_event("startup")
async def _startup():
    await create_all()
    async with SessionLocal() as db:
        await seed_if_empty(db)
    
    # Init Google Sheets
    import asyncio
    asyncio.create_task(init_sheets())
    asyncio.create_task(start_sync_loop())
    asyncio.create_task(start_import_loop())


app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

