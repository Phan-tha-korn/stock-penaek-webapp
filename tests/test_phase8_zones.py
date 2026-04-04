from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.database import Base, get_db
from server.db.models import (
    AreaScope,
    AuditEvent,
    AuditSeverity,
    Branch,
    CanonicalGroupLockState,
    CanonicalGroupMember,
    CanonicalProductGroup,
    CatalogSearchDocument,
    CurrencyCode,
    MatchingDependencyCheck,
    MatchingDependencyStatus,
    MatchingDependencyType,
    MatchingGroupStatus,
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
    Role,
    StockStatus,
    Supplier,
    User,
    UserBranchScope,
    VerificationQueueProjection,
    VerificationRequest,
    VerificationRiskLevel,
    VerificationSafetyStatus,
    VerificationWorkflowStatus,
)
import server.main as main_module
from server.main import fastapi_app
from server.services.security import hash_password


class Phase8ZoneApiTests(unittest.TestCase):
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
            now = datetime.utcnow()
            self.main_branch = Branch(code="MAIN", name="Main", description="Main", is_default=True, is_active=True)
            self.other_branch = Branch(code="OTHER", name="Other", description="Other", is_default=False, is_active=True)
            db.add_all([self.main_branch, self.other_branch])
            await db.flush()

            self.owner = User(username="owner", display_name="Owner", role=Role.OWNER, is_active=True, language="th", password_hash=hash_password("Owner@1234"), totp_secret=None)
            self.dev = User(username="dev", display_name="Dev", role=Role.DEV, is_active=True, language="en", password_hash=hash_password("Dev@1234"), totp_secret=None)
            self.admin = User(username="admin", display_name="Admin", role=Role.ADMIN, is_active=True, language="th", password_hash=hash_password("Admin@1234"), totp_secret=None)
            self.stock = User(username="stock", display_name="Stock", role=Role.STOCK, is_active=True, language="th", password_hash=hash_password("Stock@1234"), totp_secret=None)
            self.dev_other = User(username="dev_other", display_name="Dev Other", role=Role.DEV, is_active=True, language="th", password_hash=hash_password("Dev@1234"), totp_secret=None)
            db.add_all([self.owner, self.dev, self.admin, self.stock, self.dev_other])
            await db.flush()
            db.add(UserBranchScope(user_id=self.dev_other.id, branch_id=self.other_branch.id, can_view=True, can_edit=False, scope_source="test"))

            self.main_product = Product(sku="SKU-MAIN-001", branch_id=self.main_branch.id, name_th="Main One", name_en="Main One", category="Hardware", type="bolt", unit="pcs", cost_price=10, selling_price=15, stock_qty=20, min_stock=5, max_stock=50, status=StockStatus.NORMAL, supplier="Alpha", barcode="MAIN-001", created_by=self.owner.id)
            self.group_product = Product(sku="SKU-MAIN-002", branch_id=self.main_branch.id, name_th="Main Two", name_en="Main Two", category="Hardware", type="bolt", unit="pcs", cost_price=11, selling_price=16, stock_qty=10, min_stock=2, max_stock=20, status=StockStatus.NORMAL, supplier="Alpha", barcode="MAIN-002", created_by=self.owner.id)
            self.other_product = Product(sku="SKU-OTHER-001", branch_id=self.other_branch.id, name_th="Other One", name_en="Other One", category="Hardware", type="bolt", unit="pcs", cost_price=12, selling_price=18, stock_qty=9, min_stock=2, max_stock=20, status=StockStatus.NORMAL, supplier="Beta", barcode="OTHER-001", created_by=self.owner.id)
            db.add_all([self.main_product, self.group_product, self.other_product])
            await db.flush()

            self.main_supplier = Supplier(branch_id=self.main_branch.id, code="SUP-MAIN", name="Alpha Supplier", normalized_name="alpha supplier", is_verified=True, created_by=self.owner.id, updated_by=self.owner.id)
            self.other_supplier = Supplier(branch_id=self.other_branch.id, code="SUP-OTHER", name="Beta Supplier", normalized_name="beta supplier", is_verified=True, created_by=self.owner.id, updated_by=self.owner.id)
            db.add_all([self.main_supplier, self.other_supplier])
            await db.flush()

            self.group = CanonicalProductGroup(code="GROUP-001", display_name="Bolt Group", system_name="bolt_group", status=MatchingGroupStatus.ACTIVE, lock_state=CanonicalGroupLockState.EDITABLE, version_no=1, created_by=self.owner.id)
            db.add(self.group)
            await db.flush()
            db.add_all([
                CanonicalGroupMember(group_id=self.group.id, product_id=self.main_product.id, is_primary=True, assigned_by=self.owner.id, created_by=self.owner.id),
                CanonicalGroupMember(group_id=self.group.id, product_id=self.group_product.id, is_primary=False, assigned_by=self.owner.id, created_by=self.owner.id),
            ])

            self.main_price_old = PriceRecord(product_id=self.main_product.id, supplier_id=self.main_supplier.id, branch_id=self.main_branch.id, source_type=PriceSourceType.MANUAL_ENTRY, status=PriceRecordStatus.ACTIVE, delivery_mode="standard", area_scope=AreaScope.GLOBAL.value, price_dimension=PriceDimension.REAL_TOTAL_COST.value, quantity_min=1, quantity_max=9, original_currency=CurrencyCode.THB, original_amount=120, normalized_currency=CurrencyCode.THB, normalized_amount=120, exchange_rate=1, exchange_rate_snapshot_at=now - timedelta(days=2), base_price=120, vat_percent=7, vat_amount=8.4, final_total_cost=128.4, effective_at=now - timedelta(days=2), created_by=self.owner.id)
            self.main_price_new = PriceRecord(product_id=self.main_product.id, supplier_id=self.main_supplier.id, branch_id=self.main_branch.id, source_type=PriceSourceType.MANUAL_ENTRY, status=PriceRecordStatus.ACTIVE, delivery_mode="standard", area_scope=AreaScope.GLOBAL.value, price_dimension=PriceDimension.REAL_TOTAL_COST.value, quantity_min=1, quantity_max=9, original_currency=CurrencyCode.THB, original_amount=110, normalized_currency=CurrencyCode.THB, normalized_amount=110, exchange_rate=1, exchange_rate_snapshot_at=now - timedelta(days=1), base_price=110, vat_percent=7, vat_amount=7.7, final_total_cost=117.7, effective_at=now - timedelta(days=1), created_by=self.owner.id)
            self.group_price = PriceRecord(product_id=self.group_product.id, supplier_id=self.main_supplier.id, branch_id=self.main_branch.id, source_type=PriceSourceType.MANUAL_ENTRY, status=PriceRecordStatus.ACTIVE, delivery_mode="standard", area_scope=AreaScope.GLOBAL.value, price_dimension=PriceDimension.REAL_TOTAL_COST.value, quantity_min=1, quantity_max=9, original_currency=CurrencyCode.THB, original_amount=105, normalized_currency=CurrencyCode.THB, normalized_amount=105, exchange_rate=1, exchange_rate_snapshot_at=now - timedelta(hours=12), base_price=105, vat_percent=7, vat_amount=7.35, final_total_cost=112.35, effective_at=now - timedelta(hours=12), created_by=self.owner.id)
            db.add_all([self.main_price_old, self.main_price_new, self.group_price])
            await db.flush()

            db.add_all(
                [
                    CatalogSearchDocument(product_id=self.main_product.id, branch_id=self.main_branch.id, canonical_group_id=self.group.id, canonical_group_name=self.group.display_name, sku=self.main_product.sku, name_th=self.main_product.name_th, name_en=self.main_product.name_en, category_text=self.main_product.category, alias_text="bolt fastener", tag_text="hardware,main", supplier_text="alpha supplier", search_text="sku-main-001 bolt fastener main one", lifecycle_status="active", active_price_count=2, verified_supplier_count=1, latest_effective_at=now - timedelta(days=1), latest_price_record_id=self.main_price_new.id, latest_normalized_amount_thb=110, latest_final_total_cost_thb=117.7, cheapest_active_price_record_id=self.main_price_new.id, cheapest_active_normalized_amount_thb=110, cheapest_active_final_total_cost_thb=117.7),
                    CatalogSearchDocument(product_id=self.other_product.id, branch_id=self.other_branch.id, canonical_group_id=None, canonical_group_name="", sku=self.other_product.sku, name_th=self.other_product.name_th, name_en=self.other_product.name_en, category_text=self.other_product.category, alias_text="other", tag_text="hardware,other", supplier_text="beta supplier", search_text="sku-other-001 other one", lifecycle_status="active", active_price_count=0, verified_supplier_count=1),
                    PriceSearchProjection(price_record_id=self.main_price_old.id, product_id=self.main_product.id, branch_id=self.main_branch.id, supplier_id=self.main_supplier.id, canonical_group_id=self.group.id, canonical_group_name=self.group.display_name, sku=self.main_product.sku, product_name_th=self.main_product.name_th, product_name_en=self.main_product.name_en, category_text=self.main_product.category, supplier_name=self.main_supplier.name, supplier_is_verified=True, status=PriceRecordStatus.ACTIVE, source_type=PriceSourceType.MANUAL_ENTRY, delivery_mode="standard", area_scope=AreaScope.GLOBAL.value, price_dimension=PriceDimension.REAL_TOTAL_COST.value, quantity_min=1, quantity_max=9, original_currency=CurrencyCode.THB, normalized_currency=CurrencyCode.THB, normalized_amount_thb=120, vat_amount_thb=8.4, final_total_cost_thb=128.4, effective_at=now - timedelta(days=2), updated_at=now - timedelta(days=2)),
                    PriceSearchProjection(price_record_id=self.main_price_new.id, product_id=self.main_product.id, branch_id=self.main_branch.id, supplier_id=self.main_supplier.id, canonical_group_id=self.group.id, canonical_group_name=self.group.display_name, sku=self.main_product.sku, product_name_th=self.main_product.name_th, product_name_en=self.main_product.name_en, category_text=self.main_product.category, supplier_name=self.main_supplier.name, supplier_is_verified=True, status=PriceRecordStatus.ACTIVE, source_type=PriceSourceType.MANUAL_ENTRY, delivery_mode="standard", area_scope=AreaScope.GLOBAL.value, price_dimension=PriceDimension.REAL_TOTAL_COST.value, quantity_min=1, quantity_max=9, original_currency=CurrencyCode.THB, normalized_currency=CurrencyCode.THB, normalized_amount_thb=110, vat_amount_thb=7.7, final_total_cost_thb=117.7, effective_at=now - timedelta(days=1), updated_at=now - timedelta(days=1)),
                    PriceSearchProjection(price_record_id=self.group_price.id, product_id=self.group_product.id, branch_id=self.main_branch.id, supplier_id=self.main_supplier.id, canonical_group_id=self.group.id, canonical_group_name=self.group.display_name, sku=self.group_product.sku, product_name_th=self.group_product.name_th, product_name_en=self.group_product.name_en, category_text=self.group_product.category, supplier_name=self.main_supplier.name, supplier_is_verified=True, status=PriceRecordStatus.ACTIVE, source_type=PriceSourceType.MANUAL_ENTRY, delivery_mode="standard", area_scope=AreaScope.GLOBAL.value, price_dimension=PriceDimension.REAL_TOTAL_COST.value, quantity_min=1, quantity_max=9, original_currency=CurrencyCode.THB, normalized_currency=CurrencyCode.THB, normalized_amount_thb=105, vat_amount_thb=7.35, final_total_cost_thb=112.35, effective_at=now - timedelta(hours=12), updated_at=now - timedelta(hours=12)),
                ]
            )

            self.main_request = VerificationRequest(request_code="VR-MAIN-001", workflow_status=VerificationWorkflowStatus.PENDING, risk_level=VerificationRiskLevel.CRITICAL, risk_score=80, subject_domain="pricing", queue_key="dev-review", safety_status=VerificationSafetyStatus.WARNING, change_summary="main queue", request_reason="seed", branch_id=self.main_branch.id, requested_by_user_id=self.admin.id, submitted_by_user_id=self.admin.id, assignee_user_id=self.dev.id, sla_deadline_at=now - timedelta(hours=1), last_action_at=now)
            self.other_request = VerificationRequest(request_code="VR-OTHER-001", workflow_status=VerificationWorkflowStatus.PENDING, risk_level=VerificationRiskLevel.MEDIUM, risk_score=40, subject_domain="supplier", queue_key="admin-review", safety_status=VerificationSafetyStatus.SAFE, change_summary="other queue", request_reason="seed", branch_id=self.other_branch.id, requested_by_user_id=self.admin.id, submitted_by_user_id=self.admin.id, assignee_user_id=self.dev_other.id, sla_deadline_at=now + timedelta(hours=1), last_action_at=now - timedelta(minutes=5))
            db.add_all([self.main_request, self.other_request])
            await db.flush()

            db.add_all(
                [
                    VerificationQueueProjection(request_id=self.main_request.id, request_code=self.main_request.request_code, branch_id=self.main_branch.id, workflow_status=VerificationWorkflowStatus.PENDING, risk_level=VerificationRiskLevel.CRITICAL, risk_score=80, subject_domain="pricing", queue_key="dev-review", safety_status=VerificationSafetyStatus.WARNING, assignee_user_id=self.dev.id, assignee_role=Role.DEV.value, requested_by_user_id=self.admin.id, item_count=1, dependency_warning_count=1, current_escalation_level=1, has_blocking_dependency=True, is_overdue=True, primary_entity_type="pricing", primary_entity_id=self.main_price_new.id, latest_action_type="submit", latest_action_at=now, sla_deadline_at=now - timedelta(hours=1), created_at=now - timedelta(hours=3), search_text="vr-main-001 pricing"),
                    VerificationQueueProjection(request_id=self.other_request.id, request_code=self.other_request.request_code, branch_id=self.other_branch.id, workflow_status=VerificationWorkflowStatus.PENDING, risk_level=VerificationRiskLevel.MEDIUM, risk_score=40, subject_domain="supplier", queue_key="admin-review", safety_status=VerificationSafetyStatus.SAFE, assignee_user_id=self.dev_other.id, assignee_role=Role.DEV.value, requested_by_user_id=self.admin.id, item_count=1, dependency_warning_count=0, current_escalation_level=0, has_blocking_dependency=False, is_overdue=False, primary_entity_type="supplier", primary_entity_id=self.main_supplier.id, latest_action_type="submit", latest_action_at=now - timedelta(minutes=5), sla_deadline_at=now + timedelta(hours=1), created_at=now - timedelta(hours=1), search_text="vr-other-001 supplier"),
                ]
            )

            self.main_event = NotificationEvent(event_type="verification.request_overdue", notification_type=NotificationType.IMMEDIATE, source_domain="verification", source_entity_type="verification_request", source_entity_id=self.main_request.id, branch_id=self.main_branch.id, severity=NotificationSeverity.CRITICAL, priority=100, status=NotificationEventStatus.PENDING, payload_json={"message": "overdue"}, dedupe_key="evt-main", triggered_by_user_id=self.owner.id, related_request_id=self.main_request.id, occurred_at=now)
            self.other_event = NotificationEvent(event_type="supplier.verification_required", notification_type=NotificationType.IMMEDIATE, source_domain="supplier", source_entity_type="supplier_change_proposal", source_entity_id="proposal-other", branch_id=self.other_branch.id, severity=NotificationSeverity.MEDIUM, priority=50, status=NotificationEventStatus.PENDING, payload_json={"message": "supplier"}, dedupe_key="evt-other", triggered_by_user_id=self.admin.id, occurred_at=now - timedelta(minutes=10))
            self.pricing_event = NotificationEvent(event_type="pricing.record_replaced", notification_type=NotificationType.IMMEDIATE, source_domain="pricing", source_entity_type="price_record", source_entity_id=self.main_price_new.id, branch_id=self.main_branch.id, severity=NotificationSeverity.CRITICAL, priority=100, status=NotificationEventStatus.PENDING, payload_json={"product_id": self.main_product.id, "message": "pricing"}, dedupe_key="evt-pricing", triggered_by_user_id=self.owner.id, occurred_at=now - timedelta(minutes=2))
            db.add_all([self.main_event, self.other_event, self.pricing_event])
            await db.flush()

            db.add_all(
                [
                    NotificationOutbox(event_id=self.main_event.id, channel=NotificationChannel.LINE, assignment_mode=NotificationAssignmentMode.USER, recipient_user_id=self.dev.id, routing_role=Role.DEV.value, branch_id=self.main_branch.id, severity=NotificationSeverity.CRITICAL, priority=100, status=NotificationOutboxStatus.RETRY_SCHEDULED, message_title="Overdue verification", message_body="Check queue", payload_json={}, dedupe_key="out-main-dev"),
                    NotificationOutbox(event_id=self.other_event.id, channel=NotificationChannel.EMAIL, assignment_mode=NotificationAssignmentMode.USER, recipient_user_id=self.dev_other.id, recipient_address="other@example.com", routing_role=Role.DEV.value, branch_id=self.other_branch.id, severity=NotificationSeverity.MEDIUM, priority=50, status=NotificationOutboxStatus.FAILED, message_title="Supplier review", message_body="Open supplier", payload_json={}, dedupe_key="out-other-dev"),
                    NotificationOutbox(event_id=self.pricing_event.id, channel=NotificationChannel.LINE, assignment_mode=NotificationAssignmentMode.USER, recipient_user_id=self.owner.id, routing_role=Role.OWNER.value, branch_id=self.main_branch.id, severity=NotificationSeverity.CRITICAL, priority=100, status=NotificationOutboxStatus.PENDING, message_title="Critical pricing change", message_body="Open compare", payload_json={}, dedupe_key="out-pricing-owner"),
                ]
            )

            for idx in range(8):
                db.add(AuditEvent(actor_user_id=self.owner.id, actor_username=self.owner.username, actor_role=Role.OWNER, branch_id=self.main_branch.id if idx < 7 else self.other_branch.id, action=f"CRITICAL_{idx}", entity="pricing", entity_id=self.main_price_new.id, severity=AuditSeverity.CRITICAL, reason="seed", diff_summary=f"change-{idx}", success=True, created_at=now - timedelta(minutes=idx)))

            db.add(MatchingDependencyCheck(operation_id="matching-op-seed", dependency_type=MatchingDependencyType.PRICING, check_status=MatchingDependencyStatus.WARNING, affected_entity_count=2, detail_json={"warning": True}, created_at=now))
            await db.commit()

    def _login(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post("/api/auth/login", json={"username": username, "password": password, "secret_phrase": ""})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_default_landing_and_zone_access_rules(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")
        dev_headers = self._login("dev", "Dev@1234")
        admin_headers = self._login("admin", "Admin@1234")
        stock_headers = self._login("stock", "Stock@1234")

        self.assertEqual(self.client.get("/api/zones/landing", headers=owner_headers).json()["landing_path"], "/zones/owner")
        self.assertEqual(self.client.get("/api/zones/landing", headers=dev_headers).json()["landing_path"], "/zones/dev")
        self.assertEqual(self.client.get("/api/zones/landing", headers=admin_headers).json()["landing_path"], "/zones/admin")
        self.assertEqual(self.client.get("/api/zones/landing", headers=stock_headers).json()["landing_path"], "/zones/stock/search")

        self.assertEqual(self.client.get("/api/zones/owner/summary", headers=owner_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/zones/owner/summary", headers=dev_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/zones/dev/summary", headers=dev_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/zones/admin/summary", headers=admin_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/zones/verification/queue", headers=stock_headers).status_code, 403)

    def test_deep_link_queries_load_expected_context_and_handle_invalid_params_safely(self) -> None:
        headers = self._login("owner", "Owner@1234")

        verification = self.client.get("/api/zones/verification/queue", params={"q": "VR-MAIN-001"}, headers=headers)
        self.assertEqual(verification.status_code, 200, verification.text)
        self.assertEqual(len(verification.json()["items"]), 1)
        self.assertEqual(verification.json()["items"][0]["request_code"], "VR-MAIN-001")

        compare = self.client.get("/api/zones/search/compare", params={"product_id": self.main_product.id, "quantity": 1, "mode": "latest"}, headers=headers)
        self.assertEqual(compare.status_code, 200, compare.text)
        body = compare.json()
        self.assertEqual(body["scope_canonical_group_id"], self.group.id)
        self.assertEqual(body["compare_currency"], "THB")
        self.assertGreaterEqual(body["row_count"], 2)
        self.assertEqual(body["rows"][0]["final_total_cost_thb"], 112.35)

        self.assertEqual(self.client.get("/api/zones/search/compare", headers=headers).status_code, 400)
        self.assertEqual(self.client.get("/api/zones/search/history", params={"product_id": self.main_product.id}, headers=headers).status_code, 400)

    def test_branch_scope_is_enforced_server_side(self) -> None:
        scoped_headers = self._login("dev_other", "Dev@1234")
        owner_headers = self._login("owner", "Owner@1234")

        quick = self.client.get("/api/zones/search/quick", params={"q": "SKU"}, headers=scoped_headers)
        self.assertEqual(quick.status_code, 200, quick.text)
        items = quick.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["sku"], "SKU-OTHER-001")

        self.assertEqual(self.client.get("/api/zones/dev/summary", params={"branch_id": self.main_branch.id}, headers=scoped_headers).status_code, 403)
        self.assertEqual(self.client.get("/api/zones/dev/summary", params={"branch_id": self.main_branch.id}, headers=owner_headers).status_code, 200)

    def test_summary_and_notification_endpoints_return_lightweight_expected_data(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")
        admin_headers = self._login("admin", "Admin@1234")

        owner_summary = self.client.get("/api/zones/owner/summary", headers=owner_headers)
        self.assertEqual(owner_summary.status_code, 200, owner_summary.text)
        owner_body = owner_summary.json()
        self.assertIn("verification", owner_body)
        self.assertIn("notifications", owner_body)
        self.assertIn("recent_changes", owner_body)
        self.assertLessEqual(len(owner_body["recent_changes"]), 6)
        self.assertNotIn("rows", owner_body)

        admin_summary = self.client.get("/api/zones/admin/summary", headers=admin_headers)
        self.assertEqual(admin_summary.status_code, 200, admin_summary.text)
        self.assertIn("suppliers", admin_summary.json())

        notifications = self.client.get("/api/zones/notifications/summary", headers=owner_headers)
        self.assertEqual(notifications.status_code, 200, notifications.text)
        notification_body = notifications.json()
        self.assertIn("summary", notification_body)
        self.assertIn("items", notification_body)
        self.assertLessEqual(len(notification_body["items"]), 20)
        self.assertIn("message_title", notification_body["items"][0])

    def test_safe_repeated_polling_and_regression_surface_remain_correct(self) -> None:
        dev_headers = self._login("dev", "Dev@1234")

        first = self.client.get("/api/zones/dev/summary", headers=dev_headers)
        second = self.client.get("/api/zones/dev/summary", headers=dev_headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["verification"]["assigned_to_me"], second.json()["verification"]["assigned_to_me"])

        queue = self.client.get("/api/zones/verification/queue", params={"statuses": "pending", "risk_levels": "critical"}, headers=dev_headers)
        self.assertEqual(queue.status_code, 200, queue.text)
        self.assertEqual(len(queue.json()["items"]), 1)
        self.assertEqual(queue.json()["items"][0]["request_code"], "VR-MAIN-001")

        search = self.client.get("/api/zones/search/quick", params={"q": "bolt"}, headers=dev_headers)
        self.assertEqual(search.status_code, 200, search.text)
        self.assertGreaterEqual(len(search.json()["items"]), 1)

        notifications = self.client.get("/api/zones/notifications/summary", headers=dev_headers)
        self.assertEqual(notifications.status_code, 200, notifications.text)
        self.assertGreaterEqual(notifications.json()["summary"]["pending_total"], 1)

    def test_notification_target_paths_and_compare_param_mapping_are_safe(self) -> None:
        owner_headers = self._login("owner", "Owner@1234")

        notifications = self.client.get("/api/zones/notifications/summary", headers=owner_headers)
        self.assertEqual(notifications.status_code, 200, notifications.text)
        items = notifications.json()["items"]

        verification_item = next(item for item in items if item["source_domain"] == "verification")
        pricing_item = next(item for item in items if item["source_domain"] == "pricing")
        supplier_item = next(item for item in items if item["source_domain"] == "supplier")

        self.assertEqual(verification_item["target_path"], f"/zones/verification?requestId={self.main_request.id}")
        self.assertEqual(pricing_item["target_path"], f"/zones/search?view=compare&productId={self.main_product.id}&quantity=1&mode=active")
        self.assertEqual(supplier_item["target_path"], "/suppliers?proposalId=proposal-other")

        compare = self.client.get(
            "/api/zones/search/compare",
            params={"product_id": self.main_product.id, "quantity": 1, "mode": "active"},
            headers=owner_headers,
        )
        self.assertEqual(compare.status_code, 200, compare.text)
        self.assertEqual(compare.json()["scope_canonical_group_id"], self.group.id)
