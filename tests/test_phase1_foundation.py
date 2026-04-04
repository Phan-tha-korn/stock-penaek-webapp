from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.api import products as products_api
from server.db.database import Base, get_db
from server.db.models import AuditEvent, AuditLog, Product, Role, StockStatus, StockTransaction, TxnType, User, UserBranchScope
import server.main as main_module
from server.main import fastapi_app
from server.services.attachment_policy import MAX_ZIP_SIZE_BYTES, validate_attachment_payload
from server.services.audit import write_audit_log
from server.services.branches import bootstrap_branch_foundations
from server.services.catalog_foundation import validate_product_aliases
from server.services.security import hash_password


REPO_ROOT = Path(__file__).resolve().parents[1]


class FoundationMigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_foundation_tables_and_columns(self) -> None:
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            config = Config(str(REPO_ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
            config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
            command.upgrade(config, "head")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = {row[0] for row in cur.fetchall()}
            expected_tables = {
                "branches",
                "user_branch_scopes",
                "entity_archives",
                "audit_events",
                "attachments",
                "attachment_bindings",
                "product_aliases",
                "tags",
                "product_tag_links",
                "product_specs",
                "canonical_product_groups",
                "canonical_group_members",
                "supplier_reliability_profiles",
                "products",
                "audit_logs",
                "stock_transactions",
            }
            self.assertTrue(expected_tables.issubset(table_names))

            cur.execute("PRAGMA table_info(products)")
            product_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue({"branch_id", "archived_at", "deleted_at", "delete_reason"}.issubset(product_columns))

            cur.execute("PRAGMA table_info(audit_logs)")
            audit_columns = {row[1] for row in cur.fetchall()}
            self.assertIn("branch_id", audit_columns)

            cur.execute("PRAGMA table_info(stock_transactions)")
            txn_columns = {row[1] for row in cur.fetchall()}
            self.assertIn("branch_id", txn_columns)
        finally:
            try:
                conn.close()
            except Exception:
                pass
            if os.path.exists(db_path):
                os.unlink(db_path)


class FoundationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", future=True)
        self.SessionLocal = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        asyncio.run(self._init_db())

    def tearDown(self) -> None:
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
            db.add(owner)
            await db.flush()

            db.add(
                Product(
                    sku="FOUND-001",
                    branch_id=None,
                    name_th="Foundation Product",
                    name_en="Foundation Product",
                    category="General",
                    type="General",
                    unit="pcs",
                    cost_price=10,
                    selling_price=15,
                    stock_qty=5,
                    min_stock=1,
                    max_stock=10,
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
            await db.flush()

            product = await db.scalar(select(Product).where(Product.sku == "FOUND-001"))
            assert product is not None
            db.add(
                StockTransaction(
                    type=TxnType.STOCK_IN,
                    product_id=product.id,
                    branch_id=None,
                    sku=product.sku,
                    qty=2,
                    unit_cost=10,
                    unit_price=15,
                    reason="seed",
                    created_by=owner.id,
                    created_at=datetime.utcnow(),
                )
            )
            db.add(
                AuditLog(
                    actor_user_id=owner.id,
                    actor_username=owner.username,
                    actor_role=owner.role,
                    action="SEED",
                    entity="product",
                    entity_id=product.id,
                    branch_id=None,
                    success=True,
                    before_json=None,
                    after_json=None,
                    message="seed",
                    created_at=datetime.utcnow(),
                )
            )
            await db.commit()

    def test_bootstrap_branch_foundations_backfills_existing_rows(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                result = await bootstrap_branch_foundations(db)
                self.assertEqual(result["products_backfilled"], 1)
                self.assertEqual(result["transactions_backfilled"], 1)
                self.assertEqual(result["audit_logs_backfilled"], 1)

                product = await db.scalar(select(Product).where(Product.sku == "FOUND-001"))
                self.assertIsNotNone(product)
                self.assertIsNotNone(product.branch_id)

                scopes = (await db.execute(select(UserBranchScope))).scalars().all()
                self.assertEqual(len(scopes), 1)
                self.assertTrue(scopes[0].can_view)
                self.assertTrue(scopes[0].can_edit)

        asyncio.run(_run())

    def test_write_audit_log_creates_legacy_and_v2_records(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await db.scalar(select(User).where(User.username == "owner"))
                assert owner is not None
                await write_audit_log(
                    db,
                    request=None,
                    actor=owner,
                    action="FOUNDATION_TEST",
                    entity="product",
                    entity_id="entity-1",
                    success=True,
                    message="foundation",
                    before={"name": "before"},
                    after={"name": "after"},
                )
                await db.commit()

                audit_log_count = len((await db.execute(select(AuditLog).where(AuditLog.action == "FOUNDATION_TEST"))).scalars().all())
                audit_event_count = len((await db.execute(select(AuditEvent).where(AuditEvent.action == "FOUNDATION_TEST"))).scalars().all())
                self.assertEqual(audit_log_count, 1)
                self.assertEqual(audit_event_count, 1)

        asyncio.run(_run())

    def test_foundation_validators_enforce_limits(self) -> None:
        self.assertEqual(validate_product_aliases(["AA", " aa ", "BB"]), ["AA", "BB"])
        with self.assertRaises(ValueError):
            validate_product_aliases(["a1", "a2", "a3", "a4", "a5", "a6"])

        result = validate_attachment_payload(
            entity_type="product",
            current_count=1,
            incoming_files=1,
            file_name="photo.png",
            content_type="image/png",
            size_bytes=1024,
            classification="image",
        )
        self.assertFalse(result.is_zip)

        with self.assertRaises(ValueError):
            validate_attachment_payload(
                entity_type="product",
                current_count=5,
                incoming_files=1,
                file_name="photo.png",
                content_type="image/png",
                size_bytes=1024,
                classification="image",
            )

        with self.assertRaises(ValueError):
            validate_attachment_payload(
                entity_type="supplier",
                current_count=0,
                incoming_files=1,
                file_name="bundle.zip",
                content_type="application/zip",
                size_bytes=MAX_ZIP_SIZE_BYTES + 1,
                classification="zip_archive",
            )


class FoundationApiRegressionTests(unittest.TestCase):
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
            db.add(
                User(
                    username="owner",
                    display_name="Owner",
                    role=Role.OWNER,
                    is_active=True,
                    language="th",
                    password_hash=hash_password("Owner@1234"),
                    totp_secret=None,
                )
            )
            await db.commit()

    def _login(self) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "Owner@1234", "secret_phrase": ""},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_product_delete_and_restore_populate_structured_soft_delete_fields(self) -> None:
        headers = self._login()

        created = self.client.post(
            "/api/products",
            headers=headers,
            json={
                "sku": "SOFT-001",
                "name_th": "Soft Delete Product",
                "category": "General",
                "unit": "pcs",
                "stock_qty": 3,
                "min_stock": 1,
                "max_stock": 6,
                "cost_price": 12,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)

        deleted = self.client.post(
            "/api/products/SOFT-001/delete",
            headers=headers,
            json={"reason": "phase1_test"},
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["delete_reason"], "phase1_test")
        self.assertIsNotNone(deleted.json()["deleted_at"])

        restored = self.client.post("/api/products/SOFT-001/restore", headers=headers, json={})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertIsNone(restored.json()["deleted_at"])
        self.assertIsNone(restored.json()["delete_reason"])


if __name__ == "__main__":
    unittest.main()
