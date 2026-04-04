from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.api import zones as zones_api
from server.config.settings import Settings, settings
from server.db.database import Base
from server.db.models import (
    AreaScope,
    Branch,
    CatalogSearchDocument,
    NotificationAssignmentMode,
    NotificationChannel,
    NotificationEvent,
    NotificationEventStatus,
    NotificationOutbox,
    NotificationOutboxStatus,
    NotificationSeverity,
    NotificationType,
    PriceDimension,
    PriceRecord,
    PriceRecordStatus,
    PriceSearchProjection,
    PriceSourceType,
    Product,
    ReportSnapshot,
    ReportSnapshotStatus,
    ReportSnapshotType,
    Role,
    StockStatus,
    Supplier,
    User,
    VerificationApprovalStrategy,
    VerificationRequestItem,
)
from server.services.notifications import (
    claim_notification_outbox_batch,
    deliver_notification_outbox_item,
    process_pending_notifications,
    publish_notification_event,
)
from server.services.search import (
    compare_prices,
    quick_search_catalog,
    search_price_history,
)
from server.services.security import hash_password
from server.services.snapshots import create_verification_approval_snapshot, get_report_snapshot_by_id
from server.services.verification import create_verification_request


class Phase10HardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._settings_snapshot = {
            "search_result_limit_max": settings.search_result_limit_max,
            "search_query_timeout_seconds": settings.search_query_timeout_seconds,
            "report_query_timeout_seconds": settings.report_query_timeout_seconds,
            "historical_query_max_days": settings.historical_query_max_days,
            "snapshot_max_payload_bytes": settings.snapshot_max_payload_bytes,
            "notification_worker_batch_size": settings.notification_worker_batch_size,
            "notification_max_batch_size": settings.notification_max_batch_size,
            "notification_max_retry_attempts": settings.notification_max_retry_attempts,
            "notification_processing_timeout_seconds": settings.notification_processing_timeout_seconds,
            "notification_delivery_timeout_seconds": settings.notification_delivery_timeout_seconds,
            "notification_lock_seconds": settings.notification_lock_seconds,
        }
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", future=True)
        self.SessionLocal = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        asyncio.run(self._init_db())

    def tearDown(self) -> None:
        for key, value in self._settings_snapshot.items():
            setattr(settings, key, value)
        asyncio.run(self.engine.dispose())
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    async def _init_db(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.SessionLocal() as db:
            now = datetime.utcnow()
            branch = Branch(code="MAIN", name="Main", description="Main", is_default=True, is_active=True)
            owner = User(username="owner", display_name="Owner", role=Role.OWNER, is_active=True, language="th", password_hash=hash_password("Owner@1234"))
            dev = User(username="dev", display_name="Dev", role=Role.DEV, is_active=True, language="th", password_hash=hash_password("Dev@1234"))
            db.add_all([branch, owner, dev])
            await db.flush()

            product = Product(
                sku="SKU-HARD-001",
                branch_id=branch.id,
                name_th="Hard Product",
                name_en="Hard Product",
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
                barcode="HARD-001",
                created_by=owner.id,
            )
            extra_products = [
                Product(
                    sku=f"SKU-HARD-00{idx}",
                    branch_id=branch.id,
                    name_th=f"Hard Product {idx}",
                    name_en=f"Hard Product {idx}",
                    category="Hardware",
                    type="bolt",
                    unit="pcs",
                    cost_price=100 + idx,
                    selling_price=120 + idx,
                    stock_qty=10,
                    min_stock=1,
                    max_stock=20,
                    status=StockStatus.NORMAL,
                    supplier="Alpha",
                    barcode=f"HARD-00{idx}",
                    created_by=owner.id,
                )
                for idx in range(2, 6)
            ]
            supplier = Supplier(
                branch_id=branch.id,
                code="SUP-HARD",
                name="Alpha Supplier",
                normalized_name="alpha supplier",
                is_verified=True,
                created_by=owner.id,
                updated_by=owner.id,
            )
            db.add_all([product, *extra_products, supplier])
            await db.flush()

            self.branch_id = branch.id
            self.owner_id = owner.id
            self.dev_id = dev.id
            self.product_id = product.id
            self.supplier_id = supplier.id

            catalog_products = [product, *extra_products]
            for idx, item_product in enumerate(catalog_products):
                db.add(
                    CatalogSearchDocument(
                        product_id=item_product.id,
                        branch_id=branch.id,
                        canonical_group_id=None,
                        canonical_group_name="",
                        sku=f"SKU-HARD-{idx}",
                        name_th=f"Hard Product {idx}",
                        name_en=f"Hard Product {idx}",
                        category_text="Hardware",
                        alias_text=f"alias {idx}",
                        tag_text="tag",
                        supplier_text="Alpha Supplier",
                        search_text=f"sku-hard-{idx} hard product {idx}",
                        lifecycle_status="active",
                        active_price_count=1,
                        verified_supplier_count=1,
                        latest_effective_at=now,
                        latest_final_total_cost_thb=100 + idx,
                        cheapest_active_final_total_cost_thb=100 + idx,
                    )
                )

            for idx in range(3):
                db.add(
                    PriceSearchProjection(
                        price_record_id=f"price-proj-{idx}",
                        product_id=product.id,
                        branch_id=branch.id,
                        supplier_id=supplier.id,
                        canonical_group_id=None,
                        canonical_group_name="",
                        sku=product.sku,
                        product_name_th=product.name_th,
                        product_name_en=product.name_en,
                        category_text=product.category,
                        supplier_name=supplier.name,
                        supplier_is_verified=True,
                        status=PriceRecordStatus.ACTIVE,
                        source_type=PriceSourceType.MANUAL_ENTRY,
                        delivery_mode="standard",
                        area_scope=AreaScope.GLOBAL.value,
                        price_dimension=PriceDimension.REAL_TOTAL_COST.value,
                        quantity_min=1,
                        quantity_max=9,
                        original_currency="THB",
                        normalized_currency="THB",
                        normalized_amount_thb=100 + idx,
                        vat_amount_thb=7,
                        shipping_cost_thb=1,
                        fuel_cost_thb=1,
                        labor_cost_thb=1,
                        utility_cost_thb=1,
                        supplier_fee_thb=0,
                        discount_thb=0,
                        final_total_cost_thb=110 + idx,
                        effective_at=now - timedelta(days=idx),
                        updated_at=now - timedelta(days=idx),
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
                original_currency="THB",
                normalized_currency="THB",
                original_amount=100,
                normalized_amount=100,
                exchange_rate=1,
                exchange_rate_snapshot_at=now,
                base_price=100,
                vat_percent=7,
                vat_amount=7,
                shipping_cost=1,
                fuel_cost=1,
                labor_cost=1,
                utility_cost=1,
                supplier_fee=0,
                discount=0,
                final_total_cost=110,
                effective_at=now - timedelta(days=1),
                created_by=owner.id,
            )
            db.add(price)
            await db.flush()
            self.price_id = price.id

            event = NotificationEvent(
                event_type="verification.request_submitted",
                notification_type=NotificationType.IMMEDIATE,
                source_domain="verification",
                source_entity_type="verification_request",
                source_entity_id="vr-1",
                branch_id=branch.id,
                severity=NotificationSeverity.HIGH,
                priority=75,
                status=NotificationEventStatus.PENDING,
                payload_json={"message": "verify"},
                dedupe_key="event-1",
                triggered_by_user_id=owner.id,
                occurred_at=now,
            )
            db.add(event)
            await db.flush()
            self.notification_event_id = event.id

            outbox = NotificationOutbox(
                event_id=event.id,
                channel=NotificationChannel.LINE,
                assignment_mode=NotificationAssignmentMode.USER,
                recipient_user_id=dev.id,
                routing_role=Role.DEV.value,
                branch_id=branch.id,
                severity=NotificationSeverity.HIGH,
                priority=75,
                status=NotificationOutboxStatus.PROCESSING,
                message_title="Verify",
                message_body="Please verify",
                payload_json={"message": "verify"},
                dedupe_key="outbox-1",
                max_attempts=4,
                worker_token="worker-1",
                locked_at=now,
                last_attempt_at=now,
            )
            db.add(outbox)
            await db.flush()
            self.processing_outbox_id = outbox.id

            await db.commit()

    async def _get_user(self, db: AsyncSession, user_id: str) -> User:
        user = await db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        return user

    def test_guardrails_limits_and_safe_defaults(self) -> None:
        async def scenario() -> None:
            settings.search_result_limit_max = 2
            settings.historical_query_max_days = 30
            settings.snapshot_max_payload_bytes = 128
            settings.notification_max_retry_attempts = 2
            settings.notification_worker_batch_size = 10
            settings.notification_max_batch_size = 1

            async with self.SessionLocal() as db:
                rows = await quick_search_catalog(db, query="sku-hard", limit=99)
                self.assertEqual(len(rows), 2)

                with self.assertRaises(HTTPException) as history_failed:
                    await search_price_history(
                        db,
                        product_id=self.product_id,
                        from_at=datetime.utcnow() - timedelta(days=40),
                        to_at=datetime.utcnow(),
                    )
                self.assertEqual(history_failed.exception.detail, "historical_range_too_large")

                owner = await self._get_user(db, self.owner_id)
                request = await create_verification_request(
                    db,
                    actor=owner,
                    payload={
                        "subject_domain": "pricing",
                        "queue_key": "pricing",
                        "risk_score": 80,
                        "risk_level": "critical",
                        "safety_status": "warning",
                        "change_summary": "large snapshot",
                        "request_reason": "large snapshot",
                        "branch_id": self.branch_id,
                        "items": [
                            {
                                "entity_type": "price_record",
                                "entity_id": self.price_id,
                                "change_type": "archive",
                                "handler_key": "pricing.manual",
                                "approval_strategy": VerificationApprovalStrategy.MANUAL_FOLLOW_UP.value,
                                "risk_level": "critical",
                                "safety_status": "warning",
                                "before_json": {"blob": "x" * 512},
                                "proposed_after_json": {"status": "archived"},
                                "handler_payload_json": {},
                                "diff_summary": "archive",
                            }
                        ],
                    },
                )
                await db.flush()
                items = (await db.execute(select(VerificationRequestItem).where(VerificationRequestItem.request_id == request.id))).scalars().all()
                with self.assertLogs("server.services.snapshots", level="ERROR") as snapshot_logs:
                    with self.assertRaises(HTTPException) as snapshot_failed:
                        await create_verification_approval_snapshot(
                            db,
                            request_record=request,
                            items=items,
                            dependency_warnings=[],
                            actor=owner,
                            apply_results=[],
                            reason="too large",
                        )
                self.assertEqual(snapshot_failed.exception.detail, "report_snapshot_payload_too_large")
                self.assertTrue(any("report_snapshot_create_failed:verification" in entry for entry in snapshot_logs.output))

                event = await publish_notification_event(
                    db,
                    event_type="pricing.guardrail",
                    source_domain="pricing",
                    source_entity_type="price_record",
                    source_entity_id=self.price_id,
                    severity="high",
                    payload={"product_id": self.product_id},
                    triggered_by_user_id=self.owner_id,
                    branch_id=self.branch_id,
                    target_roles=[Role.DEV.value],
                )
                await db.flush()
                outboxes = (await db.execute(select(NotificationOutbox).where(NotificationOutbox.event_id == event.id))).scalars().all()
                self.assertTrue(all(item.max_attempts == 2 for item in outboxes))

                for idx in range(3):
                    db.add(
                        NotificationOutbox(
                            event_id=self.notification_event_id,
                            channel=NotificationChannel.EMAIL,
                            assignment_mode=NotificationAssignmentMode.USER,
                            recipient_user_id=self.dev_id,
                            routing_role=Role.DEV.value,
                            branch_id=self.branch_id,
                            severity=NotificationSeverity.MEDIUM,
                            priority=50,
                            status=NotificationOutboxStatus.PENDING,
                            message_title=f"Batch {idx}",
                            message_body="batch",
                            payload_json={},
                            dedupe_key=f"batch-{idx}",
                            max_attempts=2,
                        )
                    )
                await db.flush()
                claimed = await claim_notification_outbox_batch(db, worker_token="worker-batch", limit=99)
                self.assertEqual(len(claimed), 1)

            default_settings = Settings()
            self.assertGreater(default_settings.search_result_limit_max, 0)
            self.assertGreater(default_settings.notification_max_retry_attempts, 0)
            self.assertGreater(default_settings.snapshot_max_payload_bytes, 0)

        asyncio.run(scenario())

    def test_timeout_safety_monitoring_and_pagination_guards(self) -> None:
        async def scenario() -> None:
            async def fail_wait_for(coro, *args, **kwargs):
                if hasattr(coro, "close"):
                    coro.close()
                raise asyncio.TimeoutError()

            async with self.SessionLocal() as db:
                with patch("server.services.search.asyncio.wait_for", new=fail_wait_for):
                    with self.assertLogs("server.services.search", level="WARNING") as search_logs:
                        with self.assertRaises(HTTPException) as failed:
                            await quick_search_catalog(db, query="sku-hard", limit=10)
                    self.assertEqual(failed.exception.detail, "search_query_timeout")
                    self.assertTrue(any("search_timeout:quick_search_catalog" in entry for entry in search_logs.output))

                snapshot = ReportSnapshot(
                    snapshot_code="SNAP-TIMEOUT",
                    snapshot_type=ReportSnapshotType.AUDIT_BUNDLE,
                    scope_type="product",
                    scope_ref_id=self.product_id,
                    branch_id=self.branch_id,
                    as_of_at=datetime.utcnow(),
                    generation_reason="timeout",
                    generated_by_user_id=self.owner_id,
                    source_consistency_token="timeout",
                    status=ReportSnapshotStatus.COMPLETED,
                )
                db.add(snapshot)
                await db.flush()
                with patch("server.services.snapshots.asyncio.wait_for", new=fail_wait_for):
                    with self.assertLogs("server.services.snapshots", level="WARNING") as snapshot_logs:
                        with self.assertRaises(HTTPException) as snapshot_failed:
                            await get_report_snapshot_by_id(db, snapshot_id=snapshot.id)
                    self.assertEqual(snapshot_failed.exception.detail, "report_snapshot_query_timeout")
                    self.assertTrue(any("report_snapshot_query_timeout" in entry for entry in snapshot_logs.output))

                with patch("server.services.notifications.asyncio.wait_for", new=fail_wait_for):
                    with self.assertLogs("server.services.notifications", level="WARNING") as failure_logs:
                        outbox = await deliver_notification_outbox_item(
                            db,
                            outbox_id=self.processing_outbox_id,
                            worker_token="worker-1",
                        )
                    self.assertEqual(outbox.status, NotificationOutboxStatus.RETRY_SCHEDULED)
                    self.assertTrue(any("notification_processing_timeout" in entry for entry in failure_logs.output))

                pending_outbox = NotificationOutbox(
                    event_id=self.notification_event_id,
                    channel=NotificationChannel.EMAIL,
                    assignment_mode=NotificationAssignmentMode.USER,
                    recipient_user_id=self.dev_id,
                    recipient_address="dev@example.com",
                    routing_role=Role.DEV.value,
                    branch_id=self.branch_id,
                    severity=NotificationSeverity.MEDIUM,
                    priority=50,
                    status=NotificationOutboxStatus.PENDING,
                    message_title="Pending",
                    message_body="Pending",
                    payload_json={},
                    dedupe_key="pending-metric",
                    max_attempts=2,
                )
                db.add(pending_outbox)
                await db.flush()
                with patch("server.services.notifications._deliver_outbox_message", return_value="provider-1"):
                    with self.assertLogs("server.services.notifications", level="INFO") as processed_logs:
                        processed = await process_pending_notifications(db, worker_token="worker-metrics", limit=1)
                self.assertEqual(len(processed), 1)
                self.assertTrue(any("notification_queue_processed" in entry for entry in processed_logs.output))
                self.assertTrue(any("notification_outbox_claimed" in entry for entry in processed_logs.output))

                compare = await compare_prices(db, product_id=self.product_id, quantity=1, limit=999)
                self.assertLessEqual(compare["row_count"], settings.search_result_limit_max)

        with self.assertRaises(HTTPException) as invalid_id:
            zones_api._validate_optional_id("bad!", field_name="product_id")
        self.assertEqual(invalid_id.exception.detail, "invalid_product_id")

        long_text = "x" * 300
        with self.assertRaises(HTTPException) as invalid_q:
            zones_api._validate_optional_text(long_text, field_name="q", max_length=200)
        self.assertEqual(invalid_q.exception.detail, "invalid_q")

        asyncio.run(scenario())
