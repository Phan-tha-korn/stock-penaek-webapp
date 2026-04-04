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
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import server.services.matching as matching_service
from server.db.database import Base
from server.db.models import (
    AuditEvent,
    AuditLog,
    Branch,
    CanonicalGroupLockState,
    CanonicalGroupMember,
    CanonicalProductGroup,
    CurrencyCode,
    MatchingDependencyCheck,
    MatchingDependencyStatus,
    MatchingDependencyType,
    MatchingGroupStatus,
    MatchingOperation,
    MatchingOperationGroupState,
    MatchingOperationMembershipState,
    MatchingOperationType,
    MatchingSnapshotSide,
    PriceRecord,
    PriceRecordStatus,
    PriceSourceType,
    Product,
    Role,
    StockStatus,
    Supplier,
    User,
)
from server.services.matching import (
    add_product_to_group,
    change_group_lock_state,
    create_canonical_group,
    merge_groups,
    move_product_between_groups,
    remove_product_from_group,
    split_group,
)
from server.services.security import hash_password


REPO_ROOT = Path(__file__).resolve().parents[1]


class Phase4MigrationTests(unittest.TestCase):
    def test_alembic_upgrades_create_matching_tables_and_columns(self) -> None:
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
                    "matching_operations",
                    "matching_operation_group_states",
                    "matching_operation_membership_states",
                    "matching_dependency_checks",
                }.issubset(table_names)
            )

            cur.execute("PRAGMA table_info(canonical_product_groups)")
            group_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue({"status", "version_no", "merged_into_group_id", "last_operation_id"}.issubset(group_columns))

            cur.execute("PRAGMA table_info(canonical_group_members)")
            member_columns = {row[1] for row in cur.fetchall()}
            self.assertTrue(
                {"assigned_at", "assigned_by", "source_operation_id", "removed_at", "removed_by", "end_operation_id"}.issubset(
                    member_columns
                )
            )
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
            if os.path.exists(db_path):
                os.unlink(db_path)


class Phase4MatchingUnitTests(unittest.TestCase):
    def test_minimal_snapshot_contains_only_minimal_keys(self) -> None:
        snapshot = matching_service._minimal_snapshot(
            operation_type=MatchingOperationType.ADD_PRODUCT,
            group_states=[
                {
                    "group_id": "g-1",
                    "display_name": "Group 1",
                    "status": "active",
                    "lock_state": "editable",
                    "version_no": 2,
                    "merged_into_group_id": None,
                    "member_count": 1,
                }
            ],
            membership_states=[
                {
                    "membership_id": "m-1",
                    "product_id": "p-1",
                    "group_id": "g-1",
                    "is_primary": True,
                    "active_flag": True,
                }
            ],
        )
        self.assertEqual(
            set(snapshot.keys()),
            {"operation_type", "group_ids", "product_ids", "membership_ids", "group_count", "membership_count"},
        )
        self.assertEqual(snapshot["operation_type"], "add_product")
        self.assertEqual(snapshot["group_ids"], ["g-1"])
        self.assertEqual(snapshot["product_ids"], ["p-1"])
        self.assertEqual(snapshot["membership_ids"], ["m-1"])
        self.assertNotIn("display_name", snapshot)
        self.assertNotIn("member_count", snapshot)

    def test_structural_operation_classification_and_version_bump_rule(self) -> None:
        group = CanonicalProductGroup(
            code="G-UNIT",
            display_name="Unit Group",
            system_name="Unit Group",
            description="",
            status=MatchingGroupStatus.ACTIVE,
            lock_state=CanonicalGroupLockState.EDITABLE,
            version_no=5,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        matching_service._bump_group_versions([group], operation_type=MatchingOperationType.ADD_PRODUCT)
        self.assertEqual(group.version_no, 6)

        matching_service._bump_group_versions([group], operation_type=MatchingOperationType.LOCK_CHANGE)
        self.assertEqual(group.version_no, 6)

        self.assertTrue(matching_service._structural_operation(MatchingOperationType.REVERSE_OPERATION))
        self.assertFalse(matching_service._structural_operation(MatchingOperationType.LOCK_CHANGE))


class Phase4MatchingIntegrationTests(unittest.TestCase):
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
            db.add_all([owner, dev, admin])
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

            supplier = Supplier(
                branch_id=branch.id,
                code="SUP-MATCH-001",
                name="Match Supplier",
                normalized_name="match-supplier",
                created_by=owner.id,
                updated_by=owner.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(supplier)
            await db.flush()

            for sku in ("MATCH-001", "MATCH-002", "MATCH-003", "MATCH-004", "MATCH-005"):
                db.add(
                    Product(
                        sku=sku,
                        branch_id=branch.id,
                        name_th=sku,
                        name_en=sku,
                        category="General",
                        type="General",
                        unit="pcs",
                        cost_price=10,
                        selling_price=15,
                        stock_qty=10,
                        min_stock=1,
                        max_stock=50,
                        status=StockStatus.NORMAL,
                        is_test=False,
                        supplier="Match Supplier",
                        barcode="",
                        image_url=None,
                        notes="",
                        created_by=owner.id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
            await db.commit()

    async def _actor(self, db: AsyncSession, username: str) -> User:
        actor = await db.scalar(select(User).where(User.username == username))
        assert actor is not None
        return actor

    async def _branch(self, db: AsyncSession) -> Branch:
        branch = await db.scalar(select(Branch).where(Branch.code == "MAIN"))
        assert branch is not None
        return branch

    async def _supplier(self, db: AsyncSession) -> Supplier:
        supplier = await db.scalar(select(Supplier).where(Supplier.code == "SUP-MATCH-001"))
        assert supplier is not None
        return supplier

    async def _product(self, db: AsyncSession, sku: str) -> Product:
        product = await db.scalar(select(Product).where(Product.sku == sku))
        assert product is not None
        return product

    async def _group(self, db: AsyncSession, code: str) -> CanonicalProductGroup:
        group = await db.scalar(select(CanonicalProductGroup).where(CanonicalProductGroup.code == code))
        assert group is not None
        return group

    async def _create_group(self, db: AsyncSession, *, actor: User, code: str, name: str) -> CanonicalProductGroup:
        group = await create_canonical_group(db, actor=actor, code=code, display_name=name)
        await db.commit()
        await db.refresh(group)
        return group

    async def _insert_price_record(self, db: AsyncSession, *, actor: User, product: Product, supplier: Supplier, branch: Branch) -> None:
        db.add(
            PriceRecord(
                product_id=product.id,
                supplier_id=supplier.id,
                branch_id=branch.id,
                source_type=PriceSourceType.MANUAL_ENTRY,
                status=PriceRecordStatus.ACTIVE,
                delivery_mode="standard",
                area_scope="global",
                price_dimension="real_total_cost",
                quantity_min=1,
                quantity_max=9,
                original_currency=CurrencyCode.THB,
                original_amount=100,
                normalized_currency=CurrencyCode.THB,
                normalized_amount=100,
                exchange_rate=1,
                exchange_rate_source="manual",
                exchange_rate_snapshot_at=datetime.utcnow(),
                base_price=100,
                vat_percent=7,
                vat_amount=7,
                shipping_cost=0,
                fuel_cost=0,
                labor_cost=0,
                utility_cost=0,
                distance_meter=0,
                distance_cost=0,
                supplier_fee=0,
                discount=0,
                final_total_cost=107,
                verification_required=False,
                effective_at=datetime.utcnow(),
                created_by=actor.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()

    def test_create_group_writes_audit_and_defaults(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                group = await create_canonical_group(db, actor=owner, code="CG-001", display_name="Canon Group 1")
                await db.commit()
                await db.refresh(group)

                self.assertEqual(group.status, MatchingGroupStatus.ACTIVE)
                self.assertEqual(group.lock_state, CanonicalGroupLockState.EDITABLE)
                self.assertEqual(group.version_no, 1)

                audit_logs = (await db.execute(select(AuditLog).where(AuditLog.action == "MATCHING_GROUP_CREATE"))).scalars().all()
                audit_events = (await db.execute(select(AuditEvent).where(AuditEvent.action == "MATCHING_GROUP_CREATE"))).scalars().all()
                self.assertEqual(len(audit_logs), 1)
                self.assertEqual(len(audit_events), 1)

        asyncio.run(_run())

    def test_add_product_to_group_creates_history_and_dependency_checks(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                branch = await self._branch(db)
                supplier = await self._supplier(db)
                product = await self._product(db, "MATCH-001")
                await self._insert_price_record(db, actor=owner, product=product, supplier=supplier, branch=branch)

                group = await self._create_group(db, actor=owner, code="CG-ADD", name="Add Group")
                operation = await add_product_to_group(
                    db,
                    actor=owner,
                    group_id=group.id,
                    product_id=product.id,
                    reason="seed_add",
                    is_primary=True,
                )
                await db.commit()
                await db.refresh(group)

                membership = await db.scalar(
                    select(CanonicalGroupMember).where(
                        CanonicalGroupMember.product_id == product.id,
                        CanonicalGroupMember.removed_at.is_(None),
                    )
                )
                self.assertIsNotNone(membership)
                self.assertTrue(membership.is_primary)
                self.assertEqual(group.version_no, 2)

                self.assertEqual(
                    set(operation.before_snapshot_json.keys()),
                    {"operation_type", "group_ids", "product_ids", "membership_ids", "group_count", "membership_count"},
                )
                self.assertEqual(operation.before_snapshot_json["membership_count"], 1)
                self.assertEqual(operation.after_snapshot_json["group_ids"], [group.id])
                self.assertEqual(operation.after_snapshot_json["product_ids"], [product.id])

                group_states = (
                    await db.execute(select(MatchingOperationGroupState).where(MatchingOperationGroupState.operation_id == operation.id))
                ).scalars().all()
                membership_states = (
                    await db.execute(
                        select(MatchingOperationMembershipState).where(MatchingOperationMembershipState.operation_id == operation.id)
                    )
                ).scalars().all()
                dependency_checks = (
                    await db.execute(select(MatchingDependencyCheck).where(MatchingDependencyCheck.operation_id == operation.id))
                ).scalars().all()

                self.assertEqual(len(group_states), 2)
                self.assertEqual(len(membership_states), 2)
                self.assertEqual({item.snapshot_side for item in group_states}, {MatchingSnapshotSide.BEFORE, MatchingSnapshotSide.AFTER})
                self.assertEqual({item.snapshot_side for item in membership_states}, {MatchingSnapshotSide.BEFORE, MatchingSnapshotSide.AFTER})
                self.assertEqual(len(dependency_checks), 3)

                pricing_check = next(item for item in dependency_checks if item.dependency_type == MatchingDependencyType.PRICING)
                self.assertEqual(pricing_check.check_status, MatchingDependencyStatus.WARNING)
                self.assertEqual(pricing_check.affected_entity_count, 1)

        asyncio.run(_run())

    def test_remove_product_from_group_ends_active_membership_and_bumps_version(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                product = await self._product(db, "MATCH-001")
                group = await self._create_group(db, actor=owner, code="CG-REMOVE", name="Remove Group")
                await add_product_to_group(db, actor=owner, group_id=group.id, product_id=product.id, reason="seed_add")
                await db.commit()
                await db.refresh(group)
                self.assertEqual(group.version_no, 2)

                operation = await remove_product_from_group(
                    db,
                    actor=owner,
                    group_id=group.id,
                    product_id=product.id,
                    reason="remove_for_test",
                )
                await db.commit()
                await db.refresh(group)

                active_membership = await db.scalar(
                    select(CanonicalGroupMember).where(
                        CanonicalGroupMember.product_id == product.id,
                        CanonicalGroupMember.removed_at.is_(None),
                    )
                )
                ended_membership = await db.scalar(
                    select(CanonicalGroupMember).where(
                        CanonicalGroupMember.product_id == product.id,
                        CanonicalGroupMember.end_operation_id == operation.id,
                    )
                )
                self.assertIsNone(active_membership)
                self.assertIsNotNone(ended_membership)
                self.assertEqual(group.version_no, 3)
                self.assertEqual(operation.operation_type, MatchingOperationType.REMOVE_PRODUCT)

        asyncio.run(_run())

    def test_move_product_between_groups_bumps_versions_and_preserves_single_active_membership(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                product = await self._product(db, "MATCH-001")
                source = await self._create_group(db, actor=owner, code="CG-SRC", name="Source Group")
                target = await self._create_group(db, actor=owner, code="CG-TGT", name="Target Group")
                await add_product_to_group(db, actor=owner, group_id=source.id, product_id=product.id, reason="seed_add")
                await db.commit()

                await move_product_between_groups(
                    db,
                    actor=owner,
                    source_group_id=source.id,
                    target_group_id=target.id,
                    product_id=product.id,
                    reason="move_test",
                )
                await db.commit()
                await db.refresh(source)
                await db.refresh(target)

                active_memberships = (
                    await db.execute(
                        select(CanonicalGroupMember).where(
                            CanonicalGroupMember.product_id == product.id,
                            CanonicalGroupMember.removed_at.is_(None),
                        )
                    )
                ).scalars().all()
                self.assertEqual(len(active_memberships), 1)
                self.assertEqual(active_memberships[0].group_id, target.id)
                self.assertEqual(source.version_no, 3)
                self.assertEqual(target.version_no, 2)

        asyncio.run(_run())

    def test_merge_groups_archives_sources_and_bumps_versions(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                product_one = await self._product(db, "MATCH-001")
                product_two = await self._product(db, "MATCH-002")
                target = await self._create_group(db, actor=owner, code="CG-MERGE-T", name="Merge Target")
                source = await self._create_group(db, actor=owner, code="CG-MERGE-S", name="Merge Source")
                await add_product_to_group(db, actor=owner, group_id=target.id, product_id=product_one.id, reason="seed_target")
                await add_product_to_group(db, actor=owner, group_id=source.id, product_id=product_two.id, reason="seed_source")
                await db.commit()

                operation = await merge_groups(
                    db,
                    actor=owner,
                    source_group_ids=[source.id],
                    target_group_id=target.id,
                    reason="merge_test",
                )
                await db.commit()
                await db.refresh(target)
                await db.refresh(source)

                memberships = (
                    await db.execute(
                        select(CanonicalGroupMember).where(
                            CanonicalGroupMember.group_id == target.id,
                            CanonicalGroupMember.removed_at.is_(None),
                        )
                    )
                ).scalars().all()
                self.assertEqual({item.product_id for item in memberships}, {product_one.id, product_two.id})
                self.assertEqual(target.version_no, 3)
                self.assertEqual(source.version_no, 3)
                self.assertEqual(source.status, MatchingGroupStatus.ARCHIVED)
                self.assertEqual(source.merged_into_group_id, target.id)
                self.assertEqual(operation.operation_type, MatchingOperationType.MERGE_GROUPS)

        asyncio.run(_run())

    def test_split_group_bumps_source_and_keeps_new_target_at_version_one(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                product_one = await self._product(db, "MATCH-001")
                product_two = await self._product(db, "MATCH-002")
                source = await self._create_group(db, actor=owner, code="CG-SPLIT-S", name="Split Source")
                await add_product_to_group(db, actor=owner, group_id=source.id, product_id=product_one.id, reason="seed_a")
                await add_product_to_group(db, actor=owner, group_id=source.id, product_id=product_two.id, reason="seed_b")
                await db.commit()

                operation = await split_group(
                    db,
                    actor=owner,
                    source_group_id=source.id,
                    product_ids=[product_two.id],
                    new_group_code="CG-SPLIT-T",
                    new_group_name="Split Target",
                    reason="split_test",
                )
                await db.commit()
                await db.refresh(source)
                target = await self._group(db, "CG-SPLIT-T")

                source_memberships = (
                    await db.execute(
                        select(CanonicalGroupMember).where(
                            CanonicalGroupMember.group_id == source.id,
                            CanonicalGroupMember.removed_at.is_(None),
                        )
                    )
                ).scalars().all()
                target_memberships = (
                    await db.execute(
                        select(CanonicalGroupMember).where(
                            CanonicalGroupMember.group_id == target.id,
                            CanonicalGroupMember.removed_at.is_(None),
                        )
                    )
                ).scalars().all()
                self.assertEqual({item.product_id for item in source_memberships}, {product_one.id})
                self.assertEqual({item.product_id for item in target_memberships}, {product_two.id})
                self.assertEqual(source.version_no, 4)
                self.assertEqual(target.version_no, 1)
                self.assertEqual(operation.operation_type, MatchingOperationType.SPLIT_GROUP)

        asyncio.run(_run())

    def test_lock_change_does_not_bump_version_and_locked_group_blocks_structural_edits(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                product = await self._product(db, "MATCH-001")
                group = await self._create_group(db, actor=owner, code="CG-LOCK", name="Lock Group")

                operation = await change_group_lock_state(
                    db,
                    actor=owner,
                    group_id=group.id,
                    lock_state="review_locked",
                    reason="review_lock",
                )
                await db.commit()
                await db.refresh(group)
                self.assertEqual(operation.operation_type, MatchingOperationType.LOCK_CHANGE)
                self.assertEqual(group.version_no, 1)
                self.assertEqual(group.lock_state, CanonicalGroupLockState.REVIEW_LOCKED)

                with self.assertRaises(HTTPException) as locked_error:
                    await add_product_to_group(
                        db,
                        actor=owner,
                        group_id=group.id,
                        product_id=product.id,
                        reason="should_fail_locked",
                    )
                self.assertEqual(locked_error.exception.detail, "matching_group_locked")

        asyncio.run(_run())

    def test_owner_locked_permission_rule(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                dev = await self._actor(db, "dev")
                group = await self._create_group(db, actor=owner, code="CG-OWNER-LOCK", name="Owner Lock Group")

                with self.assertRaises(HTTPException) as dev_forbidden:
                    await change_group_lock_state(
                        db,
                        actor=dev,
                        group_id=group.id,
                        lock_state="owner_locked",
                        reason="dev_should_not_owner_lock",
                    )
                self.assertEqual(dev_forbidden.exception.status_code, 403)
                self.assertEqual(dev_forbidden.exception.detail, "matching_owner_lock_requires_owner")

                await change_group_lock_state(
                    db,
                    actor=owner,
                    group_id=group.id,
                    lock_state="owner_locked",
                    reason="owner_lock",
                )
                await db.commit()
                await db.refresh(group)
                self.assertEqual(group.lock_state, CanonicalGroupLockState.OWNER_LOCKED)

                with self.assertRaises(HTTPException) as dev_unlock_forbidden:
                    await change_group_lock_state(
                        db,
                        actor=dev,
                        group_id=group.id,
                        lock_state="editable",
                        reason="dev_should_not_unlock_owner_lock",
                    )
                self.assertEqual(dev_unlock_forbidden.exception.status_code, 403)

        asyncio.run(_run())

    def test_one_active_membership_per_product_constraint(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                owner_id = owner.id
                product = await self._product(db, "MATCH-001")
                product_id = product.id
                group_one = await self._create_group(db, actor=owner, code="CG-UNIQ-1", name="Unique Group 1")
                group_two = await self._create_group(db, actor=owner, code="CG-UNIQ-2", name="Unique Group 2")
                group_two_id = group_two.id
                await add_product_to_group(db, actor=owner, group_id=group_one.id, product_id=product.id, reason="seed_membership")
                await db.commit()

                with self.assertRaises(HTTPException) as service_error:
                    await add_product_to_group(db, actor=owner, group_id=group_two.id, product_id=product.id, reason="service_block")
                self.assertEqual(service_error.exception.detail, "matching_product_already_grouped")

                db.add(
                    CanonicalGroupMember(
                        group_id=group_two_id,
                        product_id=product_id,
                        is_primary=False,
                        assigned_at=datetime.utcnow(),
                        assigned_by=owner_id,
                        created_by=owner_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
                with self.assertRaises(IntegrityError):
                    await db.commit()
                await db.rollback()

        asyncio.run(_run())

    def test_one_active_primary_per_group_constraint(self) -> None:
        async def _run() -> None:
            async with self.SessionLocal() as db:
                owner = await self._actor(db, "owner")
                owner_id = owner.id
                product_one = await self._product(db, "MATCH-001")
                product_two = await self._product(db, "MATCH-002")
                product_two_id = product_two.id
                group = await self._create_group(db, actor=owner, code="CG-PRIMARY", name="Primary Group")
                group_id = group.id
                await add_product_to_group(db, actor=owner, group_id=group.id, product_id=product_one.id, reason="seed_primary", is_primary=True)
                await db.commit()

                with self.assertRaises(HTTPException) as service_error:
                    await add_product_to_group(db, actor=owner, group_id=group.id, product_id=product_two.id, reason="conflict_primary", is_primary=True)
                self.assertEqual(service_error.exception.detail, "matching_group_primary_conflict")

                db.add(
                    CanonicalGroupMember(
                        group_id=group_id,
                        product_id=product_two_id,
                        is_primary=True,
                        assigned_at=datetime.utcnow(),
                        assigned_by=owner_id,
                        created_by=owner_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
                with self.assertRaises(IntegrityError):
                    await db.commit()
                await db.rollback()

        asyncio.run(_run())

    def test_rollback_when_operation_fails_mid_transaction(self) -> None:
        async def _run() -> None:
            original_write_audit_log = matching_service.write_audit_log

            async def _boom(*args, **kwargs):
                raise RuntimeError("forced_matching_failure")

            try:
                async with self.SessionLocal() as db:
                    owner = await self._actor(db, "owner")
                    await self._create_group(db, actor=owner, code="CG-ROLLBACK", name="Rollback Group")

                matching_service.write_audit_log = _boom
                async with self.SessionLocal() as db:
                    owner = await self._actor(db, "owner")
                    product = await self._product(db, "MATCH-001")
                    group = await self._group(db, "CG-ROLLBACK")
                    with self.assertRaises(RuntimeError):
                        await add_product_to_group(
                            db,
                            actor=owner,
                            group_id=group.id,
                            product_id=product.id,
                            reason="force_failure",
                        )

                async with self.SessionLocal() as db:
                    group = await self._group(db, "CG-ROLLBACK")
                    membership_count = int(
                        await db.scalar(
                            select(func.count(CanonicalGroupMember.id)).where(
                                CanonicalGroupMember.group_id == group.id,
                                CanonicalGroupMember.removed_at.is_(None),
                            )
                        )
                        or 0
                    )
                    operation_count = int(await db.scalar(select(func.count(MatchingOperation.id))) or 0)
                    self.assertEqual(group.version_no, 1)
                    self.assertEqual(membership_count, 0)
                    self.assertEqual(operation_count, 0)
            finally:
                matching_service.write_audit_log = original_write_audit_log

        asyncio.run(_run())

    def test_reversal_operation_not_exposed_in_current_service_layer(self) -> None:
        self.assertFalse(hasattr(matching_service, "reverse_matching_operation"))


if __name__ == "__main__":
    unittest.main()
