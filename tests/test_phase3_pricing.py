from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.database import Base
from server.db.models import (
    AuditEvent,
    AuditLog,
    Branch,
    CostFormula,
    CostFormulaVersion,
    FormulaStatus,
    PriceRecord,
    PriceRecordStatus,
    Product,
    Role,
    StockStatus,
    Supplier,
    User,
)
from server.services.cost_formulas import (
    activate_cost_formula_version,
    create_cost_formula,
    create_cost_formula_version,
    ensure_formula_version_mutable,
    update_cost_formula_version,
    validate_formula_expression,
)
from server.services.pricing import (
    archive_price_record,
    calculate_final_total_cost,
    calculate_vat_amount,
    create_price_record,
    find_conflicting_price_records,
    normalize_currency_amount,
    normalize_utc_datetime,
    quantity_ranges_overlap,
    replace_price_record,
    serialize_utc_datetime,
    time_ranges_overlap,
    validate_area_scope,
    validate_currency_code,
    validate_delivery_mode,
    validate_price_dimension,
    validate_quantity_range,
)
from server.services.security import hash_password


REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase3MigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_pricing_and_formula_tables(self) -> None:
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
                    "exchange_rate_snapshots",
                    "cost_formulas",
                    "cost_formula_versions",
                    "price_records",
                }.issubset(table_names)
            )

            cur.execute("PRAGMA table_info(price_records)")
            price_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue(
                {
                    "status",
                    "quantity_min",
                    "quantity_max",
                    "original_currency",
                    "normalized_amount",
                    "vat_amount",
                    "final_total_cost",
                    "formula_version_id",
                    "replaced_by_price_record_id",
                }.issubset(price_columns)
            )

            cur.execute("PRAGMA table_info(cost_formula_versions)")
            formula_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue(
                {
                    "variables_json",
                    "constants_json",
                    "dependency_keys_json",
                    "is_active_version",
                    "is_locked",
                    "activated_at",
                }.issubset(formula_columns)
            )
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            if os.path.exists(db_path):
                os.unlink(db_path)


class Phase3PricingUnitTests(unittest.TestCase):
    def test_quantity_range_validation_and_overlap(self) -> None:
        self.assertEqual(validate_quantity_range(1, 9), (1, 9))
        self.assertEqual(validate_quantity_range(50, None), (50, None))
        self.assertTrue(quantity_ranges_overlap(1, 9, 9, 20))
        self.assertFalse(quantity_ranges_overlap(1, 9, 10, 20))
        self.assertTrue(quantity_ranges_overlap(50, None, 70, None))

        with self.assertRaises(HTTPException) as invalid_min:
            validate_quantity_range(0, 10)
        self.assertEqual(invalid_min.exception.status_code, 400)

        with self.assertRaises(HTTPException) as invalid_range:
            validate_quantity_range(10, 9)
        self.assertEqual(invalid_range.exception.status_code, 400)

    def test_time_range_overlap(self) -> None:
        start = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
        self.assertTrue(
            time_ranges_overlap(
                start,
                start + timedelta(hours=2),
                start + timedelta(hours=1),
                start + timedelta(hours=3),
            )
        )
        self.assertFalse(
            time_ranges_overlap(
                start,
                start + timedelta(hours=2),
                start + timedelta(hours=2),
                start + timedelta(hours=4),
            )
        )
        self.assertTrue(time_ranges_overlap(start, None, start + timedelta(days=30), None))

    def test_datetime_normalization_and_serialization_use_utc_consistently(self) -> None:
        aware = datetime(2026, 4, 3, 17, 0, tzinfo=timezone(timedelta(hours=7)))
        normalized = normalize_utc_datetime(aware, field_name="effective_at")
        self.assertEqual(normalized, datetime(2026, 4, 3, 10, 0))

        naive = datetime(2026, 4, 3, 10, 0)
        self.assertEqual(normalize_utc_datetime(naive, field_name="effective_at"), naive)
        self.assertEqual(serialize_utc_datetime(aware), "2026-04-03T10:00:00+00:00")
        self.assertEqual(serialize_utc_datetime(naive), "2026-04-03T10:00:00+00:00")

    def test_currency_validation_and_normalization(self) -> None:
        self.assertEqual(validate_currency_code("thb").value, "THB")
        normalized_thb = normalize_currency_amount(original_currency="THB", original_amount="100", exchange_rate="999")
        self.assertEqual(normalized_thb.normalized_currency.value, "THB")
        self.assertEqual(normalized_thb.exchange_rate, Decimal("1.00000000"))
        self.assertEqual(normalized_thb.normalized_amount, Decimal("100.000000"))

        normalized_usd = normalize_currency_amount(original_currency="USD", original_amount="10", exchange_rate="36.5")
        self.assertEqual(normalized_usd.normalized_amount, Decimal("365.000000"))
        self.assertEqual(normalized_usd.exchange_rate, Decimal("36.50000000"))

        with self.assertRaises(HTTPException) as invalid_currency:
            validate_currency_code("EUR")
        self.assertEqual(invalid_currency.exception.detail, "unsupported_currency")

        with self.assertRaises(HTTPException) as invalid_rate:
            normalize_currency_amount(original_currency="USD", original_amount="10", exchange_rate="0")
        self.assertEqual(invalid_rate.exception.detail, "invalid_exchange_rate")

    def test_vat_and_total_cost_calculation(self) -> None:
        self.assertEqual(calculate_vat_amount("100", "7"), Decimal("7.000000"))

        total = calculate_final_total_cost(
            base_price="100",
            vat_percent="7",
            shipping_cost="10",
            fuel_cost="2",
            labor_cost="3",
            utility_cost="4",
            distance_meter="1500",
            distance_cost="5",
            supplier_fee="1",
            discount="6",
        )
        self.assertEqual(total.vat_amount, Decimal("7.000000"))
        self.assertEqual(total.final_total_cost, Decimal("126.000000"))

        with self.assertRaises(HTTPException) as invalid_vat:
            calculate_vat_amount("100", "101")
        self.assertEqual(invalid_vat.exception.detail, "invalid_vat_percent")

        with self.assertRaises(HTTPException) as invalid_discount:
            calculate_final_total_cost(base_price="10", vat_percent="0", discount="11")
        self.assertEqual(invalid_discount.exception.detail, "invalid_final_total_cost")

    def test_delivery_area_and_dimension_validation(self) -> None:
        self.assertEqual(validate_delivery_mode("express"), "express")
        self.assertEqual(validate_area_scope("branch"), "branch")
        self.assertEqual(validate_price_dimension("real_total_cost"), "real_total_cost")

        with self.assertRaises(HTTPException):
            validate_delivery_mode("overnight")
        with self.assertRaises(HTTPException):
            validate_area_scope("province")
        with self.assertRaises(HTTPException):
            validate_price_dimension("cheapest")

    def test_formula_expression_validation_and_immutability_guard(self) -> None:
        variables = validate_formula_expression("base_price + vat_amount + custom_input_1")
        self.assertEqual(variables, ["base_price", "vat_amount", "custom_input_1"])

        with self.assertRaises(HTTPException) as invalid_formula:
            validate_formula_expression("base_price + os.system")
        self.assertIn("invalid_formula_variables", invalid_formula.exception.detail)

        mutable_version = CostFormulaVersion(
            formula_id="f1",
            version_no=1,
            expression_text="base_price",
            variables_json=["base_price"],
            constants_json={},
            dependency_keys_json=["base_price"],
            is_active_version=False,
            is_locked=False,
            created_by="u1",
            created_at=datetime.utcnow(),
        )
        ensure_formula_version_mutable(mutable_version)

        immutable_version = CostFormulaVersion(
            formula_id="f1",
            version_no=2,
            expression_text="base_price",
            variables_json=["base_price"],
            constants_json={},
            dependency_keys_json=["base_price"],
            is_active_version=True,
            is_locked=True,
            activated_at=datetime.utcnow(),
            created_by="u1",
            created_at=datetime.utcnow(),
        )
        with self.assertRaises(HTTPException) as immutable_error:
            ensure_formula_version_mutable(immutable_version)
        self.assertEqual(immutable_error.exception.detail, "cost_formula_version_immutable")


class Phase3PricingIntegrationTests(unittest.TestCase):
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

            branch = Branch(
                code="MAIN",
                name="Main Branch",
                description="Main",
                is_default=True,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(branch)
            await db.flush()

            product = Product(
                sku="PRICE-001",
                branch_id=branch.id,
                name_th="Price Product",
                name_en="Price Product",
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
                supplier="Supplier One",
                barcode="",
                image_url=None,
                notes="",
                created_by=owner.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            supplier = Supplier(
                branch_id=branch.id,
                code="SUP-001",
                name="Supplier One",
                normalized_name="supplier-one",
                created_by=owner.id,
                updated_by=owner.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add_all([product, supplier])
            await db.commit()

    async def _seed_formula(
        self,
        db: AsyncSession,
        *,
        actor: User,
        code: str,
        expression_text: str = "base_price + vat_amount",
    ) -> tuple[CostFormula, CostFormulaVersion]:
        formula = await create_cost_formula(
            db,
            actor=actor,
            request=None,
            payload={
                "code": code,
                "name": code,
                "scope_type": "global",
                "status": FormulaStatus.DRAFT.value,
            },
        )
        version = await create_cost_formula_version(
            db,
            formula=formula,
            actor=actor,
            request=None,
            payload={"expression_text": expression_text},
        )
        await db.commit()
        return formula, version

    def test_create_price_record_calculates_totals_and_audit(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                record = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 1,
                        "quantity_max": 9,
                        "original_currency": "THB",
                        "original_amount": "100",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "shipping_cost": "10",
                        "fuel_cost": "2",
                        "labor_cost": "3",
                        "utility_cost": "4",
                        "distance_cost": "5",
                        "supplier_fee": "1",
                        "discount": "6",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                await db.commit()

                self.assertEqual(record.status, PriceRecordStatus.ACTIVE)
                self.assertEqual(record.normalized_amount, Decimal("100.000000"))
                self.assertEqual(record.vat_amount, Decimal("7.000000"))
                self.assertEqual(record.final_total_cost, Decimal("126.000000"))

                audit_logs = (await db.execute(select(AuditLog).where(AuditLog.action == "PRICE_RECORD_CREATE"))).scalars().all()
                audit_events = (await db.execute(select(AuditEvent).where(AuditEvent.action == "PRICE_RECORD_CREATE"))).scalars().all()
                self.assertEqual(len(audit_logs), 1)
                self.assertEqual(len(audit_events), 1)

        asyncio.run(_run())

    def test_usd_price_creates_snapshot_and_normalized_amount(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                record = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "supplier_quote",
                        "status": "draft",
                        "quantity_min": 10,
                        "quantity_max": 49,
                        "original_currency": "USD",
                        "original_amount": "10",
                        "exchange_rate": "36.5",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 4, tzinfo=timezone.utc),
                    },
                )
                await db.commit()

                self.assertEqual(record.normalized_amount, Decimal("365.000000"))
                self.assertEqual(record.exchange_rate, Decimal("36.50000000"))
                self.assertIsNotNone(record.exchange_rate_snapshot_id)

        asyncio.run(_run())

    def test_active_price_conflict_detection_blocks_overlap(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                first = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 1,
                        "quantity_max": 9,
                        "original_currency": "THB",
                        "original_amount": "100",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                await db.commit()

                conflicts = await find_conflicting_price_records(
                    db,
                    product_id=product.id,
                    supplier_id=supplier.id,
                    branch_id=branch.id,
                    delivery_mode="standard",
                    area_scope="global",
                    price_dimension="real_total_cost",
                    quantity_min=5,
                    quantity_max=15,
                    effective_at=datetime(2026, 4, 5, tzinfo=timezone.utc),
                    expire_at=None,
                )
                self.assertEqual([item.id for item in conflicts], [first.id])

                with self.assertRaises(HTTPException) as conflict_error:
                    await create_price_record(
                        db,
                        actor=actor,
                        request=None,
                        payload={
                            "product_id": product.id,
                            "supplier_id": supplier.id,
                            "branch_id": branch.id,
                            "source_type": "manual_entry",
                            "status": "active",
                            "quantity_min": 5,
                            "quantity_max": 15,
                            "original_currency": "THB",
                            "original_amount": "99",
                            "exchange_rate": "1",
                            "vat_percent": "7",
                            "effective_at": datetime(2026, 4, 5, tzinfo=timezone.utc),
                        },
                    )
                self.assertEqual(conflict_error.exception.status_code, 409)
                self.assertEqual(conflict_error.exception.detail, "active_price_conflict")

        asyncio.run(_run())

    def test_active_price_conflict_detection_handles_aware_and_naive_datetimes(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                first = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 1,
                        "quantity_max": 9,
                        "original_currency": "THB",
                        "original_amount": "100",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 3, 17, 0, tzinfo=timezone(timedelta(hours=7))),
                    },
                )
                await db.commit()

                first = await db.scalar(select(PriceRecord).where(PriceRecord.id == first.id))
                self.assertIsNotNone(first)
                self.assertEqual(first.effective_at, datetime(2026, 4, 3, 10, 0))

                with self.assertRaises(HTTPException) as conflict_error:
                    await create_price_record(
                        db,
                        actor=actor,
                        request=None,
                        payload={
                            "product_id": product.id,
                            "supplier_id": supplier.id,
                            "branch_id": branch.id,
                            "source_type": "manual_entry",
                            "status": "active",
                            "quantity_min": 5,
                            "quantity_max": 15,
                            "original_currency": "THB",
                            "original_amount": "99",
                            "exchange_rate": "1",
                            "vat_percent": "7",
                            "effective_at": datetime(2026, 4, 3, 10, 30),
                        },
                    )
                self.assertEqual(conflict_error.exception.detail, "active_price_conflict")

        asyncio.run(_run())

    def test_active_price_allows_non_overlapping_and_different_conditions(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 1,
                        "quantity_max": 9,
                        "original_currency": "THB",
                        "original_amount": "100",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                non_overlap = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 10,
                        "quantity_max": 49,
                        "original_currency": "THB",
                        "original_amount": "95",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                different_area = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 1,
                        "quantity_max": 9,
                        "original_currency": "THB",
                        "original_amount": "101",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "area_scope": "branch",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                inactive_overlap = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "inactive",
                        "quantity_min": 5,
                        "quantity_max": 15,
                        "original_currency": "THB",
                        "original_amount": "102",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                await db.commit()

                self.assertEqual(non_overlap.status, PriceRecordStatus.ACTIVE)
                self.assertEqual(different_area.status, PriceRecordStatus.ACTIVE)
                self.assertEqual(inactive_overlap.status, PriceRecordStatus.INACTIVE)

        asyncio.run(_run())

    def test_replace_and_archive_price_record_lifecycle(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                original = await create_price_record(
                    db,
                    actor=actor,
                    request=None,
                    payload={
                        "product_id": product.id,
                        "supplier_id": supplier.id,
                        "branch_id": branch.id,
                        "source_type": "manual_entry",
                        "status": "active",
                        "quantity_min": 50,
                        "quantity_max": None,
                        "original_currency": "THB",
                        "original_amount": "100",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 3, tzinfo=timezone.utc),
                    },
                )
                await db.commit()

                replacement = await replace_price_record(
                    db,
                    existing_record=original,
                    actor=actor,
                    request=None,
                    replacement_payload={
                        "original_currency": "THB",
                        "original_amount": "90",
                        "exchange_rate": "1",
                        "vat_percent": "7",
                        "effective_at": datetime(2026, 4, 10, tzinfo=timezone.utc),
                    },
                )
                await db.commit()
                await db.refresh(original)
                await db.refresh(replacement)

                self.assertEqual(original.status, PriceRecordStatus.REPLACED)
                self.assertEqual(original.replaced_by_price_record_id, replacement.id)
                self.assertEqual(original.expire_at, replacement.effective_at)
                self.assertEqual(replacement.status, PriceRecordStatus.ACTIVE)

                archived = await archive_price_record(
                    db,
                    record=replacement,
                    actor=actor,
                    request=None,
                    reason="phase3_archive_test",
                )
                await db.commit()
                self.assertEqual(archived.status, PriceRecordStatus.ARCHIVED)
                self.assertIsNotNone(archived.archived_at)

        asyncio.run(_run())

    def test_formula_version_lifecycle_and_price_formula_mismatch(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                actor = await db.scalar(select(User).where(User.username == "owner"))
                product = await db.scalar(select(Product).where(Product.sku == "PRICE-001"))
                supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-001"))
                branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
                assert actor and product and supplier and branch

                formula_one, version_one = await self._seed_formula(db, actor=actor, code="FORM-A")
                updated = await update_cost_formula_version(
                    db,
                    version=version_one,
                    actor=actor,
                    request=None,
                    payload={"expression_text": "base_price + vat_amount + shipping_cost"},
                )
                self.assertIn("shipping_cost", updated.expression_text)

                activated = await activate_cost_formula_version(
                    db,
                    formula=formula_one,
                    version=version_one,
                    actor=actor,
                    request=None,
                )
                await db.commit()
                self.assertTrue(activated.is_active_version)
                self.assertTrue(activated.is_locked)
                self.assertIsNotNone(activated.activated_at)

                with self.assertRaises(HTTPException) as immutable_error:
                    await update_cost_formula_version(
                        db,
                        version=version_one,
                        actor=actor,
                        request=None,
                        payload={"expression_text": "base_price"},
                    )
                self.assertEqual(immutable_error.exception.detail, "cost_formula_version_immutable")

                _, version_two = await self._seed_formula(db, actor=actor, code="FORM-B")
                with self.assertRaises(HTTPException) as mismatch_error:
                    await create_price_record(
                        db,
                        actor=actor,
                        request=None,
                        payload={
                            "product_id": product.id,
                            "supplier_id": supplier.id,
                            "branch_id": branch.id,
                            "source_type": "manual_entry",
                            "status": "draft",
                            "quantity_min": 1,
                            "quantity_max": 9,
                            "original_currency": "THB",
                            "original_amount": "100",
                            "exchange_rate": "1",
                            "vat_percent": "7",
                            "formula_id": formula_one.id,
                            "formula_version_id": version_two.id,
                            "effective_at": datetime(2026, 4, 20, tzinfo=timezone.utc),
                        },
                    )
                self.assertEqual(mismatch_error.exception.detail, "cost_formula_version_mismatch")

                version_next = await create_cost_formula_version(
                    db,
                    formula=formula_one,
                    actor=actor,
                    request=None,
                    payload={"expression_text": "base_price + vat_amount + fuel_cost"},
                )
                await activate_cost_formula_version(
                    db,
                    formula=formula_one,
                    version=version_next,
                    actor=actor,
                    request=None,
                )
                await db.commit()
                await db.refresh(formula_one)
                await db.refresh(version_one)
                await db.refresh(version_next)

                self.assertEqual(formula_one.active_version_id, version_next.id)
                self.assertFalse(version_one.is_active_version)
                self.assertEqual(version_one.replaced_version_id, version_next.id)
                self.assertTrue(version_next.is_active_version)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
