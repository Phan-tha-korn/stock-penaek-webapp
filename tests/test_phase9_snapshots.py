from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.database import Base
from server.db.models import (
    AreaScope,
    Branch,
    CanonicalGroupLockState,
    CanonicalGroupMember,
    CanonicalProductGroup,
    CostFormula,
    CostFormulaVersion,
    CurrencyCode,
    FormulaScopeType,
    FormulaStatus,
    PriceDimension,
    PriceRecord,
    PriceRecordStatus,
    PriceSourceType,
    Product,
    ReportSnapshot,
    ReportSnapshotItem,
    ReportSnapshotItemType,
    ReportSnapshotLink,
    ReportSnapshotStatus,
    ReportSnapshotType,
    Role,
    StockStatus,
    Supplier,
    User,
    VerificationAction,
    VerificationActionType,
    VerificationApprovalStrategy,
    VerificationDependencyWarning,
    VerificationRequest,
    VerificationRequestItem,
    VerificationRiskLevel,
    VerificationSafetyStatus,
    VerificationWorkflowStatus,
)
from server.services.pricing import archive_price_record
from server.services.security import hash_password
from server.services.snapshots import get_report_snapshot_by_id
import server.services.verification as verification_service
from server.services.verification import approve_verification_request, create_verification_request


REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase9MigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_snapshot_tables(self) -> None:
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = None
        try:
            config = Config(str(REPO_ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
            config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
            command.upgrade(config, "head")

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = {row[0] for row in cur.fetchall()}
            self.assertTrue(
                {
                    "report_snapshots",
                    "report_snapshot_items",
                    "report_snapshot_links",
                }.issubset(table_names)
            )
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            if os.path.exists(db_path):
                os.unlink(db_path)


class Phase9SnapshotIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        verification_service.clear_verification_handlers()
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", future=True)
        self.SessionLocal = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        asyncio.run(self._init_db())

    def tearDown(self) -> None:
        verification_service.clear_verification_handlers()
        asyncio.run(self.engine.dispose())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    async def _init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.SessionLocal() as db:
            now = datetime.utcnow()
            branch = Branch(code="MAIN", name="Main", description="Main", is_default=True, is_active=True)
            owner = User(username="owner", display_name="Owner", role=Role.OWNER, is_active=True, language="th", password_hash=hash_password("Owner@1234"), totp_secret=None)
            dev = User(username="dev", display_name="Dev", role=Role.DEV, is_active=True, language="th", password_hash=hash_password("Dev@1234"), totp_secret=None)
            admin = User(username="admin", display_name="Admin", role=Role.ADMIN, is_active=True, language="th", password_hash=hash_password("Admin@1234"), totp_secret=None)
            db.add_all([branch, owner, dev, admin])
            await db.flush()

            product = Product(
                sku="SKU-SNAP-001",
                branch_id=branch.id,
                name_th="Snap Product",
                name_en="Snap Product",
                category="Hardware",
                type="bolt",
                unit="pcs",
                cost_price=100,
                selling_price=120,
                stock_qty=10,
                min_stock=1,
                max_stock=20,
                status=StockStatus.NORMAL,
                supplier="Alpha",
                barcode="SNAP-001",
                created_by=owner.id,
            )
            supplier = Supplier(
                branch_id=branch.id,
                code="SUP-SNAP",
                name="Alpha Supplier",
                normalized_name="alpha supplier",
                is_verified=True,
                created_by=owner.id,
                updated_by=owner.id,
            )
            formula = CostFormula(
                code="FORM-SNAP",
                name="Formula Snap",
                description="Test formula",
                scope_type=FormulaScopeType.PRODUCT,
                scope_ref_id="scope-product",
                branch_id=branch.id,
                is_override=False,
                status=FormulaStatus.ACTIVE,
                created_by=owner.id,
                updated_by=owner.id,
            )
            db.add_all([product, supplier, formula])
            await db.flush()

            formula_version = CostFormulaVersion(
                formula_id=formula.id,
                version_no=1,
                expression_text="base_price + vat_amount",
                variables_json=["base_price", "vat_amount"],
                constants_json={},
                dependency_keys_json=["base_price", "vat_amount"],
                is_active_version=True,
                is_locked=True,
                activated_at=now,
                created_by=owner.id,
            )
            db.add(formula_version)
            await db.flush()
            formula.active_version_id = formula_version.id

            group = CanonicalProductGroup(
                code="GROUP-SNAP",
                display_name="Snap Group",
                system_name="snap_group",
                status="active",
                lock_state=CanonicalGroupLockState.EDITABLE,
                version_no=3,
                created_by=owner.id,
            )
            db.add(group)
            await db.flush()
            db.add(
                CanonicalGroupMember(
                    group_id=group.id,
                    product_id=product.id,
                    is_primary=True,
                    assigned_by=owner.id,
                    created_by=owner.id,
                )
            )

            price = PriceRecord(
                product_id=product.id,
                supplier_id=supplier.id,
                branch_id=branch.id,
                source_type=PriceSourceType.MANUAL_ENTRY,
                status=PriceRecordStatus.ACTIVE,
                delivery_mode="standard",
                area_scope=AreaScope.GLOBAL.value,
                price_dimension=PriceDimension.REAL_TOTAL_COST.value,
                quantity_min=1,
                quantity_max=9,
                original_currency=CurrencyCode.THB,
                original_amount=100,
                normalized_currency=CurrencyCode.THB,
                normalized_amount=100,
                exchange_rate=1,
                exchange_rate_snapshot_at=now,
                base_price=100,
                vat_percent=7,
                vat_amount=7,
                shipping_cost=5,
                fuel_cost=1,
                labor_cost=1,
                utility_cost=1,
                supplier_fee=0,
                discount=0,
                final_total_cost=115,
                formula_id=formula.id,
                formula_version_id=formula_version.id,
                effective_at=now - timedelta(hours=1),
                created_by=owner.id,
            )
            db.add(price)
            await db.flush()

            self.ids = {
                "branch": branch.id,
                "owner": owner.id,
                "dev": dev.id,
                "admin": admin.id,
                "product": product.id,
                "supplier": supplier.id,
                "formula": formula.id,
                "formula_version": formula_version.id,
                "group": group.id,
                "price": price.id,
            }
            await db.commit()

    async def _get_user(self, db: AsyncSession, user_id: str) -> User:
        user = await db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        return user

    def _verification_payload(self, *, entity_id: str | None = None, entity_type: str = "price_record", entity_version_token: str | None = None) -> dict:
        return {
            "subject_domain": "pricing",
            "queue_key": "pricing",
            "risk_score": 80,
            "risk_level": "critical",
            "safety_status": "warning",
            "change_summary": "pricing change",
            "request_reason": "approve pricing change",
            "branch_id": self.ids["branch"],
            "items": [
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "change_type": "archive",
                    "handler_key": "pricing.manual",
                    "approval_strategy": VerificationApprovalStrategy.MANUAL_FOLLOW_UP.value,
                    "risk_level": "critical",
                    "safety_status": "warning",
                    "before_json": {"status": "active"},
                    "proposed_after_json": {"status": "archived"},
                    "handler_payload_json": {},
                    "diff_summary": "archive price record",
                    "entity_version_token": entity_version_token,
                }
            ],
            "dependency_warnings": [
                {
                    "dependency_type": "pricing",
                    "dependency_entity_type": "price_record",
                    "dependency_entity_id": self.ids["price"],
                    "safety_status": "warning",
                    "message": "pricing dependency",
                    "detail_json": {"kind": "price"},
                }
            ],
        }

    def test_snapshot_creation_consistency_query_and_payload_correctness(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.ids["owner"])
                dev = await self._get_user(db, self.ids["dev"])

                request_record = await create_verification_request(
                    db,
                    actor=owner,
                    payload=self._verification_payload(entity_id=self.ids["price"]),
                )
                request_id = request_record.id
                await db.commit()

                await approve_verification_request(db, request_id=request_id, actor=dev, reason="approve pricing snapshot")
                await db.commit()

                approved_request = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert approved_request is not None
                self.assertEqual(approved_request.workflow_status, VerificationWorkflowStatus.APPROVED)

                snapshots = (
                    await db.execute(
                        select(ReportSnapshot).where(
                            ReportSnapshot.scope_type == "verification_request",
                            ReportSnapshot.scope_ref_id == request_id,
                        )
                    )
                ).scalars().all()
                self.assertEqual(len(snapshots), 1)
                snapshot = snapshots[0]

                items = (
                    await db.execute(
                        select(ReportSnapshotItem).where(ReportSnapshotItem.snapshot_id == snapshot.id)
                    )
                ).scalars().all()
                links = (
                    await db.execute(
                        select(ReportSnapshotLink).where(ReportSnapshotLink.snapshot_id == snapshot.id)
                    )
                ).scalars().all()
                self.assertGreaterEqual(len(items), 4)
                self.assertGreaterEqual(len(links), 2)

                verification_item = next(item for item in items if item.item_type == ReportSnapshotItemType.VERIFICATION_STATE)
                request_item = next(item for item in items if item.item_type == ReportSnapshotItemType.REQUEST_ITEM)
                price_item = next(item for item in items if item.item_type == ReportSnapshotItemType.PRICE_RECORD)

                self.assertEqual(verification_item.payload_json["workflow_status"], "approved")
                self.assertIn("apply_results", verification_item.payload_json)
                self.assertIn("before_json", request_item.payload_json)
                self.assertIn("proposed_after_json", request_item.payload_json)
                self.assertEqual(price_item.payload_json["normalized_currency"], "THB")
                self.assertNotIn("note", price_item.payload_json)
                self.assertIsNotNone(price_item.source_version_token)

                loaded = await get_report_snapshot_by_id(db, snapshot_id=snapshot.id)
                self.assertEqual(loaded["id"], snapshot.id)
                self.assertEqual(loaded["scope_ref_id"], request_id)
                self.assertGreaterEqual(len(loaded["items"]), 4)
                self.assertGreaterEqual(len(loaded["links"]), 2)

                filtered = await get_report_snapshot_by_id(db, snapshot_id=snapshot.id, item_types=["price_record"])
                self.assertEqual(len(filtered["items"]), 1)
                self.assertEqual(filtered["items"][0]["item_type"], "price_record")

        asyncio.run(scenario())

    def test_pricing_change_snapshot_created_with_version_binding(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.ids["owner"])
                record = await db.scalar(select(PriceRecord).where(PriceRecord.id == self.ids["price"]))
                assert record is not None

                await archive_price_record(db, record=record, actor=owner, request=None, reason="archive for snapshot")
                await db.commit()

                snapshots = (
                    await db.execute(
                        select(ReportSnapshot).where(
                            ReportSnapshot.scope_type == "price_record",
                            ReportSnapshot.scope_ref_id == self.ids["price"],
                        )
                    )
                ).scalars().all()
                self.assertEqual(len(snapshots), 1)
                snapshot = snapshots[0]

                payload = await get_report_snapshot_by_id(db, snapshot_id=snapshot.id)
                item_types = {item["item_type"] for item in payload["items"]}
                self.assertTrue({"price_record", "product_state", "supplier_state", "formula_version", "matching_group"}.issubset(item_types))
                price_item = next(item for item in payload["items"] if item["item_type"] == "price_record")
                self.assertTrue(str(price_item["source_version_token"]).startswith("price_record:"))

        asyncio.run(scenario())

    def test_snapshot_failure_rolls_back_verification_approval_without_partial_commit(self) -> None:
        async def failing_snapshot(*_: object, **__: object):
            raise HTTPException(status_code=409, detail="snapshot_generation_failed")

        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.ids["owner"])
                dev = await self._get_user(db, self.ids["dev"])
                request_record = await create_verification_request(
                    db,
                    actor=owner,
                    payload=self._verification_payload(entity_id=self.ids["price"]),
                )
                request_id = request_record.id
                await db.commit()

                with patch("server.services.verification.create_verification_approval_snapshot", new=failing_snapshot):
                    with self.assertRaises(HTTPException) as failed:
                        await approve_verification_request(db, request_id=request_id, actor=dev, reason="approve should fail")
                    self.assertEqual(failed.exception.detail, "snapshot_generation_failed")
                    await db.rollback()

            async with self.SessionLocal() as verify_db:
                request_after = await verify_db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert request_after is not None
                self.assertEqual(request_after.workflow_status, VerificationWorkflowStatus.PENDING)
                approve_actions = (
                    await verify_db.execute(
                        select(VerificationAction).where(
                            VerificationAction.request_id == request_id,
                            VerificationAction.action_type == VerificationActionType.APPROVE,
                        )
                    )
                ).scalars().all()
                self.assertEqual(len(approve_actions), 0)
                snapshots = (
                    await verify_db.execute(
                        select(ReportSnapshot).where(ReportSnapshot.scope_ref_id == request_id)
                    )
                ).scalars().all()
                self.assertEqual(len(snapshots), 0)

        asyncio.run(scenario())

    def test_missing_version_token_for_missing_versioned_source_triggers_failure(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.ids["owner"])
                dev = await self._get_user(db, self.ids["dev"])
                request_record = await create_verification_request(
                    db,
                    actor=owner,
                    payload=self._verification_payload(entity_id="missing-group", entity_type="canonical_product_group"),
                )
                request_id = request_record.id
                await db.commit()

                with self.assertRaises(HTTPException) as failed:
                    await approve_verification_request(db, request_id=request_id, actor=dev, reason="missing token")
                self.assertEqual(failed.exception.detail, "snapshot_version_token_required")
                await db.rollback()

            async with self.SessionLocal() as verify_db:
                request_after = await verify_db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert request_after is not None
                self.assertEqual(request_after.workflow_status, VerificationWorkflowStatus.PENDING)

        asyncio.run(scenario())

    def test_snapshot_immutability_and_cancelled_snapshot_query(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                cancelled = ReportSnapshot(
                    snapshot_code="CANCELLED-SNAP",
                    snapshot_type=ReportSnapshotType.AUDIT_BUNDLE,
                    scope_type="verification_request",
                    scope_ref_id="cancelled-request",
                    branch_id=self.ids["branch"],
                    as_of_at=datetime.utcnow(),
                    generation_reason="cancelled seed",
                    generated_by_user_id=self.ids["owner"],
                    source_consistency_token="cancelled-seed",
                    status=ReportSnapshotStatus.CANCELLED,
                )
                db.add(cancelled)
                await db.commit()

                loaded = await get_report_snapshot_by_id(db, snapshot_id=cancelled.id)
                self.assertEqual(loaded["status"], "cancelled")

                existing = await db.scalar(
                    select(ReportSnapshot).where(
                        ReportSnapshot.scope_type == "price_record",
                        ReportSnapshot.scope_ref_id == self.ids["price"],
                    )
                )
                if existing is None:
                    owner = await self._get_user(db, self.ids["owner"])
                    record = await db.scalar(select(PriceRecord).where(PriceRecord.id == self.ids["price"]))
                    assert record is not None
                    await archive_price_record(db, record=record, actor=owner, request=None, reason="immutability seed")
                    await db.commit()
                    existing = await db.scalar(
                        select(ReportSnapshot).where(
                            ReportSnapshot.scope_type == "price_record",
                            ReportSnapshot.scope_ref_id == self.ids["price"],
                        )
                    )
                assert existing is not None
                existing.generation_reason = "mutated"
                with self.assertRaises(ValueError) as immutable:
                    await db.commit()
                self.assertIn("report_snapshot_immutable", str(immutable.exception))
                await db.rollback()

        asyncio.run(scenario())
