from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.api import config as config_api
from server.api import dev_sheets as dev_sheets_api
from server.api import products as products_api
from server.db.database import Base, get_db
from server.db.models import AuditLog, Product, Role, StockStatus, User
import server.main as main_module
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
        self._orig_create_all = main_module.create_all
        self._orig_seed_if_empty = main_module.seed_if_empty
        self._orig_bootstrap_branch_foundations = main_module.bootstrap_branch_foundations
        self._orig_ensure_attachment_type_classifications = main_module.ensure_attachment_type_classifications
        self._orig_bootstrap_supplier_foundations = main_module.bootstrap_supplier_foundations

        async def _noop(*_args, **_kwargs):
            return None

        main_module.create_all = _noop
        main_module.seed_if_empty = _noop
        main_module.bootstrap_branch_foundations = _noop
        main_module.ensure_attachment_type_classifications = _noop
        main_module.bootstrap_supplier_foundations = _noop

        self.client = TestClient(fastapi_app)

    def tearDown(self) -> None:
        self.client.close()
        products_api._trigger_sheet_sync = self._orig_trigger_sheet_sync
        dev_sheets_api.get_client = self._orig_dev_sheets_get_client
        config_api.get_client = self._orig_config_get_client
        main_module.create_all = self._orig_create_all
        main_module.seed_if_empty = self._orig_seed_if_empty
        main_module.bootstrap_branch_foundations = self._orig_bootstrap_branch_foundations
        main_module.ensure_attachment_type_classifications = self._orig_ensure_attachment_type_classifications
        main_module.bootstrap_supplier_foundations = self._orig_bootstrap_supplier_foundations
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
            admin = User(
                username="admin",
                display_name="Admin",
                role=Role.ADMIN,
                is_active=True,
                language="th",
                password_hash=hash_password("Admin@1234"),
                totp_secret=None,
            )
            accountant = User(
                username="accountant",
                display_name="Accountant",
                role=Role.ACCOUNTANT,
                is_active=True,
                language="th",
                password_hash=hash_password("Acc@1234"),
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
            db.add_all([owner, dev, admin, accountant, stock])
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
        data = self._login_tokens(username, password)
        return {"Authorization": f"Bearer {data['access_token']}"}

    def _login_tokens(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password, "secret_phrase": ""},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_health_and_public_config(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        public_config = self.client.get("/api/config")
        self.assertEqual(public_config.status_code, 200)
        self.assertIn("app_name", public_config.json())

    def test_prepare_import_tab_uses_lightweight_snapshot(self) -> None:
        headers = self._login("owner", "Owner@1234")
        with (
            patch(
                "server.api.dev_sheets.create_sheet_operation_snapshot",
                new=AsyncMock(return_value={"id": "snap-1", "created_at": "2026-04-09T10:00:00Z", "backup_file_name": ""}),
            ) as snapshot_mock,
            patch("server.api.dev_sheets.sync_product_import_template_to_sheet", new=AsyncMock(return_value=True)) as sync_mock,
        ):
            response = self.client.post("/api/dev/sheets/prepare-import-tab", headers=headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])
        self.assertIsNone(response.json()["snapshot_backup_file_name"])
        snapshot_mock.assert_awaited_once_with(
            "prepare-import-tab",
            note="before refresh import tab",
            include_backup=False,
            tab_titles=[dev_sheets_api.TAB_PRODUCT_IMPORT],
        )
        sync_mock.assert_awaited_once_with(fail_if_busy=True)

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

    def test_category_lifecycle_and_bulk_create_flow(self) -> None:
        headers = self._login("owner", "Owner@1234")

        create_category = self.client.post(
            "/api/product-categories",
            headers=headers,
            json={"name": "อาหาร", "description": "โซนอาหาร", "sort_order": 10},
        )
        self.assertEqual(create_category.status_code, 200, create_category.text)
        category_id = create_category.json()["id"]

        settings_update = self.client.put(
            "/api/product-categories/settings",
            headers=headers,
            json={"max_multiplier": 4, "min_divisor": 2},
        )
        self.assertEqual(settings_update.status_code, 200, settings_update.text)
        self.assertEqual(settings_update.json()["max_multiplier"], 4)

        bulk_create = self.client.post(
            "/api/products/bulk-create",
            headers=headers,
            json={
                "items": [
                    {
                        "sku": "BULK-001",
                        "name_th": "ข้าวสาร",
                        "category_id": category_id,
                        "type": "วัตถุดิบ",
                        "unit": "ชิ้น",
                        "stock_qty": 9,
                        "min_stock": 3,
                        "max_stock": 18,
                    },
                    {
                        "sku": "BULK-002",
                        "name_th": "น้ำปลา",
                        "category_id": category_id,
                        "type": "เครื่องปรุง",
                        "unit": "กก.",
                        "stock_qty": 2.5,
                        "min_stock": 1,
                        "max_stock": 5,
                    },
                ]
            },
        )
        self.assertEqual(bulk_create.status_code, 200, bulk_create.text)
        self.assertEqual(bulk_create.json()["total"], 2)

        filtered = self.client.get(f"/api/products?category_id={category_id}", headers=headers)
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()["total"], 2)

        delete_category = self.client.delete(f"/api/product-categories/{category_id}", headers=headers)
        self.assertEqual(delete_category.status_code, 200, delete_category.text)

        uncategorized = self.client.get("/api/products?uncategorized_only=true", headers=headers)
        self.assertEqual(uncategorized.status_code, 200, uncategorized.text)
        returned_skus = {item["sku"] for item in uncategorized.json()["items"]}
        self.assertIn("BULK-001", returned_skus)
        self.assertIn("BULK-002", returned_skus)

        restore_category = self.client.post(f"/api/product-categories/{category_id}/restore", headers=headers)
        self.assertEqual(restore_category.status_code, 200, restore_category.text)

        filtered_again = self.client.get(f"/api/products?category_id={category_id}", headers=headers)
        self.assertEqual(filtered_again.status_code, 200, filtered_again.text)
        self.assertEqual(filtered_again.json()["total"], 2)

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

    def test_new_user_can_login_and_deleted_user_is_blocked_immediately(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")

        create = self.client.post(
            "/api/users",
            headers=owner_headers,
            json={
                "username": "freshuser",
                "display_name": "Fresh User",
                "role": "STOCK",
                "password": "FreshUser@123",
                "language": "th",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        user_id = create.json()["id"]

        fresh_tokens = self._login_tokens("freshuser", "FreshUser@123")
        me_before_delete = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh_tokens['access_token']}"})
        self.assertEqual(me_before_delete.status_code, 200, me_before_delete.text)

        delete = self.client.delete(f"/api/users/{user_id}", headers=owner_headers)
        self.assertEqual(delete.status_code, 200, delete.text)

        relogin = self.client.post(
            "/api/auth/login",
            json={"username": "freshuser", "password": "FreshUser@123", "secret_phrase": ""},
        )
        self.assertEqual(relogin.status_code, 401, relogin.text)

        me_after_delete = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh_tokens['access_token']}"})
        self.assertEqual(me_after_delete.status_code, 401, me_after_delete.text)

        refresh_after_delete = self.client.post("/api/auth/refresh", json={"refresh_token": fresh_tokens["refresh_token"]})
        self.assertEqual(refresh_after_delete.status_code, 401, refresh_after_delete.text)

    def test_invalid_totp_secret_is_rejected_and_reset_password_revokes_sessions(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")

        invalid_secret = self.client.post(
            "/api/users",
            headers=owner_headers,
            json={
                "username": "badtotp",
                "display_name": "Bad Totp",
                "role": "STOCK",
                "password": "BadTotp@123",
                "secret_key": "123456",
                "language": "th",
            },
        )
        self.assertEqual(invalid_secret.status_code, 400, invalid_secret.text)
        self.assertEqual(invalid_secret.json()["detail"], "invalid_totp_secret")

        create = self.client.post(
            "/api/users",
            headers=owner_headers,
            json={
                "username": "resetme",
                "display_name": "Reset Me",
                "role": "ADMIN",
                "password": "ResetMe@123",
                "language": "th",
            },
        )
        self.assertEqual(create.status_code, 200, create.text)
        user_id = create.json()["id"]

        tokens = self._login_tokens("resetme", "ResetMe@123")

        reset = self.client.post(
            f"/api/users/{user_id}/reset-password",
            headers=owner_headers,
            json={"password": "ResetMe@456"},
        )
        self.assertEqual(reset.status_code, 200, reset.text)

        refresh_old = self.client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        self.assertEqual(refresh_old.status_code, 401, refresh_old.text)

        login_old_password = self.client.post(
            "/api/auth/login",
            json={"username": "resetme", "password": "ResetMe@123", "secret_phrase": ""},
        )
        self.assertEqual(login_old_password.status_code, 401, login_old_password.text)

        login_new_password = self.client.post(
            "/api/auth/login",
            json={"username": "resetme", "password": "ResetMe@456", "secret_phrase": ""},
        )
        self.assertEqual(login_new_password.status_code, 200, login_new_password.text)

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

    def test_role_access_matrix(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")
        dev_headers = self._login("dev", "Dev@1234")
        admin_headers = self._login("admin", "Admin@1234")
        accountant_headers = self._login("accountant", "Acc@1234")
        stock_headers = self._login("stock", "Stock@1234")

        owner_users = self.client.get("/api/users?limit=5", headers=owner_headers)
        self.assertEqual(owner_users.status_code, 200, owner_users.text)

        dev_garbage = self.client.get("/api/dev/garbage/scan", headers=dev_headers)
        self.assertEqual(dev_garbage.status_code, 200, dev_garbage.text)

        admin_products = self.client.get("/api/products?limit=5", headers=admin_headers)
        self.assertEqual(admin_products.status_code, 200, admin_products.text)
        admin_google_setup = self.client.get("/api/config/google-setup", headers=admin_headers)
        self.assertEqual(admin_google_setup.status_code, 403, admin_google_setup.text)

        accountant_transactions = self.client.get("/api/dashboard/transactions?limit=5", headers=accountant_headers)
        self.assertEqual(accountant_transactions.status_code, 200, accountant_transactions.text)
        accountant_products = self.client.get("/api/products?limit=5", headers=accountant_headers)
        self.assertEqual(accountant_products.status_code, 403, accountant_products.text)

        stock_products = self.client.get("/api/products?limit=5", headers=stock_headers)
        self.assertEqual(stock_products.status_code, 200, stock_products.text)
        stock_dev_sheets = self.client.get("/api/dev/sheets/config", headers=stock_headers)
        self.assertEqual(stock_dev_sheets.status_code, 403, stock_dev_sheets.text)

    def test_accountant_can_post_in_out_but_not_adjust_absolute(self) -> None:
        accountant_headers = self._login("accountant", "Acc@1234")

        stock_in = self.client.post(
            "/api/products/SKU-0001/adjust",
            headers=accountant_headers,
            json={"qty": 3, "type": "STOCK_IN", "reason": "accountant_in"},
        )
        self.assertEqual(stock_in.status_code, 200, stock_in.text)
        self.assertEqual(stock_in.json()["stock_qty"], "23.000")

        stock_out = self.client.post(
            "/api/products/SKU-0001/adjust",
            headers=accountant_headers,
            json={"qty": 5, "type": "STOCK_OUT", "reason": "accountant_out"},
        )
        self.assertEqual(stock_out.status_code, 200, stock_out.text)
        self.assertEqual(stock_out.json()["stock_qty"], "18.000")

        adjust_absolute = self.client.post(
            "/api/products/SKU-0001/adjust",
            headers=accountant_headers,
            json={"qty": 99, "type": "ADJUST", "reason": "accountant_adjust"},
        )
        self.assertEqual(adjust_absolute.status_code, 403, adjust_absolute.text)

    def test_stock_role_read_surface_and_forbidden_mutations(self) -> None:
        stock_headers = self._login("stock", "Stock@1234")

        products = self.client.get("/api/products?limit=10", headers=stock_headers)
        self.assertEqual(products.status_code, 200, products.text)
        self.assertGreaterEqual(products.json()["total"], 1)

        dashboard = self.client.get("/api/dashboard/kpis", headers=stock_headers)
        self.assertEqual(dashboard.status_code, 200, dashboard.text)

        create_product = self.client.post(
            "/api/products",
            headers=stock_headers,
            json={
                "sku": "STOCK-CREATE-001",
                "name_th": "Stock Should Not Create",
                "category": "General",
                "unit": "pcs",
            },
        )
        self.assertEqual(create_product.status_code, 403, create_product.text)

        create_user = self.client.post(
            "/api/users",
            headers=stock_headers,
            json={
                "username": "blocked",
                "display_name": "Blocked",
                "role": "STOCK",
                "password": "Blocked@123",
            },
        )
        self.assertEqual(create_user.status_code, 403, create_user.text)


if __name__ == "__main__":
    unittest.main()
