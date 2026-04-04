from __future__ import annotations

import asyncio
import io
import os
import tempfile
import unittest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.datastructures import Headers, UploadFile

import server.main as main_module
from server.db.database import Base, get_db
from server.db.models import Attachment, AttachmentStorageDriver, Product, Role, StockStatus, Supplier, SupplierProductLink, User
from server.main import fastapi_app
from server.services.attachment_policy import MAX_ZIP_SIZE_BYTES, validate_attachment_payload
from server.services.attachments import create_attachment_for_entity, ensure_attachment_type_classifications
from server.services.branches import bootstrap_branch_foundations
from server.services.security import hash_password
from server.services.suppliers import bootstrap_supplier_foundations


class Phase2SupplierServiceTests(unittest.TestCase):
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
                    sku="SUP-BACKFILL-001",
                    name_th="Backfill Product",
                    name_en="Backfill Product",
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
                    supplier="Legacy Supplier",
                    barcode="",
                    image_url=None,
                    notes="",
                    created_by=owner.id,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            await db.commit()

    def test_bootstrap_supplier_foundations_backfills_legacy_product_supplier_links(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                await bootstrap_branch_foundations(db)
                await ensure_attachment_type_classifications(db)
                result = await bootstrap_supplier_foundations(db)
                await db.commit()

                self.assertEqual(result["linked_products"], 1)
                suppliers = (await db.execute(select(Supplier))).scalars().all()
                links = (await db.execute(select(SupplierProductLink))).scalars().all()
                self.assertEqual(len(suppliers), 1)
                self.assertEqual(len(links), 1)
                self.assertEqual(suppliers[0].name, "Legacy Supplier")

        asyncio.run(_run())

    def test_attachment_object_storage_and_zip_validation(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                await bootstrap_branch_foundations(db)
                await ensure_attachment_type_classifications(db)
                owner = await db.scalar(select(User).where(User.username == "owner"))
                supplier = Supplier(
                    branch_id=None,
                    code="SUP-OBJ-001",
                    name="Object Supplier",
                    normalized_name="object-supplier",
                    created_by=owner.id if owner else None,
                    updated_by=owner.id if owner else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(supplier)
                await db.flush()

                upload = UploadFile(
                    filename="proof.pdf",
                    file=io.BytesIO(b"pdf-content"),
                    headers=Headers({"content-type": "application/pdf"}),
                )
                attachment = await create_attachment_for_entity(
                    db,
                    actor=owner,
                    entity_type="supplier",
                    entity_id=supplier.id,
                    branch_id=None,
                    upload=upload,
                    classification="supplier_profile",
                    storage_driver=AttachmentStorageDriver.OBJECT,
                )
                await db.commit()

                stored = await db.scalar(select(Attachment).where(Attachment.id == attachment.id))
                self.assertIsNotNone(stored)
                self.assertEqual(stored.storage_driver, AttachmentStorageDriver.OBJECT)

                with self.assertRaises(ValueError):
                    validate_attachment_payload(
                        entity_type="supplier",
                        current_count=0,
                        incoming_files=1,
                        file_name="large.zip",
                        content_type="application/zip",
                        size_bytes=MAX_ZIP_SIZE_BYTES + 1,
                        classification="zip_archive",
                    )

        asyncio.run(_run())


class Phase2SupplierApiTests(unittest.TestCase):
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
            db.add_all(
                [
                    User(username="owner", display_name="Owner", role=Role.OWNER, is_active=True, language="th", password_hash=hash_password("Owner@1234"), totp_secret=None),
                    User(username="dev", display_name="Dev", role=Role.DEV, is_active=True, language="th", password_hash=hash_password("Dev@1234"), totp_secret=None),
                    User(username="admin", display_name="Admin", role=Role.ADMIN, is_active=True, language="th", password_hash=hash_password("Admin@1234"), totp_secret=None),
                    User(username="stock", display_name="Stock", role=Role.STOCK, is_active=True, language="th", password_hash=hash_password("Stock@1234"), totp_secret=None),
                ]
            )
            await db.commit()

    def _login(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password, "secret_phrase": ""},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_supplier_crud_rules_and_admin_edit_requires_dev_verification(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")
        admin_headers = self._login("admin", "Admin@1234")
        dev_headers = self._login("dev", "Dev@1234")

        created = self.client.post(
            "/api/suppliers",
            headers=owner_headers,
            json={
                "name": "Phase2 Supplier",
                "phone": "0812345678",
                "website_url": "https://example.com",
                "address": "Bangkok",
                "source_details": "seed",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        supplier_id = created.json()["id"]
        self.assertEqual(created.json()["name"], "Phase2 Supplier")
        self.assertGreaterEqual(created.json()["reliability"]["effective_score"], 0)

        pending = self.client.put(
            f"/api/suppliers/{supplier_id}",
            headers=admin_headers,
            json={"phone": "0999999999", "source_details": "admin edit"},
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()["status"], "PENDING")

        unchanged = self.client.get(f"/api/suppliers/{supplier_id}", headers=owner_headers)
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertEqual(unchanged.json()["phone"], "0812345678")

        admin_approve = self.client.post(
            f"/api/suppliers/proposals/{pending.json()['id']}/approve",
            headers=admin_headers,
            json={"review_note": "nope"},
        )
        self.assertEqual(admin_approve.status_code, 403, admin_approve.text)

        approved = self.client.post(
            f"/api/suppliers/proposals/{pending.json()['id']}/approve",
            headers=dev_headers,
            json={"review_note": "approved"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "APPROVED")

        updated = self.client.get(f"/api/suppliers/{supplier_id}", headers=owner_headers)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["phone"], "0999999999")

    def test_supplier_attachment_upload_and_permission_denied(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")
        stock_headers = self._login("stock", "Stock@1234")

        created = self.client.post("/api/suppliers", headers=owner_headers, json={"name": "Attachment Supplier"})
        self.assertEqual(created.status_code, 200, created.text)
        supplier_id = created.json()["id"]

        upload = self.client.post(
            f"/api/suppliers/{supplier_id}/attachments",
            headers=owner_headers,
            files={"file": ("profile.pdf", b"pdf-content", "application/pdf")},
            data={"classification": "supplier_profile"},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["classification"], "supplier_profile")

        listed = self.client.get(f"/api/suppliers/{supplier_id}/attachments", headers=owner_headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 1)

        denied = self.client.post(
            "/api/suppliers",
            headers=stock_headers,
            json={"name": "Stock Must Not Create"},
        )
        self.assertEqual(denied.status_code, 403, denied.text)


if __name__ == "__main__":
    unittest.main()
