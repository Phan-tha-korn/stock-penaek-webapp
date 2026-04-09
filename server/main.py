from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.api import auth, config, dashboard, dev_backup, dev_notifications, dev_reset, dev_sheets, dev_tools, health, price_records, product_categories, products, suppliers, users, zones
from server.db.database import SessionLocal
from server.db.init_db import create_all, seed_if_empty
from server.services.attachments import ensure_attachment_type_classifications
from server.middleware.https import EnforceHTTPSMiddleware
from server.realtime.socket_manager import sio
from server.services.branches import bootstrap_branch_foundations
from server.services.media_store import ensure_media_root, media_public_root
from server.services.suppliers import bootstrap_supplier_foundations

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from server.api.auth import _limiter


fastapi_app = FastAPI(title="Enterprise Stock Platform API", version="2.0.0")

fastapi_app.state.limiter = _limiter
fastapi_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

fastapi_app.add_middleware(EnforceHTTPSMiddleware)


def _cors_origins() -> list[str]:
    from server.config.settings import settings
    from server.config.config_loader import load_master_config
    origins: list[str] = []
    web_url = str(load_master_config().get("web_url") or "").strip().rstrip("/")
    if web_url:
        origins.append(web_url)
        if "://" in web_url:
            scheme, host = web_url.split("://", 1)
            if host.startswith("www."):
                origins.append(f"{scheme}://{host[4:]}")
            else:
                origins.append(f"{scheme}://www.{host}")
    if settings.env != "production":
        origins.extend(["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"])
    return list(dict.fromkeys(origins)) or ["http://localhost:5173"]


fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(health.router, prefix="/api")
fastapi_app.include_router(config.router, prefix="/api")
fastapi_app.include_router(auth.router, prefix="/api")
fastapi_app.include_router(products.router, prefix="/api")
fastapi_app.include_router(suppliers.router, prefix="/api")
fastapi_app.include_router(product_categories.router, prefix="/api")
fastapi_app.include_router(dashboard.router, prefix="/api")
fastapi_app.include_router(zones.router, prefix="/api")
fastapi_app.include_router(price_records.router, prefix="/api")
fastapi_app.include_router(users.router, prefix="/api")
fastapi_app.include_router(dev_tools.router, prefix="/api")
fastapi_app.include_router(dev_backup.router, prefix="/api")
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


from server.services.gsheets import init_sheets, start_sync_loop

@fastapi_app.on_event("startup")
async def _startup():
    await create_all()
    async with SessionLocal() as db:
        await seed_if_empty(db)
        await bootstrap_branch_foundations(db)
        await ensure_attachment_type_classifications(db)
        await bootstrap_supplier_foundations(db)
        await db.commit()
    
    # Init Google Sheets
    import asyncio
    asyncio.create_task(init_sheets())
    asyncio.create_task(start_sync_loop())


app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

