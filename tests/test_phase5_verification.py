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
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import server.services.verification as verification_service
from server.db.database import Base
from server.db.models import (
    AuditEvent,
    Branch,
    Role,
    User,
    VerificationAction,
    VerificationActionType,
    VerificationApprovalStrategy,
    VerificationAssignment,
    VerificationDependencyWarning,
    VerificationEscalation,
    VerificationRequest,
    VerificationRequestItem,
    VerificationRiskLevel,
    VerificationWorkflowStatus,
)
from server.services.security import hash_password
from server.services.verification import (
    approve_verification_request,
    assign_verification_request,
    cancel_verification_request,
    clear_verification_handlers,
    create_verification_request,
    escalate_verification_request,
    map_risk_score_to_level,
    mark_verification_request_overdue,
    register_verification_handler,
    reject_verification_request,
    return_verification_request_for_revision,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase5MigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_verification_tables(self) -> None:
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
                    "verification_requests",
                    "verification_request_items",
                    "verification_actions",
                    "verification_assignments",
                    "verification_dependency_warnings",
                    "verification_escalations",
                }.issubset(table_names)
            )

            cur.execute("PRAGMA table_info(verification_requests)")
            request_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue(
                {
                    "workflow_status",
                    "risk_level",
                    "risk_score",
                    "safety_status",
                    "item_count",
                    "dependency_warning_count",
                    "current_escalation_level",
                    "sla_deadline_at",
                }.issubset(request_columns)
            )

            cur.execute("PRAGMA table_info(verification_request_items)")
            item_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue(
                {
                    "entity_type",
                    "handler_key",
                    "approval_strategy",
                    "before_json",
                    "proposed_after_json",
                    "handler_payload_json",
                }.issubset(item_columns)
            )
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            if os.path.exists(db_path):
                os.unlink(db_path)


class Phase5VerificationUnitTests(unittest.TestCase):
    def test_risk_score_mapping_and_transition_guard(self) -> None:
        self.assertEqual(map_risk_score_to_level(0), VerificationRiskLevel.LOW)
        self.assertEqual(map_risk_score_to_level(24), VerificationRiskLevel.LOW)
        self.assertEqual(map_risk_score_to_level(25), VerificationRiskLevel.MEDIUM)
        self.assertEqual(map_risk_score_to_level(50), VerificationRiskLevel.HIGH)
        self.assertEqual(map_risk_score_to_level(75), VerificationRiskLevel.CRITICAL)

        with self.assertRaises(HTTPException) as invalid:
            map_risk_score_to_level(101)
        self.assertEqual(invalid.exception.detail, "verification_risk_score_out_of_range")

        verification_service._ensure_transition_allowed(
            VerificationWorkflowStatus.PENDING,
            VerificationWorkflowStatus.APPROVED,
        )
        with self.assertRaises(HTTPException) as invalid_transition:
            verification_service._ensure_transition_allowed(
                VerificationWorkflowStatus.APPROVED,
                VerificationWorkflowStatus.REJECTED,
            )
        self.assertEqual(invalid_transition.exception.detail, "verification_invalid_status_transition")


class Phase5VerificationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_verification_handlers()
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", future=True)
        self.SessionLocal = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        asyncio.run(self._init_db())

    def tearDown(self) -> None:
        clear_verification_handlers()
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
            stock = User(
                username="stock",
                display_name="Stock",
                role=Role.STOCK,
                is_active=True,
                language="th",
                password_hash=hash_password("Stock@1234"),
                totp_secret=None,
            )
            branch = Branch(
                code="MAIN",
                name="Main Branch",
                description="Main",
                is_default=True,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add_all([owner, dev, admin, stock, branch])
            await db.flush()
            self.owner_id = owner.id
            self.dev_id = dev.id
            self.admin_id = admin.id
            self.stock_id = stock.id
            self.branch_id = branch.id
            await db.commit()

    async def _get_user(self, db: AsyncSession, user_id: str) -> User:
        user = await db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        return user

    def _payload(
        self,
        *,
        approval_strategy: str = "manual_follow_up",
        safety_status: str = "safe",
        risk_score: int | None = 40,
        risk_level: str | None = None,
        dedupe_key: str | None = None,
        handler_key: str = "stub.handler",
        extra_items: list[dict] | None = None,
        dependency_warnings: list[dict] | None = None,
    ) -> dict:
        items = [
            {
                "entity_type": "supplier",
                "entity_id": "supplier-1",
                "change_type": "update",
                "handler_key": handler_key,
                "approval_strategy": approval_strategy,
                "risk_level": risk_level or verification_service.map_risk_score_to_level(risk_score or 0).value,
                "safety_status": safety_status,
                "before_json": {"name": "old"},
                "proposed_after_json": {"name": "new"},
                "handler_payload_json": {"field": "name"},
                "diff_summary": "supplier name update",
            }
        ]
        if extra_items:
            items.extend(extra_items)
        return {
            "subject_domain": "supplier",
            "queue_key": "supplier",
            "risk_score": risk_score,
            "risk_level": risk_level or verification_service.map_risk_score_to_level(risk_score or 0).value,
            "safety_status": safety_status,
            "change_summary": "supplier change summary",
            "request_reason": "need verification",
            "branch_id": self.branch_id,
            "items": items,
            "dedupe_key": dedupe_key,
            "dependency_warnings": dependency_warnings or [],
        }

    async def _create_request(self, db: AsyncSession, *, actor_id: str, payload: dict | None = None) -> VerificationRequest:
        actor = await self._get_user(db, actor_id)
        return await create_verification_request(db, actor=actor, payload=payload or self._payload())

    def test_request_creation_and_invalid_request_without_items(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                request_record = await create_verification_request(db, actor=owner, payload=self._payload())
                await db.commit()
                self.assertEqual(request_record.workflow_status, VerificationWorkflowStatus.PENDING)
                self.assertEqual(request_record.item_count, 1)

                items = (await db.execute(select(VerificationRequestItem).where(VerificationRequestItem.request_id == request_record.id))).scalars().all()
                self.assertEqual(len(items), 1)

                actions = (await db.execute(select(VerificationAction).where(VerificationAction.request_id == request_record.id))).scalars().all()
                self.assertEqual(len(actions), 1)
                self.assertEqual(actions[0].action_type, VerificationActionType.SUBMIT)

                with self.assertRaises(HTTPException) as no_items:
                    await create_verification_request(
                        db,
                        actor=owner,
                        payload={
                            "subject_domain": "supplier",
                            "queue_key": "supplier",
                            "risk_score": 25,
                            "risk_level": "medium",
                            "safety_status": "safe",
                            "change_summary": "x",
                            "request_reason": "x",
                            "branch_id": self.branch_id,
                            "items": [],
                        },
                    )
                self.assertEqual(no_items.exception.detail, "verification_items_required")

        asyncio.run(scenario())

    def test_workflow_transitions_and_invalid_terminal_transition(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                dev = await self._get_user(db, self.dev_id)

                approved = await self._create_request(db, actor_id=self.owner_id)
                approved_id = approved.id
                await db.commit()
                await approve_verification_request(db, request_id=approved_id, actor=dev, reason="approve")
                await db.commit()
                approved = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == approved_id))
                assert approved is not None
                self.assertEqual(approved.workflow_status, VerificationWorkflowStatus.APPROVED)

                with self.assertRaises(HTTPException) as invalid:
                    await reject_verification_request(db, request_id=approved_id, actor=owner, reason="too late")
                self.assertEqual(invalid.exception.detail, "verification_invalid_status_transition")

                rejected = await self._create_request(db, actor_id=self.owner_id)
                returned = await self._create_request(db, actor_id=self.owner_id)
                cancelled = await self._create_request(db, actor_id=self.owner_id)
                rejected_id = rejected.id
                returned_id = returned.id
                cancelled_id = cancelled.id
                await db.commit()

                await reject_verification_request(db, request_id=rejected_id, actor=dev, reason="reject")
                await return_verification_request_for_revision(db, request_id=returned_id, actor=owner, reason="revise")
                await cancel_verification_request(db, request_id=cancelled_id, actor=owner, reason="cancel")
                await db.commit()

                rejected = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == rejected_id))
                returned = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == returned_id))
                cancelled = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == cancelled_id))
                assert rejected is not None and returned is not None and cancelled is not None
                self.assertEqual(rejected.workflow_status, VerificationWorkflowStatus.REJECTED)
                self.assertEqual(returned.workflow_status, VerificationWorkflowStatus.RETURNED_FOR_REVISION)
                self.assertEqual(cancelled.workflow_status, VerificationWorkflowStatus.CANCELLED)

        asyncio.run(scenario())

    def test_permission_rules_for_submit_and_verify(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                admin = await self._get_user(db, self.admin_id)
                stock = await self._get_user(db, self.stock_id)
                dev = await self._get_user(db, self.dev_id)

                request_record = await create_verification_request(db, actor=admin, payload=self._payload())
                request_id = request_record.id
                await db.commit()
                admin = await self._get_user(db, self.admin_id)
                self.assertEqual(request_record.workflow_status, VerificationWorkflowStatus.PENDING)

                with self.assertRaises(HTTPException) as stock_submit:
                    await create_verification_request(db, actor=stock, payload=self._payload())
                self.assertEqual(stock_submit.exception.detail, "verification_submit_permission_denied")

                with self.assertRaises(HTTPException) as admin_verify:
                    await approve_verification_request(db, request_id=request_id, actor=admin, reason="approve")
                self.assertEqual(admin_verify.exception.detail, "verification_permission_denied")

                owner_request = await self._create_request(db, actor_id=self.owner_id)
                dev_request = await self._create_request(db, actor_id=self.owner_id)
                owner_request_id = owner_request.id
                dev_request_id = dev_request.id
                await db.commit()
                owner = await self._get_user(db, self.owner_id)
                dev = await self._get_user(db, self.dev_id)

                await approve_verification_request(db, request_id=owner_request_id, actor=owner, reason="owner approve")
                await approve_verification_request(db, request_id=dev_request_id, actor=dev, reason="dev approve")
                await db.commit()
                owner_request = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == owner_request_id))
                dev_request = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == dev_request_id))
                assert owner_request is not None and dev_request is not None
                self.assertEqual(owner_request.workflow_status, VerificationWorkflowStatus.APPROVED)
                self.assertEqual(dev_request.workflow_status, VerificationWorkflowStatus.APPROVED)

        asyncio.run(scenario())

    def test_risk_validation_valid_invalid_and_mismatch(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                for score in (0, 24, 25, 49, 50, 74, 75, 100):
                    owner = await self._get_user(db, self.owner_id)
                    request_record = await create_verification_request(db, actor=owner, payload=self._payload(risk_score=score))
                    await db.flush()
                    self.assertEqual(request_record.risk_level, verification_service.map_risk_score_to_level(score))
                    await db.rollback()

                owner = await self._get_user(db, self.owner_id)
                with self.assertRaises(HTTPException) as invalid_score:
                    await create_verification_request(db, actor=owner, payload=self._payload(risk_score=101, risk_level="critical"))
                self.assertEqual(invalid_score.exception.detail, "verification_risk_score_out_of_range")

                owner = await self._get_user(db, self.owner_id)
                with self.assertRaises(HTTPException) as mismatch:
                    await create_verification_request(db, actor=owner, payload=self._payload(risk_score=80, risk_level="low"))
                self.assertEqual(mismatch.exception.detail, "verification_risk_level_score_mismatch")

        asyncio.run(scenario())

    def test_assignment_and_reassignment_keep_only_one_active_assignment(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                dev = await self._get_user(db, self.dev_id)
                request_record = await self._create_request(db, actor_id=self.owner_id)
                request_id = request_record.id
                await db.commit()

                await assign_verification_request(
                    db,
                    request_id=request_id,
                    actor=owner,
                    assigned_to_user_id=dev.id,
                    assigned_role=Role.DEV.value,
                    reason="assign dev",
                )
                await db.commit()

                await assign_verification_request(
                    db,
                    request_id=request_id,
                    actor=owner,
                    assigned_to_user_id=owner.id,
                    assigned_role=Role.OWNER.value,
                    reason="reassign owner",
                )
                await db.commit()

                assignments = (
                    await db.execute(
                        select(VerificationAssignment)
                        .where(VerificationAssignment.request_id == request_id)
                        .order_by(VerificationAssignment.started_at.asc())
                    )
                ).scalars().all()
                self.assertEqual(len(assignments), 2)
                self.assertFalse(assignments[0].is_current)
                self.assertIsNotNone(assignments[0].ended_at)
                self.assertTrue(assignments[1].is_current)
                self.assertEqual(request_record.assignee_user_id, owner.id)

        asyncio.run(scenario())

    def test_overdue_and_escalation_behaviors(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                request_record = await self._create_request(
                    db,
                    actor_id=self.owner_id,
                    payload={
                        **self._payload(),
                        "sla_deadline_at": datetime.utcnow() - timedelta(hours=3),
                    },
                )
                request_id = request_record.id
                await db.commit()

                await mark_verification_request_overdue(db, request_id=request_id)
                await db.commit()
                request_record = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert request_record is not None
                self.assertIsNotNone(request_record.first_overdue_at)

                await escalate_verification_request(
                    db,
                    request_id=request_id,
                    actor=owner,
                    reason="manual escalate",
                    target_role=Role.DEV.value,
                    new_assignee_user_id=self.dev_id,
                )
                await db.commit()
                request_record = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert request_record is not None
                self.assertEqual(request_record.current_escalation_level, 1)
                self.assertEqual(request_record.assignee_user_id, self.dev_id)

                escalations = (await db.execute(select(VerificationEscalation).where(VerificationEscalation.request_id == request_id))).scalars().all()
                self.assertEqual(len(escalations), 1)
                self.assertEqual(escalations[0].escalation_level, 1)

        asyncio.run(scenario())

    def test_dependency_safety_blocked_rejected_and_warning_can_approve(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                dev = await self._get_user(db, self.dev_id)

                blocked_request = await create_verification_request(
                    db,
                    actor=owner,
                    payload=self._payload(
                        safety_status="blocked",
                        dependency_warnings=[
                            {
                                "dependency_type": "pricing",
                                "message": "blocked dependency",
                                "safety_status": "blocked",
                            }
                        ],
                    ),
                )
                warning_request = await create_verification_request(
                    db,
                    actor=owner,
                    payload=self._payload(
                        safety_status="warning",
                        dependency_warnings=[
                            {
                                "dependency_type": "pricing",
                                "message": "warning dependency",
                                "safety_status": "warning",
                            }
                        ],
                    ),
                )
                blocked_id = blocked_request.id
                warning_id = warning_request.id
                await db.commit()
                dev = await self._get_user(db, self.dev_id)

                with self.assertRaises(HTTPException) as blocked:
                    await approve_verification_request(db, request_id=blocked_id, actor=dev, reason="blocked")
                self.assertEqual(blocked.exception.detail, "verification_request_blocked")

                await approve_verification_request(db, request_id=warning_id, actor=dev, reason="warning ok")
                await db.commit()
                warning_request = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == warning_id))
                assert warning_request is not None
                self.assertEqual(warning_request.workflow_status, VerificationWorkflowStatus.APPROVED)

        asyncio.run(scenario())

    def test_transactional_approval_rolls_back_on_handler_failure(self) -> None:
        async def first_handler(*, db: AsyncSession, item: VerificationRequestItem, **_: object) -> dict:
            item.diff_summary = "first-applied"
            await db.flush()
            return {"applied": item.id}

        async def failing_handler(*, db: AsyncSession, item: VerificationRequestItem, **_: object) -> dict:
            item.diff_summary = "second-applied"
            await db.flush()
            raise HTTPException(status_code=409, detail="verification_handler_failed")

        async def scenario() -> None:
            register_verification_handler("handler.first", first_handler)
            register_verification_handler("handler.fail", failing_handler)
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                dev = await self._get_user(db, self.dev_id)
                payload = self._payload(
                    approval_strategy="domain_handler",
                    handler_key="handler.first",
                    extra_items=[
                        {
                            "entity_type": "pricing",
                            "entity_id": "price-1",
                            "change_type": "replace",
                            "handler_key": "handler.fail",
                            "approval_strategy": "domain_handler",
                            "risk_level": "high",
                            "safety_status": "safe",
                            "before_json": {"amount": 10},
                            "proposed_after_json": {"amount": 20},
                            "handler_payload_json": {"field": "amount"},
                            "diff_summary": "replace price",
                        }
                    ],
                )
                request_record = await create_verification_request(db, actor=owner, payload=payload)
                request_id = request_record.id
                await db.commit()
                original_item_values = {
                    item.id: item.diff_summary
                    for item in (await db.execute(select(VerificationRequestItem).where(VerificationRequestItem.request_id == request_id))).scalars().all()
                }

                with self.assertRaises(HTTPException) as handler_failed:
                    await approve_verification_request(db, request_id=request_id, actor=dev, reason="apply")
                self.assertEqual(handler_failed.exception.detail, "verification_handler_failed")
                await db.rollback()

            async with self.SessionLocal() as verify_db:
                refreshed_request = await verify_db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert refreshed_request is not None
                self.assertEqual(refreshed_request.workflow_status, VerificationWorkflowStatus.PENDING)
                items = (
                    await verify_db.execute(
                        select(VerificationRequestItem).where(VerificationRequestItem.request_id == request_id)
                    )
                ).scalars().all()
                self.assertEqual({item.id: item.diff_summary for item in items}, original_item_values)
                approve_actions = (
                    await verify_db.execute(
                        select(VerificationAction).where(
                            VerificationAction.request_id == request_id,
                            VerificationAction.action_type == VerificationActionType.APPROVE,
                        )
                    )
                ).scalars().all()
                self.assertEqual(len(approve_actions), 0)

        asyncio.run(scenario())

    def test_dedupe_and_audit_trail(self) -> None:
        async def scenario() -> None:
            async with self.SessionLocal() as db:
                owner = await self._get_user(db, self.owner_id)
                dev = await self._get_user(db, self.dev_id)
                request_record = await create_verification_request(
                    db,
                    actor=owner,
                    payload=self._payload(dedupe_key="supplier:1:update"),
                )
                request_id = request_record.id
                await db.commit()
                dev = await self._get_user(db, self.dev_id)

                with self.assertRaises(HTTPException) as duplicate:
                    await create_verification_request(
                        db,
                        actor=owner,
                        payload=self._payload(dedupe_key="supplier:1:update"),
                    )
                self.assertEqual(duplicate.exception.detail, "verification_pending_dedupe_conflict")

                await assign_verification_request(
                    db,
                    request_id=request_id,
                    actor=owner,
                    assigned_to_user_id=dev.id,
                    assigned_role=Role.DEV.value,
                    reason="assign dev",
                )
                await approve_verification_request(db, request_id=request_id, actor=dev, reason="approve")
                await db.commit()

                actions = (
                    await db.execute(
                        select(VerificationAction)
                        .where(VerificationAction.request_id == request_id)
                        .order_by(VerificationAction.created_at.asc())
                    )
                ).scalars().all()
                self.assertEqual(
                    [action.action_type for action in actions],
                    [VerificationActionType.SUBMIT, VerificationActionType.ASSIGN, VerificationActionType.APPROVE],
                )

                audit_events = (
                    await db.execute(
                        select(AuditEvent)
                        .where(AuditEvent.entity == "verification_request", AuditEvent.entity_id == request_id)
                        .order_by(AuditEvent.created_at.asc())
                    )
                ).scalars().all()
                self.assertGreaterEqual(len(audit_events), 3)
                self.assertEqual(audit_events[-1].action, "VERIFICATION_REQUEST_APPROVED")
                request_record = await db.scalar(select(VerificationRequest).where(VerificationRequest.id == request_id))
                assert request_record is not None
                self.assertEqual(request_record.workflow_status, VerificationWorkflowStatus.APPROVED)

        asyncio.run(scenario())
