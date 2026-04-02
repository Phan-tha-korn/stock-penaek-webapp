from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.api import config as config_api
from server.api import dev_sheets as dev_sheets_api
from server.api import products as products_api
from server.db.database import Base, get_db
from server.db.models import AuditLog, Product, Role, StockStatus, User
from server.main import fastapi_app
from server.services.security import hash_password


class ApiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", future=True)
        self.SessionLocal = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        asyncio.run(self._init_db())

        async def override_get_db():
            async with self.SessionLocal() as session:
                yield session

        fastapi_app.dependency_overrides[get_db] = override_get_db

        self._orig_trigger_sheet_sync = products_api._trigger_sheet_sync
        products_api._trigger_sheet_sync = lambda: None
        self._orig_dev_sheets_get_client = dev_sheets_api.get_client
        dev_sheets_api.get_client = lambda: None
        self._orig_config_get_client = config_api.get_client
        config_api.get_client = lambda: None

        self.client = TestClient(fastapi_app)

    def tearDown(self) -> None:
        self.client.close()
        products_api._trigger_sheet_sync = self._orig_trigger_sheet_sync
        dev_sheets_api.get_client = self._orig_dev_sheets_get_client
        config_api.get_client = self._orig_config_get_client
        fastapi_app.dependency_overrides.clear()
        asyncio.run(self.engine.dispose())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    async def _init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.SessionLocal() as db:
            owner = User(
                username="owner",
                display_name="Owner",
                role=Role.OWNER,
                is_active=True,
                language="th",
                password_hash=hash_password("Owner@1234"),
                totp_secret=None,
            )
            dev = User(
                username="dev",
                display_name="Dev",
                role=Role.DEV,
                is_active=True,
                language="en",
                password_hash=hash_password("Dev@1234"),
                totp_secret=None,
            )
            stock = User(
                username="stock",
                display_name="Stock",
                role=Role.STOCK,
                is_active=True,
                language="th",
                password_hash=hash_password("Stock@1234"),
                totp_secret=None,
            )
            db.add_all([owner, dev, stock])
            await db.flush()

            db.add(
                Product(
                    sku="SKU-0001",
                    name_th="Test Product",
                    name_en="Test Product",
                    category="General",
                    type="",
                    unit="pcs",
                    cost_price=10,
                    selling_price=15,
                    stock_qty=20,
                    min_stock=5,
                    max_stock=50,
                    status=StockStatus.NORMAL,
                    is_test=False,
                    supplier="",
                    barcode="",
                    image_url=None,
                    notes="",
                    created_by=owner.id,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            db.add(
                AuditLog(
                    actor_user_id=owner.id,
                    actor_username=owner.username,
                    actor_role=owner.role,
                    action="LOGIN",
                    entity="auth",
                    entity_id=owner.id,
                    success=True,
                    before_json=None,
                    after_json=None,
                    message="seed_log",
                )
            )
            await db.commit()

    def _login(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password, "secret_phrase": ""},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        return {"Authorization": f"Bearer {data['access_token']}"}

    def test_health_and_public_config(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        public_config = self.client.get("/api/config")
        self.assertEqual(public_config.status_code, 200)
        self.assertIn("app_name", public_config.json())

    def test_auth_login_me_and_invalid_password(self) -> None:
        bad_login = self.client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "wrong-password", "secret_phrase": ""},
        )
        self.assertEqual(bad_login.status_code, 401)

        headers = self._login("owner", "Owner@1234")
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "owner")

    def test_dashboard_endpoints_for_authenticated_user(self) -> None:
        headers = self._login("owner", "Owner@1234")

        kpis = self.client.get("/api/dashboard/kpis", headers=headers)
        self.assertEqual(kpis.status_code, 200)
        self.assertEqual(kpis.json()["total_products"], 1)

        summary = self.client.get("/api/dashboard/stock_summary", headers=headers)
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["normal"], 1)

        activity = self.client.get("/api/dashboard/activity", headers=headers)
        self.assertEqual(activity.status_code, 200)
        self.assertGreaterEqual(len(activity.json()["items"]), 1)

    def test_product_crud_flow(self) -> None:
        headers = self._login("owner", "Owner@1234")

        create = self.client.post(
            "/api/products",
            headers=headers,
            json={
                "sku": "SKU-NEW",
                "name_th": "New Product",
                "category": "General",
                "unit": "pcs",
                "stock_qty": 5,
                "min_stock": 1,
                "max_stock": 10,
                "cost_price": 20,
                "selling_price": 30,
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        self.assertEqual(create.json()["sku"], "SKU-NEW")

        update = self.client.put(
            "/api/products/SKU-NEW",
            headers=headers,
            json={"name_th": "Updated Product", "category": "Updated"},
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.assertEqual(update.json()["name"]["th"], "Updated Product")

        adjust = self.client.post(
            "/api/products/SKU-NEW/adjust",
            headers=headers,
            json={"qty": 2, "type": "STOCK_OUT", "reason": "smoke"},
        )
        self.assertEqual(adjust.status_code, 200, adjust.text)
        self.assertEqual(adjust.json()["stock_qty"], "3.000")

    def test_user_management_flow(self) -> None:
        headers = self._login("owner", "Owner@1234")

        create = self.client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "newuser",
                "display_name": "New User",
                "role": "ADMIN",
                "password": "NewUser@123",
                "language": "th",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        user_id = create.json()["id"]

        listing = self.client.get("/api/users", headers=headers)
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.json()["total"], 4)

        update = self.client.patch(
            f"/api/users/{user_id}",
            headers=headers,
            json={"display_name": "Updated User", "language": "en"},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["display_name"], "Updated User")

        reset = self.client.post(
            f"/api/users/{user_id}/reset-password",
            headers=headers,
            json={"password": "ResetUser@123"},
        )
        self.assertEqual(reset.status_code, 200)

        delete = self.client.delete(f"/api/users/{user_id}", headers=headers)
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.json()["ok"])

    def test_dev_and_google_read_only_endpoints(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")
        dev_headers = self._login("dev", "Dev@1234")

        google_setup = self.client.get("/api/config/google-setup", headers=owner_headers)
        self.assertEqual(google_setup.status_code, 200, google_setup.text)
        self.assertIn("configured", google_setup.json())

        notifications = self.client.get("/api/dev/notifications/config", headers=dev_headers)
        self.assertEqual(notifications.status_code, 200, notifications.text)
        self.assertIn("roles", notifications.json())

        sheets_cfg = self.client.get("/api/dev/sheets/config", headers=dev_headers)
        self.assertEqual(sheets_cfg.status_code, 200, sheets_cfg.text)
        self.assertIn("enabled", sheets_cfg.json())


if __name__ == "__main__":
    unittest.main()
