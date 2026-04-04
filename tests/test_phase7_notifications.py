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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.config.settings import settings
from server.db.database import Base
from server.db.models import (
    Branch,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEvent,
    NotificationFailure,
    NotificationFailureType,
    NotificationOutbox,
    NotificationOutboxStatus,
    PriceRecord,
    Product,
    Role,
    StockStatus,
    Supplier,
    SupplierChangeProposal,
    SupplierProductLink,
    User,
    UserBranchScope,
    VerificationRequest,
)
from server.services.notifications import (
    NotificationSeverity,
    claim_notification_outbox_batch,
    deliver_notification_outbox_item,
    process_pending_notifications,
    publish_notification_event,
)
from server.services.pricing import create_price_record
from server.services.security import hash_password
from server.services.suppliers import create_supplier_change_proposal
from server.services.verification import assign_verification_request, create_verification_request


REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase7MigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_notification_tables(self) -> None:
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
                    "notification_events",
                    "notification_outbox",
                    "notification_deliveries",
                    "notification_failures",
                    "notification_preferences",
                    "notification_templates",
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


class Phase7NotificationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._settings_snapshot = {
            "notification_email_dev": settings.notification_email_dev,
            "notification_email_owner": settings.notification_email_owner,
            "notification_email_admin": settings.notification_email_admin,
            "notification_email_stock": settings.notification_email_stock,
            "notification_worker_batch_size": settings.notification_worker_batch_size,
            "notification_lock_seconds": settings.notification_lock_seconds,
            "smtp_host": settings.smtp_host,
            "smtp_from_email": settings.smtp_from_email,
            "smtp_port": settings.smtp_port,
        }
        settings.notification_email_dev = "dev@example.com"
        settings.notification_email_owner = "owner@example.com"
        settings.notification_email_admin = "admin@example.com"
        settings.notification_email_stock = "stock@example.com"
        settings.notification_worker_batch_size = 10
        settings.notification_lock_seconds = 120
        settings.smtp_host = "smtp.example.com"
        settings.smtp_from_email = "noreply@example.com"
        settings.smtp_port = 587

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
            self.main_branch = Branch(code="MAIN", name="Main Branch", description="Main", is_default=True, is_active=True)
            self.other_branch = Branch(code="OTHER", name="Other Branch", description="Other", is_default=False, is_active=True)
            self.owner = User(
                username="owner",
                display_name="Owner",
                role=Role.OWNER,
                is_active=True,
                language="th",
                password_hash=hash_password("Owner@1234"),
                totp_secret=None,
            )
            self.dev = User(
                username="dev",
                display_name="Dev",
                role=Role.DEV,
                is_active=True,
                language="th",
                password_hash=hash_password("Dev@1234"),
                totp_secret=None,
            )
            self.dev_other = User(
                username="dev_other",
                display_name="Dev Other",
                role=Role.DEV,
                is_active=True,
                language="th",
                password_hash=hash_password("Dev@1234"),
                totp_secret=None,
            )
            self.admin = User(
                username="admin",
                display_name="Admin",
                role=Role.ADMIN,
                is_active=True,
                language="th",
                password_hash=hash_password("Admin@1234"),
                totp_secret=None,
            )
            db.add_all([self.main_branch, self.other_branch, self.owner, self.dev, self.dev_other, self.admin])
            await db.flush()
            db.add(
                UserBranchScope(
                    user_id=self.dev_other.id,
                    branch_id=self.other_branch.id,
                    can_view=True,
                    can_edit=False,
                    scope_source="test",
                )
            )

            self.product = Product(
                sku="SKU-NTF-001",
                branch_id=self.main_branch.id,
                name_th="Bolt Notify",
                name_en="Bolt Notify",
                category="Hardware",
                type="bolt",
                unit="pcs",
                cost_price=0,
                selling_price=None,
                stock_qty=0,
                min_stock=0,
                max_stock=0,
                status=StockStatus.NORMAL,
                supplier="Alpha Supplier",
                barcode="NTF-001",
                created_by=self.dev.id,
            )
            self.supplier = Supplier(
                branch_id=self.main_branch.id,
                code="SUP-NTF",
                name="Alpha Supplier",
                normalized_name="alpha supplier",
                is_verified=True,
                created_by=self.dev.id,
                updated_by=self.dev.id,
            )
            db.add_all([self.product, self.supplier])
            await db.flush()
            db.add(
                SupplierProductLink(
                    supplier_id=self.supplier.id,
                    product_id=self.product.id,
                    legacy_supplier_name=self.supplier.name,
                    is_primary=True,
                    linked_by_user_id=self.dev.id,
                )
            )
            await db.commit()

    async def _get_user(self, db: AsyncSession, user_id: str) -> User:
        user = await db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        return user

    async def _create_verification_request(self, db: AsyncSession, *, code: str = "VR-NTF-001") -> VerificationRequest:
        admin = await self._get_user(db, self.admin.id)
        return await create_verification_request(
            db,
            actor=admin,
            payload={
                "request_code": code,
                "subject_domain": "pricing",
                "queue_key": "dev-review",
                "risk_score": 80,
                "risk_level": "critical",
                "safety_status": "warning",
                "change_summary": "pricing update",
                "request_reason": "notify",
                "branch_id": self.main_branch.id,
                "items": [
                    {
                        "entity_type": "pricing",
                        "entity_id": "price-1",
                        "change_type": "update",
                        "handler_key": "pricing.handler",
                        "approval_strategy": "manual_follow_up",
                        "risk_level": "critical",
                        "safety_status": "warning",
                        "before_json": {"old": 1},
                        "proposed_after_json": {"new": 2},
                        "diff_summary": "pricing changed",
                    }
                ],
            },
            request=None,
        )

    async def _create_pending_verify_price(self, db: AsyncSession) -> PriceRecord:
        dev = await self._get_user(db, self.dev.id)
        return await create_price_record(
            db,
            actor=dev,
            request=None,
            payload={
                "product_id": self.product.id,
                "supplier_id": self.supplier.id,
                "branch_id": self.main_branch.id,
                "source_type": "manual_entry",
                "status": "pending_verify",
                "delivery_mode": "standard",
                "area_scope": "global",
                "price_dimension": "real_total_cost",
                "quantity_min": 1,
                "quantity_max": 9,
                "original_currency": "THB",
                "original_amount": "100",
                "exchange_rate": "1",
                "vat_percent": "7",
                "verification_required": True,
                "effective_at": datetime(2026, 4, 3, 9, 0),
            },
        )

    def test_event_publishing_from_verification_supplier_and_pricing_flows(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                request_record = await self._create_verification_request(db, code="VR-TRIGGER-001")
                owner = await self._get_user(db, self.owner.id)
                await assign_verification_request(
                    db,
                    request_id=request_record.id,
                    actor=owner,
                    assigned_to_user_id=self.dev.id,
                    assigned_role=Role.DEV.value,
                    reason="assign dev",
                    request=None,
                )
                proposal = await create_supplier_change_proposal(
                    db,
                    supplier=self.supplier,
                    action="update",
                    payload={"name": "Alpha Supplier Prime", "branch_id": self.main_branch.id},
                    actor_id=self.admin.id,
                )
                price_record = await self._create_pending_verify_price(db)
                await db.commit()

                event_types = set((await db.execute(select(NotificationEvent.event_type))).scalars().all())
                self.assertIn("verification.request_submitted", event_types)
                self.assertIn("verification.request_assigned", event_types)
                self.assertIn("supplier.verification_required", event_types)
                self.assertIn("pricing.verification_required", event_types)
                self.assertIsNotNone(proposal.id)
                self.assertIsNotNone(price_record.id)

        asyncio.run(_scenario())

    def test_dedupe_blocks_duplicate_events_and_outbox_duplicates_per_channel_recipient(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                event_one = await publish_notification_event(
                    db,
                    event_type="verification.request_submitted",
                    source_domain="verification",
                    source_entity_type="verification_request",
                    source_entity_id="req-1",
                    severity="low",
                    payload={"message": "hello"},
                    triggered_by_user_id=self.admin.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value, Role.DEV.value],
                    target_user_ids=[self.dev.id],
                    channels=[NotificationChannel.LINE, NotificationChannel.LINE, NotificationChannel.EMAIL],
                    dedupe_tokens=["same"],
                )
                event_two = await publish_notification_event(
                    db,
                    event_type="verification.request_submitted",
                    source_domain="verification",
                    source_entity_type="verification_request",
                    source_entity_id="req-1",
                    severity="low",
                    payload={"message": "hello"},
                    triggered_by_user_id=self.admin.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value],
                    target_user_ids=[self.dev.id],
                    channels=[NotificationChannel.LINE, NotificationChannel.EMAIL],
                    dedupe_tokens=["same"],
                )
                await db.commit()

                self.assertEqual(event_one.id, event_two.id)
                outboxes = (
                    await db.execute(select(NotificationOutbox).where(NotificationOutbox.event_id == event_one.id))
                ).scalars().all()
                self.assertEqual(len(outboxes), 2)
                self.assertEqual(
                    {(row.channel.value, row.recipient_user_id) for row in outboxes},
                    {("line", self.dev.id), ("email", self.dev.id)},
                )

        asyncio.run(_scenario())

    def test_claim_queue_skips_locked_rows_and_prevents_double_processing(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                await publish_notification_event(
                    db,
                    event_type="pricing.price_record_replaced",
                    source_domain="pricing",
                    source_entity_type="price_record",
                    source_entity_id="price-1",
                    severity="critical",
                    payload={"message": "critical pricing"},
                    triggered_by_user_id=self.dev.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value],
                    channels=[NotificationChannel.LINE],
                    dedupe_tokens=["claim"],
                )
                await db.commit()

                claimed_one = await claim_notification_outbox_batch(db, worker_token="worker-1", limit=10)
                self.assertEqual(len(claimed_one), 2)  # DEV + OWNER for critical
                claimed_two = await claim_notification_outbox_batch(db, worker_token="worker-2", limit=10)
                self.assertEqual(len(claimed_two), 0)

                locked_ids = {row.id for row in claimed_one}
                rows = (
                    await db.execute(select(NotificationOutbox).where(NotificationOutbox.id.in_(locked_ids)))
                ).scalars().all()
                self.assertTrue(all(row.status == NotificationOutboxStatus.PROCESSING for row in rows))

        asyncio.run(_scenario())

    def test_retry_and_failure_handling_cover_retryable_and_terminal_paths(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                retry_event = await publish_notification_event(
                    db,
                    event_type="verification.request_overdue",
                    source_domain="verification",
                    source_entity_type="verification_request",
                    source_entity_id="req-retry",
                    severity="high",
                    payload={"message": "retry me"},
                    triggered_by_user_id=self.admin.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value],
                    channels=[NotificationChannel.LINE],
                    dedupe_tokens=["retry"],
                )
                await db.commit()
                retry_outbox = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_id == retry_event.id))
                assert retry_outbox is not None
                retry_outbox.max_attempts = 2
                await db.commit()

                with patch("server.services.notifications.send_line_notify", return_value=False):
                    first_batch = await process_pending_notifications(db, worker_token="worker-retry-1", limit=10)
                    self.assertEqual(len(first_batch), 2)  # DEV + OWNER
                    refreshed = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.id == retry_outbox.id))
                    assert refreshed is not None
                    self.assertEqual(refreshed.attempt_count, 1)
                    self.assertEqual(refreshed.status, NotificationOutboxStatus.RETRY_SCHEDULED)
                    self.assertIsNotNone(refreshed.next_retry_at)

                    none_claimed = await claim_notification_outbox_batch(db, worker_token="worker-retry-2", now=datetime.utcnow(), limit=10)
                    self.assertEqual(len(none_claimed), 0)

                    future_now = refreshed.next_retry_at + timedelta(seconds=1)
                    claimed_again = await claim_notification_outbox_batch(db, worker_token="worker-retry-3", now=future_now, limit=10)
                    self.assertTrue(any(row.id == retry_outbox.id for row in claimed_again))
                    retry_row = next(row for row in claimed_again if row.id == retry_outbox.id)
                    await deliver_notification_outbox_item(db, outbox_id=retry_row.id, worker_token="worker-retry-3")

                final_retry_outbox = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.id == retry_row.id))
                assert final_retry_outbox is not None
                self.assertEqual(final_retry_outbox.status, NotificationOutboxStatus.FAILED)
                self.assertEqual(final_retry_outbox.attempt_count, 2)

                failure_rows = (
                    await db.execute(select(NotificationFailure).where(NotificationFailure.outbox_id == retry_outbox.id))
                ).scalars().all()
                self.assertEqual(len(failure_rows), 2)
                self.assertTrue(all(row.failure_type == NotificationFailureType.PROVIDER_ERROR for row in failure_rows))

                terminal_event = await publish_notification_event(
                    db,
                    event_type="verification.request_overdue",
                    source_domain="verification",
                    source_entity_type="verification_request",
                    source_entity_id="req-terminal",
                    severity="medium",
                    payload={"message": "discord only"},
                    triggered_by_user_id=self.admin.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value],
                    channels=[NotificationChannel.DISCORD],
                    dedupe_tokens=["terminal"],
                )
                await db.commit()

                await process_pending_notifications(db, worker_token="worker-terminal", limit=10)
                terminal_outbox = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_id == terminal_event.id))
                assert terminal_outbox is not None
                self.assertEqual(terminal_outbox.status, NotificationOutboxStatus.FAILED)
                self.assertEqual(terminal_outbox.attempt_count, 1)
                terminal_failure = await db.scalar(select(NotificationFailure).where(NotificationFailure.outbox_id == terminal_outbox.id))
                assert terminal_failure is not None
                self.assertEqual(terminal_failure.failure_type, NotificationFailureType.CONFIG_ERROR)
                self.assertFalse(terminal_failure.retryable)

        asyncio.run(_scenario())

    def test_delivery_success_and_idempotent_reprocessing_behavior(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                event = await publish_notification_event(
                    db,
                    event_type="verification.request_approved",
                    source_domain="verification",
                    source_entity_type="verification_request",
                    source_entity_id="req-success",
                    severity="low",
                    payload={"message": "email success"},
                    triggered_by_user_id=self.owner.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value],
                    channels=[NotificationChannel.EMAIL],
                    dedupe_tokens=["success"],
                )
                await db.commit()

                with patch("server.services.notifications._send_email_message", return_value="provider-123"):
                    processed = await process_pending_notifications(db, worker_token="worker-success", limit=10)
                self.assertEqual(len(processed), 1)
                outbox = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.event_id == event.id))
                assert outbox is not None
                self.assertEqual(outbox.status, NotificationOutboxStatus.SENT)

                deliveries = (
                    await db.execute(select(NotificationDelivery).where(NotificationDelivery.outbox_id == outbox.id))
                ).scalars().all()
                self.assertEqual(len(deliveries), 1)
                self.assertEqual(deliveries[0].delivery_status, NotificationDeliveryStatus.SENT)

                with patch("server.services.notifications._send_email_message", return_value="provider-456"):
                    processed_again = await process_pending_notifications(db, worker_token="worker-success-2", limit=10)
                self.assertEqual(processed_again, [])
                deliveries_after = (
                    await db.execute(select(NotificationDelivery).where(NotificationDelivery.outbox_id == outbox.id))
                ).scalars().all()
                self.assertEqual(len(deliveries_after), 1)

        asyncio.run(_scenario())

    def test_routing_honors_role_assignment_and_branch_scope(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                event = await publish_notification_event(
                    db,
                    event_type="verification.request_escalated",
                    source_domain="verification",
                    source_entity_type="verification_request",
                    source_entity_id="req-routing",
                    severity="critical",
                    payload={"message": "branch critical"},
                    triggered_by_user_id=self.owner.id,
                    branch_id=self.main_branch.id,
                    target_roles=[Role.DEV.value],
                    assignment_user_id=self.dev.id,
                    assignment_role=Role.DEV.value,
                    channels=[NotificationChannel.LINE],
                    dedupe_tokens=["routing"],
                )
                await db.commit()

                outboxes = (
                    await db.execute(select(NotificationOutbox).where(NotificationOutbox.event_id == event.id))
                ).scalars().all()
                self.assertEqual({row.recipient_user_id for row in outboxes}, {self.dev.id, self.owner.id})
                self.assertNotIn(self.dev_other.id, {row.recipient_user_id for row in outboxes})

        asyncio.run(_scenario())

    def test_business_transaction_rollback_removes_notification_side_effects_and_delivery_does_not_block_flow(self) -> None:
        async def _scenario() -> None:
            async with self.SessionLocal() as db:
                admin = await self._get_user(db, self.admin.id)
                try:
                    await create_verification_request(
                        db,
                        actor=admin,
                        payload={
                            "request_code": "VR-TX-ROLLBACK",
                            "subject_domain": "supplier",
                            "queue_key": "dev-review",
                            "risk_score": 80,
                            "risk_level": "critical",
                            "safety_status": "warning",
                            "change_summary": "rollback me",
                            "request_reason": "rollback",
                            "branch_id": self.main_branch.id,
                            "items": [
                                {
                                    "entity_type": "supplier",
                                    "entity_id": "supplier-1",
                                    "change_type": "update",
                                    "handler_key": "supplier.handler",
                                    "approval_strategy": "manual_follow_up",
                                    "risk_level": "critical",
                                    "safety_status": "warning",
                                    "before_json": {"old": 1},
                                    "proposed_after_json": {"new": 2},
                                    "diff_summary": "rollback supplier",
                                }
                            ],
                        },
                        request=None,
                    )
                    raise RuntimeError("force rollback")
                except RuntimeError:
                    await db.rollback()

            async with self.SessionLocal() as check_db:
                request_row = await check_db.scalar(
                    select(VerificationRequest).where(VerificationRequest.request_code == "VR-TX-ROLLBACK")
                )
                event_row = await check_db.scalar(
                    select(NotificationEvent).where(NotificationEvent.event_type == "verification.request_submitted")
                )
                self.assertIsNone(request_row)
                self.assertIsNone(event_row)

            async with self.SessionLocal() as db:
                request_record = await self._create_verification_request(db, code="VR-TX-SUCCESS")
                await db.commit()
                deliveries = (await db.execute(select(NotificationDelivery))).scalars().all()
                outboxes = (
                    await db.execute(select(NotificationOutbox).where(NotificationOutbox.event_id.is_not(None)))
                ).scalars().all()
                self.assertIsNotNone(request_record.id)
                self.assertEqual(deliveries, [])
                self.assertGreaterEqual(len(outboxes), 1)

        asyncio.run(_scenario())
