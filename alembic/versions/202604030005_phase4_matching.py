"""phase 4 matching operations

Revision ID: 202604030005
Revises: 202604030004
Create Date: 2026-04-03 22:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202604030005"
down_revision = "202604030004"
branch_labels = None
depends_on = None


GROUP_STATUS_ENUM = sa.Enum("active", "archived", name="matchinggroupstatus", native_enum=False)
LOCK_STATE_ENUM = sa.Enum("editable", "review_locked", "owner_locked", name="canonicalgrouplockstate", native_enum=False)
OPERATION_TYPE_ENUM = sa.Enum(
    "add_product",
    "remove_product",
    "move_product",
    "merge_groups",
    "split_group",
    "lock_change",
    "reverse_operation",
    name="matchingoperationtype",
    native_enum=False,
)
OPERATION_STATUS_ENUM = sa.Enum("completed", "reversed", "cancelled", name="matchingoperationstatus", native_enum=False)
SNAPSHOT_SIDE_ENUM = sa.Enum("before", "after", name="matchingsnapshotside", native_enum=False)
DEPENDENCY_TYPE_ENUM = sa.Enum("pricing", "search", "reporting", name="matchingdependencytype", native_enum=False)
DEPENDENCY_STATUS_ENUM = sa.Enum("clear", "warning", "blocked", name="matchingdependencystatus", native_enum=False)
JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(inspector: sa.Inspector, table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "canonical_product_groups"):
        with op.batch_alter_table("canonical_product_groups") as batch_op:
            if not _has_column(inspector, "canonical_product_groups", "status"):
                batch_op.add_column(sa.Column("status", GROUP_STATUS_ENUM, nullable=False, server_default="active"))
            if not _has_column(inspector, "canonical_product_groups", "version_no"):
                batch_op.add_column(sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"))
            if not _has_column(inspector, "canonical_product_groups", "merged_into_group_id"):
                batch_op.add_column(sa.Column("merged_into_group_id", sa.String(length=36), nullable=True))
            if not _has_column(inspector, "canonical_product_groups", "last_operation_id"):
                batch_op.add_column(sa.Column("last_operation_id", sa.String(length=36), nullable=True))
            if not _has_column(inspector, "canonical_product_groups", "archived_by"):
                batch_op.add_column(sa.Column("archived_by", sa.String(length=36), nullable=True))
            if not _has_column(inspector, "canonical_product_groups", "archive_reason"):
                batch_op.add_column(sa.Column("archive_reason", sa.Text(), nullable=False, server_default=""))
            batch_op.create_check_constraint(
                "ck_canonical_product_groups_version_no_positive",
                "version_no >= 1",
            )
        inspector = sa.inspect(bind)
        op.execute("UPDATE canonical_product_groups SET status = 'archived' WHERE archived_at IS NOT NULL")
        op.execute("UPDATE canonical_product_groups SET status = 'active' WHERE archived_at IS NULL")
        op.execute("UPDATE canonical_product_groups SET version_no = 1 WHERE version_no IS NULL OR version_no < 1")
        for index_name, cols in [
            ("ix_canonical_product_groups_status", ["status"]),
            ("ix_canonical_product_groups_version_no", ["version_no"]),
            ("ix_canonical_product_groups_merged_into_group_id", ["merged_into_group_id"]),
            ("ix_canonical_product_groups_last_operation_id", ["last_operation_id"]),
        ]:
            _create_index_if_missing(inspector, "canonical_product_groups", index_name, cols)

    if not _has_table(inspector, "matching_operations"):
        op.create_table(
            "matching_operations",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("operation_type", OPERATION_TYPE_ENUM, nullable=False),
            sa.Column("status", OPERATION_STATUS_ENUM, nullable=False, server_default="completed"),
            sa.Column("source_group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=True),
            sa.Column("target_group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=True),
            sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("before_snapshot_json", JSON_VARIANT, nullable=False),
            sa.Column("after_snapshot_json", JSON_VARIANT, nullable=False),
            sa.Column("reversal_of_operation_id", sa.String(length=36), sa.ForeignKey("matching_operations.id"), nullable=True),
            sa.Column("reversed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dependency_status", DEPENDENCY_STATUS_ENUM, nullable=False, server_default="clear"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_matching_operations_operation_type", ["operation_type"]),
        ("ix_matching_operations_status", ["status"]),
        ("ix_matching_operations_source_group_id", ["source_group_id"]),
        ("ix_matching_operations_target_group_id", ["target_group_id"]),
        ("ix_matching_operations_actor_user_id", ["actor_user_id"]),
        ("ix_matching_operations_reversal_of_operation_id", ["reversal_of_operation_id"]),
        ("ix_matching_operations_reversed_by_user_id", ["reversed_by_user_id"]),
        ("ix_matching_operations_reversed_at", ["reversed_at"]),
        ("ix_matching_operations_dependency_status", ["dependency_status"]),
        ("ix_matching_operations_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "matching_operations", index_name, cols)

    if _has_table(inspector, "canonical_product_groups") and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_canonical_product_groups_merged_into_group_id",
            "canonical_product_groups",
            "canonical_product_groups",
            ["merged_into_group_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_canonical_product_groups_last_operation_id",
            "canonical_product_groups",
            "matching_operations",
            ["last_operation_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_canonical_product_groups_archived_by",
            "canonical_product_groups",
            "users",
            ["archived_by"],
            ["id"],
        )

    if _has_table(inspector, "canonical_group_members"):
        with op.batch_alter_table("canonical_group_members", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_canonical_group_product", type_="unique")
            batch_op.add_column(sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("assigned_by", sa.String(length=36), nullable=True))
            batch_op.add_column(sa.Column("source_operation_id", sa.String(length=36), nullable=True))
            batch_op.add_column(sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.add_column(sa.Column("removed_by", sa.String(length=36), nullable=True))
            batch_op.add_column(sa.Column("end_operation_id", sa.String(length=36), nullable=True))
            batch_op.add_column(sa.Column("removal_reason", sa.Text(), nullable=False, server_default=""))
            batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        inspector = sa.inspect(bind)
        op.execute("UPDATE canonical_group_members SET assigned_at = COALESCE(assigned_at, created_at)")
        op.execute("UPDATE canonical_group_members SET assigned_by = COALESCE(assigned_by, created_by)")
        op.execute("UPDATE canonical_group_members SET removed_at = COALESCE(removed_at, archived_at)")
        op.execute("UPDATE canonical_group_members SET updated_at = COALESCE(updated_at, removed_at, assigned_at, created_at)")
        for index_name, cols in [
            ("ix_canonical_group_members_assigned_by", ["assigned_by"]),
            ("ix_canonical_group_members_source_operation_id", ["source_operation_id"]),
            ("ix_canonical_group_members_removed_at", ["removed_at"]),
            ("ix_canonical_group_members_removed_by", ["removed_by"]),
            ("ix_canonical_group_members_end_operation_id", ["end_operation_id"]),
            ("ix_canonical_group_members_updated_at", ["updated_at"]),
        ]:
            _create_index_if_missing(inspector, "canonical_group_members", index_name, cols)
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_canonical_group_members_active_product "
            "ON canonical_group_members (product_id) WHERE removed_at IS NULL AND archived_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_canonical_group_members_active_group_product "
            "ON canonical_group_members (group_id, product_id) WHERE removed_at IS NULL AND archived_at IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_canonical_group_members_active_primary_group "
            "ON canonical_group_members (group_id) WHERE is_primary = 1 AND removed_at IS NULL AND archived_at IS NULL"
        )
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_canonical_group_members_assigned_by",
                "canonical_group_members",
                "users",
                ["assigned_by"],
                ["id"],
            )
            op.create_foreign_key(
                "fk_canonical_group_members_source_operation_id",
                "canonical_group_members",
                "matching_operations",
                ["source_operation_id"],
                ["id"],
            )
            op.create_foreign_key(
                "fk_canonical_group_members_removed_by",
                "canonical_group_members",
                "users",
                ["removed_by"],
                ["id"],
            )
            op.create_foreign_key(
                "fk_canonical_group_members_end_operation_id",
                "canonical_group_members",
                "matching_operations",
                ["end_operation_id"],
                ["id"],
            )

    if not _has_table(inspector, "matching_operation_group_states"):
        op.create_table(
            "matching_operation_group_states",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("operation_id", sa.String(length=36), sa.ForeignKey("matching_operations.id"), nullable=False),
            sa.Column("snapshot_side", SNAPSHOT_SIDE_ENUM, nullable=False),
            sa.Column("group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", GROUP_STATUS_ENUM, nullable=False, server_default="active"),
            sa.Column("lock_state", LOCK_STATE_ENUM, nullable=False, server_default="editable"),
            sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("merged_into_group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=True),
            sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_matching_operation_group_states_operation_id", ["operation_id"]),
        ("ix_matching_operation_group_states_snapshot_side", ["snapshot_side"]),
        ("ix_matching_operation_group_states_group_id", ["group_id"]),
        ("ix_matching_operation_group_states_status", ["status"]),
        ("ix_matching_operation_group_states_lock_state", ["lock_state"]),
        ("ix_matching_operation_group_states_merged_into_group_id", ["merged_into_group_id"]),
        ("ix_matching_operation_group_states_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "matching_operation_group_states", index_name, cols)

    if not _has_table(inspector, "matching_operation_membership_states"):
        op.create_table(
            "matching_operation_membership_states",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("operation_id", sa.String(length=36), sa.ForeignKey("matching_operations.id"), nullable=False),
            sa.Column("snapshot_side", SNAPSHOT_SIDE_ENUM, nullable=False),
            sa.Column("membership_id", sa.String(length=36), sa.ForeignKey("canonical_group_members.id"), nullable=True),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("assigned_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("removed_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("active_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_matching_operation_membership_states_operation_id", ["operation_id"]),
        ("ix_matching_operation_membership_states_snapshot_side", ["snapshot_side"]),
        ("ix_matching_operation_membership_states_membership_id", ["membership_id"]),
        ("ix_matching_operation_membership_states_product_id", ["product_id"]),
        ("ix_matching_operation_membership_states_group_id", ["group_id"]),
        ("ix_matching_operation_membership_states_assigned_by", ["assigned_by"]),
        ("ix_matching_operation_membership_states_removed_by", ["removed_by"]),
        ("ix_matching_operation_membership_states_active_flag", ["active_flag"]),
        ("ix_matching_operation_membership_states_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "matching_operation_membership_states", index_name, cols)

    if not _has_table(inspector, "matching_dependency_checks"):
        op.create_table(
            "matching_dependency_checks",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("operation_id", sa.String(length=36), sa.ForeignKey("matching_operations.id"), nullable=False),
            sa.Column("dependency_type", DEPENDENCY_TYPE_ENUM, nullable=False),
            sa.Column("check_status", DEPENDENCY_STATUS_ENUM, nullable=False, server_default="clear"),
            sa.Column("affected_entity_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("detail_json", JSON_VARIANT, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_matching_dependency_checks_operation_id", ["operation_id"]),
        ("ix_matching_dependency_checks_dependency_type", ["dependency_type"]),
        ("ix_matching_dependency_checks_check_status", ["check_status"]),
        ("ix_matching_dependency_checks_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "matching_dependency_checks", index_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for index_name in [
        "ux_canonical_group_members_active_product",
        "ux_canonical_group_members_active_group_product",
        "ux_canonical_group_members_active_primary_group",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    for table_name in [
        "matching_dependency_checks",
        "matching_operation_membership_states",
        "matching_operation_group_states",
        "matching_operations",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)

    if _has_table(inspector, "canonical_group_members"):
        with op.batch_alter_table("canonical_group_members", recreate="always") as batch_op:
            batch_op.drop_column("updated_at")
            batch_op.drop_column("removal_reason")
            batch_op.drop_column("end_operation_id")
            batch_op.drop_column("removed_by")
            batch_op.drop_column("removed_at")
            batch_op.drop_column("source_operation_id")
            batch_op.drop_column("assigned_by")
            batch_op.drop_column("assigned_at")
            batch_op.create_unique_constraint("uq_canonical_group_product", ["group_id", "product_id"])
        inspector = sa.inspect(bind)

    if _has_table(inspector, "canonical_product_groups"):
        with op.batch_alter_table("canonical_product_groups") as batch_op:
            batch_op.drop_constraint("ck_canonical_product_groups_version_no_positive", type_="check")
            batch_op.drop_column("archive_reason")
            batch_op.drop_column("archived_by")
            batch_op.drop_column("last_operation_id")
            batch_op.drop_column("merged_into_group_id")
            batch_op.drop_column("version_no")
            batch_op.drop_column("status")
