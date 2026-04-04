"""phase 9 historical snapshots

Revision ID: 202604030009
Revises: 202604030008
Create Date: 2026-04-03 14:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202604030009"
down_revision = "202604030008"
branch_labels = None
depends_on = None


JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
REPORT_SNAPSHOT_TYPE_ENUM = sa.Enum(
    "report",
    "audit_bundle",
    "decision_trace",
    "historical_compare",
    name="reportsnapshottype",
    native_enum=False,
)
REPORT_SNAPSHOT_STATUS_ENUM = sa.Enum("completed", "cancelled", name="reportsnapshotstatus", native_enum=False)
REPORT_SNAPSHOT_ITEM_TYPE_ENUM = sa.Enum(
    "verification_state",
    "request_item",
    "dependency_warning",
    "price_record",
    "formula_version",
    "supplier_state",
    "matching_group",
    "product_state",
    name="reportsnapshotitemtype",
    native_enum=False,
)
REPORT_SNAPSHOT_LINK_ROLE_ENUM = sa.Enum("primary", "related", "dependency", name="reportsnapshotlinkrole", native_enum=False)


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(inspector: sa.Inspector, table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "report_snapshots"):
        op.create_table(
            "report_snapshots",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("snapshot_code", sa.String(length=64), nullable=False),
            sa.Column("snapshot_type", REPORT_SNAPSHOT_TYPE_ENUM, nullable=False, server_default="decision_trace"),
            sa.Column("scope_type", sa.String(length=64), nullable=False),
            sa.Column("scope_ref_id", sa.String(length=36), nullable=True),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("as_of_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("period_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("period_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("generation_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("generated_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("source_consistency_token", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", REPORT_SNAPSHOT_STATUS_ENUM, nullable=False, server_default="completed"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("snapshot_code", name="uq_report_snapshots_snapshot_code"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_report_snapshots_snapshot_code", ["snapshot_code"]),
        ("ix_report_snapshots_snapshot_type", ["snapshot_type"]),
        ("ix_report_snapshots_scope_type", ["scope_type"]),
        ("ix_report_snapshots_scope_ref_id", ["scope_ref_id"]),
        ("ix_report_snapshots_branch_id", ["branch_id"]),
        ("ix_report_snapshots_as_of_at", ["as_of_at"]),
        ("ix_report_snapshots_period_from", ["period_from"]),
        ("ix_report_snapshots_period_to", ["period_to"]),
        ("ix_report_snapshots_generated_by_user_id", ["generated_by_user_id"]),
        ("ix_report_snapshots_source_consistency_token", ["source_consistency_token"]),
        ("ix_report_snapshots_status", ["status"]),
        ("ix_report_snapshots_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "report_snapshots", index_name, cols)

    if not _has_table(inspector, "report_snapshot_items"):
        op.create_table(
            "report_snapshot_items",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("report_snapshots.id"), nullable=False),
            sa.Column("item_type", REPORT_SNAPSHOT_ITEM_TYPE_ENUM, nullable=False),
            sa.Column("source_entity_type", sa.String(length=64), nullable=False),
            sa.Column("source_entity_id", sa.String(length=36), nullable=True),
            sa.Column("source_version_token", sa.String(length=255), nullable=True),
            sa.Column("payload_json", JSON_VARIANT, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_report_snapshot_items_snapshot_id", ["snapshot_id"]),
        ("ix_report_snapshot_items_item_type", ["item_type"]),
        ("ix_report_snapshot_items_source_entity_type", ["source_entity_type"]),
        ("ix_report_snapshot_items_source_entity_id", ["source_entity_id"]),
        ("ix_report_snapshot_items_source_version_token", ["source_version_token"]),
        ("ix_report_snapshot_items_created_at", ["created_at"]),
        ("ix_report_snapshot_items_snapshot_item_type", ["snapshot_id", "item_type"]),
    ]:
        _create_index_if_missing(inspector, "report_snapshot_items", index_name, cols)

    if not _has_table(inspector, "report_snapshot_links"):
        op.create_table(
            "report_snapshot_links",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("snapshot_id", sa.String(length=36), sa.ForeignKey("report_snapshots.id"), nullable=False),
            sa.Column("linked_entity_type", sa.String(length=64), nullable=False),
            sa.Column("linked_entity_id", sa.String(length=36), nullable=False),
            sa.Column("link_role", REPORT_SNAPSHOT_LINK_ROLE_ENUM, nullable=False, server_default="related"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_report_snapshot_links_snapshot_id", ["snapshot_id"]),
        ("ix_report_snapshot_links_linked_entity_type", ["linked_entity_type"]),
        ("ix_report_snapshot_links_linked_entity_id", ["linked_entity_id"]),
        ("ix_report_snapshot_links_link_role", ["link_role"]),
        ("ix_report_snapshot_links_created_at", ["created_at"]),
        ("ix_report_snapshot_links_snapshot_role", ["snapshot_id", "link_role"]),
    ]:
        _create_index_if_missing(inspector, "report_snapshot_links", index_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in [
        "report_snapshot_links",
        "report_snapshot_items",
        "report_snapshots",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
