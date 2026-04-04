from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.database import Base
from server.db.models import (
    Branch,
    CatalogSearchDocument,
    PriceRecord,
    PriceRecordStatus,
    PriceSearchProjection,
    Product,
    ProductAlias,
    ProductTagLink,
    Role,
    StockStatus,
    Supplier,
    SupplierProductLink,
    Tag,
    User,
    VerificationQueueProjection,
    VerificationRiskLevel,
    VerificationWorkflowStatus,
)
from server.services.matching import add_product_to_group, create_canonical_group, move_product_between_groups
from server.services.pricing import create_price_record, replace_price_record
from server.services.search import (
    compare_prices,
    quick_search_catalog,
    search_price_history,
    search_verification_queue,
    sync_catalog_search_documents_for_products,
    sync_search_projections_for_supplier,
)
from server.services.security import hash_password
from server.services.suppliers import apply_supplier_payload
from server.services.verification import (
    assign_verification_request,
    create_verification_request,
    mark_verification_request_overdue,
    reject_verification_request,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase6MigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_search_projection_tables(self) -> None:
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
                    "catalog_search_documents",
                    "price_search_projections",
                    "verification_queue_projections",
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


class Phase6SearchIntegrationTests(unittest.TestCase):
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
            branch = Branch(code="MAIN", name="Main Branch", description="Main", is_default=True, is_active=True)
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
                language="th",
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
            db.add_all([branch, owner, dev, admin])
            await db.flush()

            self.branch_id = branch.id
            self.owner_id = owner.id
            self.dev_id = dev.id
            self.admin_id = admin.id

            product_1 = Product(
                sku="SKU-100",
                branch_id=branch.id,
                name_th="Bolt M8 Zinc",
                name_en="Bolt M8 Zinc",
                category="Hardware",
                type="bolt",
                unit="pcs",
                cost_price=0,
                selling_price=None,
                stock_qty=0,
                min_stock=0,
                max_stock=0,
                status=StockStatus.NORMAL,
                supplier="Alpha Supply",
                barcode="BOLT-100",
                created_by=dev.id,
            )
            product_2 = Product(
                sku="SKU-200",
                branch_id=branch.id,
                name_th="Bolt M8 Stainless",
                name_en="Bolt M8 Stainless",
                category="Hardware",
                type="bolt",
                unit="pcs",
                cost_price=0,
                selling_price=None,
                stock_qty=0,
                min_stock=0,
                max_stock=0,
                status=StockStatus.NORMAL,
                supplier="Bravo Metals",
                barcode="BOLT-200",
                created_by=dev.id,
            )
            product_3 = Product(
                sku="SKU-300",
                branch_id=branch.id,
                name_th="Nut M8",
                name_en="Nut M8",
                category="Hardware",
                type="nut",
                unit="pcs",
                cost_price=0,
                selling_price=None,
                stock_qty=0,
                min_stock=0,
                max_stock=0,
                status=StockStatus.NORMAL,
                supplier="Charlie Parts",
                barcode="NUT-300",
                created_by=dev.id,
            )
            db.add_all([product_1, product_2, product_3])
            await db.flush()

            self.product_1_id = product_1.id
            self.product_2_id = product_2.id
            self.product_3_id = product_3.id

            db.add(ProductAlias(product_id=product_1.id, alias="Hex Bolt", normalized_alias="hex bolt", sort_order=1, created_by=dev.id))
            tag = Tag(name="fastener", normalized_name="fastener", created_by=dev.id)
            db.add(tag)
            await db.flush()
            db.add_all(
                [
                    ProductTagLink(product_id=product_1.id, tag_id=tag.id, created_by=dev.id),
                    ProductTagLink(product_id=product_2.id, tag_id=tag.id, created_by=dev.id),
                ]
            )

            supplier_1 = Supplier(
                branch_id=branch.id,
                code="SUP-ALPHA",
                name="Alpha Supply",
                normalized_name="alpha supply",
                is_verified=True,
                created_by=dev.id,
                updated_by=dev.id,
            )
            supplier_2 = Supplier(
                branch_id=branch.id,
                code="SUP-BRAVO",
                name="Bravo Metals",
                normalized_name="bravo metals",
                is_verified=False,
                created_by=dev.id,
                updated_by=dev.id,
            )
            db.add_all([supplier_1, supplier_2])
            await db.flush()
            self.supplier_1_id = supplier_1.id
            self.supplier_2_id = supplier_2.id

            db.add_all(
                [
                    SupplierProductLink(supplier_id=supplier_1.id, product_id=product_1.id, legacy_supplier_name="Alpha Supply", is_primary=True, linked_by_user_id=dev.id),
                    SupplierProductLink(supplier_id=supplier_2.id, product_id=product_1.id, legacy_supplier_name="Bravo Metals", is_primary=False, linked_by_user_id=dev.id),
                    SupplierProductLink(supplier_id=supplier_2.id, product_id=product_2.id, legacy_supplier_name="Bravo Metals", is_primary=True, linked_by_user_id=dev.id),
                ]
            )
            await db.flush()
            await sync_catalog_search_documents_for_products(db, product_ids=[product_1.id, product_2.id, product_3.id])
            await db.commit()

    async def _get_user(self, db: AsyncSession, user_id: str) -> User:
        user = await db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        return user

    async def _get_supplier(self, db: AsyncSession, supplier_id: str) -> Supplier:
        supplier = await db.scalar(select(Supplier).where(Supplier.id == supplier_id))
        assert supplier is not None
        return supplier

    async def _create_price(
        self,
        db: AsyncSession,
        *,
        actor: User,
        product_id: str,
        supplier_id: str,
        original_currency: str = "THB",
        original_amount: str = "100",
        exchange_rate: str = "1",
        status: str = "active",
        quantity_min: int = 1,
        quantity_max: int | None = 9,
        effective_at: datetime | None = None,
        expire_at: datetime | None = None,
        delivery_mode: str = "standard",
        area_scope: str = "global",
        final_inputs: dict | None = None,
    ) -> PriceRecord:
        payload = {
            "product_id": product_id,
            "supplier_id": supplier_id,
            "branch_id": self.branch_id,
            "source_type": "manual_entry",
            "status": status,
            "delivery_mode": delivery_mode,
            "area_scope": area_scope,
            "price_dimension": "real_total_cost",
            "quantity_min": quantity_min,
            "quantity_max": quantity_max,
            "original_currency": original_currency,
            "original_amount": original_amount,
            "exchange_rate": exchange_rate,
            "vat_percent": "7",
            "effective_at": effective_at or datetime(2026, 4, 1, 9, 0),
            "expire_at": expire_at,
        }
        payload.update(final_inputs or {})
        return await create_price_record(db, actor=actor, request=None, payload=payload)

    def _verification_payload(
        self,
        *,
        request_code: str,
        workflow_domain: str = "pricing",
        risk_score: int = 60,
        risk_level: str | None = None,
        safety_status: str = "safe",
        sla_deadline_at: datetime | None = None,
    ) -> dict:
        return {
            "request_code": request_code,
            "subject_domain": workflow_domain,
            "queue_key": "dev-review",
            "change_summary": f"{workflow_domain} change",
            "request_reason": f"{workflow_domain} verification",
            "branch_id": self.branch_id,
            "risk_score": risk_score,
            "risk_level": risk_level or VerificationRiskLevel.HIGH.value,
            "safety_status": safety_status,
            "sla_deadline_at": sla_deadline_at,
            "items": [
                {
                    "entity_type": workflow_domain,
                    "entity_id": f"{workflow_domain}-entity-1",
                    "change_type": "update",
                    "handler_key": f"{workflow_domain}.handler",
                    "approval_strategy": "manual_follow_up",
                    "risk_level": risk_level or VerificationRiskLevel.HIGH.value,
                    "safety_status": safety_status,
                    "before_json": {"old": 1},
                    "proposed_after_json": {"new": 2},
                    "diff_summary": f"{workflow_domain} diff",
                }
            ],
        }

    def test_quick_search_matches_sku_alias_and_name(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                sku_rows = await quick_search_catalog(db, query="SKU-100")
                self.assertEqual([row["sku"] for row in sku_rows], ["SKU-100"])

                alias_rows = await quick_search_catalog(db, query="hex bolt")
                self.assertEqual(alias_rows[0]["product_id"], self.product_1_id)

                fuzzy_rows = await quick_search_catalog(db, query="stainless")
                self.assertEqual(fuzzy_rows[0]["product_id"], self.product_2_id)

        asyncio.run(_scenario())

    def test_deep_comparison_groups_by_canonical_group_and_ranks_deterministically(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                dev = await self._get_user(db, self.dev_id)
                group = await create_canonical_group(db, actor=dev, code="CG-BOLT", display_name="Bolt Group", request=None)
                await add_product_to_group(db, actor=dev, group_id=group.id, product_id=self.product_1_id, reason="seed", request=None)
                await add_product_to_group(db, actor=dev, group_id=group.id, product_id=self.product_2_id, reason="seed", request=None)

                first = await self._create_price(db, actor=dev, product_id=self.product_1_id, supplier_id=self.supplier_1_id, original_amount="100")
                second = await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_2_id,
                    supplier_id=self.supplier_2_id,
                    original_currency="USD",
                    original_amount="2.00",
                    exchange_rate="35",
                    final_inputs={"shipping_cost": "0"},
                )
                third = await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_1_id,
                    supplier_id=self.supplier_2_id,
                    original_amount="70",
                    final_inputs={"shipping_cost": "0"},
                )
                await db.commit()

                result = await compare_prices(db, product_id=self.product_1_id, branch_id=self.branch_id, quantity=5, selection_mode="active")
                self.assertEqual(result["scope_canonical_group_id"], group.id)
                self.assertEqual(result["compare_currency"], "THB")
                self.assertEqual({row["product_id"] for row in result["rows"]}, {self.product_1_id, self.product_2_id})
                expected_tied_ids = sorted([third.id, second.id])
                self.assertEqual([row["price_record_id"] for row in result["rows"][:2]], expected_tied_ids)
                self.assertEqual(result["rows"][2]["price_record_id"], first.id)
                self.assertEqual(result["rows"][0]["final_total_cost_thb"], result["rows"][1]["final_total_cost_thb"])
                self.assertEqual(
                    [row["price_record_id"] for row in result["rows"][:2]],
                    sorted([row["price_record_id"] for row in result["rows"][:2]]),
                )

        asyncio.run(_scenario())

    def test_compare_latest_selection_filters_and_quantity_enforcement(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                dev = await self._get_user(db, self.dev_id)
                await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_1_id,
                    supplier_id=self.supplier_1_id,
                    status="active",
                    quantity_min=1,
                    quantity_max=9,
                    effective_at=datetime(2026, 4, 1, 9, 0),
                    delivery_mode="standard",
                    area_scope="global",
                    final_inputs={"shipping_cost": "10"},
                )
                latest = await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_1_id,
                    supplier_id=self.supplier_1_id,
                    status="inactive",
                    quantity_min=1,
                    quantity_max=9,
                    effective_at=datetime(2026, 4, 2, 9, 0),
                    delivery_mode="standard",
                    area_scope="global",
                    final_inputs={"shipping_cost": "5"},
                )
                tier_2 = await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_1_id,
                    supplier_id=self.supplier_1_id,
                    status="active",
                    quantity_min=10,
                    quantity_max=49,
                    delivery_mode="express",
                    area_scope="local",
                    final_inputs={"shipping_cost": "3"},
                )
                await db.commit()

                latest_result = await compare_prices(
                    db,
                    product_id=self.product_1_id,
                    branch_id=self.branch_id,
                    quantity=5,
                    selection_mode="latest",
                    as_of=datetime(2026, 4, 3, 9, 0),
                    delivery_modes=["standard"],
                    area_scopes=["global"],
                    lifecycle_statuses=["active", "inactive"],
                )
                self.assertEqual(latest_result["row_count"], 1)
                self.assertEqual(latest_result["rows"][0]["price_record_id"], latest.id)
                self.assertEqual(latest_result["rows"][0]["normalized_currency"], "THB")

                tier_result = await compare_prices(
                    db,
                    product_id=self.product_1_id,
                    branch_id=self.branch_id,
                    quantity=20,
                    selection_mode="active",
                    delivery_modes=["express"],
                    area_scopes=["local"],
                    final_total_cost_min="0",
                    final_total_cost_max="500",
                    normalized_amount_min="0",
                    normalized_amount_max="500",
                )
                self.assertEqual(tier_result["row_count"], 1)
                self.assertEqual(tier_result["rows"][0]["price_record_id"], tier_2.id)
                self.assertEqual(tier_result["rows"][0]["delivery_mode"], "express")
                self.assertEqual(tier_result["rows"][0]["area_scope"], "local")

        asyncio.run(_scenario())

    def test_historical_queries_respect_as_of_range_and_overlap(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                dev = await self._get_user(db, self.dev_id)
                first = await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_1_id,
                    supplier_id=self.supplier_1_id,
                    status="active",
                    quantity_min=1,
                    quantity_max=9,
                    effective_at=datetime(2026, 1, 1, 0, 0),
                )
                replacement = await replace_price_record(
                    db,
                    existing_record=first,
                    actor=dev,
                    request=None,
                    replacement_payload={
                        "original_currency": "THB",
                        "original_amount": "120",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 2, 1, 0, 0),
                    },
                )
                replacement.archived_at = datetime(2026, 3, 1, 0, 0)
                replacement.status = PriceRecordStatus.ARCHIVED
                await db.flush()
                await sync_search_projections_for_supplier(db, supplier_id=self.supplier_1_id)
                await db.commit()

                as_of = await compare_prices(
                    db,
                    product_id=self.product_1_id,
                    quantity=5,
                    selection_mode="historical",
                    from_at=datetime(2026, 1, 15, 0, 0),
                    to_at=datetime(2026, 1, 15, 0, 0),
                )
                self.assertEqual(as_of["row_count"], 1)
                self.assertEqual(as_of["rows"][0]["price_record_id"], first.id)

                history = await search_price_history(
                    db,
                    product_id=self.product_1_id,
                    from_at=datetime(2026, 1, 15, 0, 0),
                    to_at=datetime(2026, 3, 15, 0, 0),
                )
                self.assertEqual([row["price_record_id"] for row in history], [replacement.id, first.id])
                self.assertEqual(history[0]["status"], PriceRecordStatus.ARCHIVED.value)
                self.assertEqual(history[1]["status"], PriceRecordStatus.REPLACED.value)

        asyncio.run(_scenario())

    def test_admin_search_filters_assignment_risk_status_and_overdue(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                admin = await self._get_user(db, self.admin_id)
                dev = await self._get_user(db, self.dev_id)
                owner = await self._get_user(db, self.owner_id)

                pending = await create_verification_request(
                    db,
                    actor=admin,
                    payload=self._verification_payload(
                        request_code="VR-SEARCH-1",
                        workflow_domain="supplier",
                        risk_score=30,
                        risk_level=VerificationRiskLevel.MEDIUM.value,
                    ),
                    request=None,
                )
                rejected = await create_verification_request(
                    db,
                    actor=admin,
                    payload=self._verification_payload(
                        request_code="VR-SEARCH-2",
                        workflow_domain="pricing",
                        risk_score=80,
                        risk_level=VerificationRiskLevel.CRITICAL.value,
                    ),
                    request=None,
                )
                overdue = await create_verification_request(
                    db,
                    actor=admin,
                    payload=self._verification_payload(
                        request_code="VR-SEARCH-3",
                        workflow_domain="matching",
                        risk_score=55,
                        risk_level=VerificationRiskLevel.HIGH.value,
                        sla_deadline_at=datetime.utcnow() - timedelta(hours=3),
                    ),
                    request=None,
                )
                await assign_verification_request(
                    db,
                    request_id=pending.id,
                    actor=owner,
                    assigned_to_user_id=dev.id,
                    assigned_role=Role.DEV.value,
                    reason="assign dev",
                    request=None,
                )
                await reject_verification_request(db, request_id=rejected.id, actor=owner, reason="reject", request=None)
                await assign_verification_request(
                    db,
                    request_id=overdue.id,
                    actor=owner,
                    assigned_to_user_id=owner.id,
                    assigned_role=Role.OWNER.value,
                    reason="assign owner",
                    request=None,
                )
                await mark_verification_request_overdue(db, request_id=overdue.id, actor=None, request=None)
                await db.commit()

                pending_rows = await search_verification_queue(
                    db,
                    workflow_statuses=[VerificationWorkflowStatus.PENDING.value],
                    assignee_user_id=dev.id,
                )
                self.assertEqual([row["request_code"] for row in pending_rows], ["VR-SEARCH-1"])

                critical_rows = await search_verification_queue(
                    db,
                    workflow_statuses=[VerificationWorkflowStatus.REJECTED.value],
                    risk_levels=[VerificationRiskLevel.CRITICAL.value],
                )
                self.assertEqual([row["request_code"] for row in critical_rows], ["VR-SEARCH-2"])

                overdue_rows = await search_verification_queue(db, overdue_only=True)
                self.assertEqual([row["request_code"] for row in overdue_rows], ["VR-SEARCH-3"])
                self.assertTrue(overdue_rows[0]["is_overdue"])

        asyncio.run(_scenario())

    def test_projection_sync_updates_for_price_replace_matching_supplier_and_verification(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                dev = await self._get_user(db, self.dev_id)
                owner = await self._get_user(db, self.owner_id)
                admin = await self._get_user(db, self.admin_id)

                base_record = await self._create_price(
                    db,
                    actor=dev,
                    product_id=self.product_1_id,
                    supplier_id=self.supplier_1_id,
                    status="active",
                    quantity_min=1,
                    quantity_max=9,
                    effective_at=datetime(2026, 4, 1, 0, 0),
                )
                replacement = await replace_price_record(
                    db,
                    existing_record=base_record,
                    actor=dev,
                    request=None,
                    replacement_payload={
                        "original_currency": "THB",
                        "original_amount": "95",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 2, 0, 0),
                    },
                )
                await db.flush()

                old_projection = await db.scalar(select(PriceSearchProjection).where(PriceSearchProjection.price_record_id == base_record.id))
                new_projection = await db.scalar(select(PriceSearchProjection).where(PriceSearchProjection.price_record_id == replacement.id))
                catalog = await db.scalar(select(CatalogSearchDocument).where(CatalogSearchDocument.product_id == self.product_1_id))
                self.assertEqual(old_projection.status, PriceRecordStatus.REPLACED)
                self.assertEqual(new_projection.status, PriceRecordStatus.ACTIVE)
                self.assertEqual(catalog.latest_price_record_id, replacement.id)

                group_1 = await create_canonical_group(db, actor=dev, code="CG-ONE", display_name="Group One", request=None)
                group_2 = await create_canonical_group(db, actor=dev, code="CG-TWO", display_name="Group Two", request=None)
                await add_product_to_group(db, actor=dev, group_id=group_1.id, product_id=self.product_1_id, reason="seed", request=None)
                compare_group = await compare_prices(db, product_id=self.product_1_id, quantity=5, selection_mode="active")
                self.assertEqual(compare_group["scope_canonical_group_id"], group_1.id)

                await move_product_between_groups(
                    db,
                    actor=dev,
                    source_group_id=group_1.id,
                    target_group_id=group_2.id,
                    product_id=self.product_1_id,
                    reason="move",
                    request=None,
                )
                moved_doc = await db.scalar(select(CatalogSearchDocument).where(CatalogSearchDocument.product_id == self.product_1_id))
                moved_projection = await db.scalar(select(PriceSearchProjection).where(PriceSearchProjection.price_record_id == replacement.id))
                self.assertEqual(moved_doc.canonical_group_id, group_2.id)
                self.assertEqual(moved_projection.canonical_group_id, group_2.id)

                supplier = await self._get_supplier(db, self.supplier_1_id)
                apply_supplier_payload(
                    supplier,
                    {
                        "name": "Alpha Prime Supply",
                        "status": supplier.status.value,
                        "is_verified": True,
                    },
                    actor_id=dev.id,
                )
                await sync_search_projections_for_supplier(db, supplier_id=supplier.id)
                supplier_rows = await quick_search_catalog(db, supplier_query="prime")
                self.assertEqual([row["product_id"] for row in supplier_rows], [self.product_1_id])

                request_record = await create_verification_request(
                    db,
                    actor=admin,
                    payload=self._verification_payload(
                        request_code="VR-QUEUE-SYNC",
                        workflow_domain="formula",
                        risk_score=55,
                        risk_level=VerificationRiskLevel.HIGH.value,
                    ),
                    request=None,
                )
                await reject_verification_request(db, request_id=request_record.id, actor=owner, reason="reject now", request=None)
                await db.commit()

                queue_projection = await db.scalar(select(VerificationQueueProjection).where(VerificationQueueProjection.request_id == request_record.id))
                queue_rows = await search_verification_queue(db, workflow_statuses=[VerificationWorkflowStatus.REJECTED.value])
                self.assertEqual(queue_projection.workflow_status, VerificationWorkflowStatus.REJECTED)
                self.assertEqual([row["request_code"] for row in queue_rows], ["VR-QUEUE-SYNC"])

        asyncio.run(_scenario())
