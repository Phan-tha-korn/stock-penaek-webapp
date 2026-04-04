"""phase 2 suppliers and attachments

Revision ID: 202604030003
Revises: 202604030002
Create Date: 2026-04-03 14:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604030003"
down_revision = "202604030002"
branch_labels = None
depends_on = None


SUPPLIER_STATUS_ENUM = sa.Enum("ACTIVE", "INACTIVE", "ARCHIVED", name="supplierstatus", native_enum=False)
SUPPLIER_PROPOSAL_STATUS_ENUM = sa.Enum("PENDING", "APPROVED", "REJECTED", "CANCELLED", name="supplierproposalstatus", native_enum=False)
ATTACHMENT_SCAN_STATUS_ENUM = sa.Enum("PENDING", "PROCESSING", "CLEAN", "INFECTED", "FAILED", name="attachmentscanstatus", native_enum=False)


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

    if not _has_table(inspector, "suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("phone", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("line_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("facebook_url", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("website_url", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("address", sa.Text(), nullable=False, server_default=""),
            sa.Column("pickup_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_details", sa.Text(), nullable=False, server_default=""),
            sa.Column("purchase_history_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("reliability_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", SUPPLIER_STATUS_ENUM, nullable=False, server_default="ACTIVE"),
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delete_reason", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols, unique in [
        ("ix_suppliers_branch_id", ["branch_id"], False),
        ("ix_suppliers_code", ["code"], True),
        ("ix_suppliers_name", ["name"], False),
        ("ix_suppliers_normalized_name", ["normalized_name"], True),
        ("ix_suppliers_status", ["status"], False),
        ("ix_suppliers_is_verified", ["is_verified"], False),
        ("ix_suppliers_archived_at", ["archived_at"], False),
        ("ix_suppliers_deleted_at", ["deleted_at"], False),
    ]:
        _create_index_if_missing(inspector, "suppliers", index_name, cols, unique=unique)

    if not _has_table(inspector, "supplier_contacts"):
        op.create_table(
            "supplier_contacts",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("contact_type", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("value", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_contacts_supplier_id", ["supplier_id"]),
        ("ix_supplier_contacts_contact_type", ["contact_type"]),
        ("ix_supplier_contacts_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "supplier_contacts", index_name, cols)

    if not _has_table(inspector, "supplier_links"):
        op.create_table(
            "supplier_links",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("link_type", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("url", sa.String(length=1024), nullable=False, server_default=""),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_links_supplier_id", ["supplier_id"]),
        ("ix_supplier_links_link_type", ["link_type"]),
        ("ix_supplier_links_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "supplier_links", index_name, cols)

    if not _has_table(inspector, "supplier_pickup_points"):
        op.create_table(
            "supplier_pickup_points",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("address", sa.Text(), nullable=False, server_default=""),
            sa.Column("details", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_pickup_points_supplier_id", ["supplier_id"]),
        ("ix_supplier_pickup_points_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "supplier_pickup_points", index_name, cols)

    if not _has_table(inspector, "supplier_product_links"):
        op.create_table(
            "supplier_product_links",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("legacy_supplier_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("linked_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product_link"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_product_links_supplier_id", ["supplier_id"]),
        ("ix_supplier_product_links_product_id", ["product_id"]),
        ("ix_supplier_product_links_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "supplier_product_links", index_name, cols)

    if not _has_table(inspector, "supplier_reliability_scores"):
        op.create_table(
            "supplier_reliability_scores",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("overall_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("auto_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("effective_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("supplier_id", name="uq_supplier_reliability_score_supplier"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_reliability_scores_supplier_id", ["supplier_id"]),
        ("ix_supplier_reliability_scores_calculated_at", ["calculated_at"]),
    ]:
        _create_index_if_missing(inspector, "supplier_reliability_scores", index_name, cols)

    if not _has_table(inspector, "supplier_reliability_breakdowns"):
        op.create_table(
            "supplier_reliability_breakdowns",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_score_id", sa.String(length=36), sa.ForeignKey("supplier_reliability_scores.id"), nullable=False),
            sa.Column("metric_key", sa.String(length=64), nullable=False),
            sa.Column("score_value", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("weight", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("detail_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_reliability_breakdowns_supplier_score_id", ["supplier_score_id"]),
        ("ix_supplier_reliability_breakdowns_metric_key", ["metric_key"]),
    ]:
        _create_index_if_missing(inspector, "supplier_reliability_breakdowns", index_name, cols)

    if not _has_table(inspector, "supplier_change_proposals"):
        op.create_table(
            "supplier_change_proposals",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("status", SUPPLIER_PROPOSAL_STATUS_ENUM, nullable=False, server_default="PENDING"),
            sa.Column("proposed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reviewed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=True),
            sa.Column("requires_dev_review", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("proposed_payload_json", sa.Text(), nullable=True),
            sa.Column("current_payload_json", sa.Text(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_supplier_change_proposals_supplier_id", ["supplier_id"]),
        ("ix_supplier_change_proposals_action", ["action"]),
        ("ix_supplier_change_proposals_status", ["status"]),
        ("ix_supplier_change_proposals_proposed_by_user_id", ["proposed_by_user_id"]),
        ("ix_supplier_change_proposals_reviewed_by_user_id", ["reviewed_by_user_id"]),
        ("ix_supplier_change_proposals_approved_supplier_id", ["approved_supplier_id"]),
        ("ix_supplier_change_proposals_requires_dev_review", ["requires_dev_review"]),
        ("ix_supplier_change_proposals_reviewed_at", ["reviewed_at"]),
    ]:
        _create_index_if_missing(inspector, "supplier_change_proposals", index_name, cols)

    if not _has_table(inspector, "attachment_scan_jobs"):
        op.create_table(
            "attachment_scan_jobs",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("attachment_id", sa.String(length=36), sa.ForeignKey("attachments.id"), nullable=False),
            sa.Column("status", ATTACHMENT_SCAN_STATUS_ENUM, nullable=False, server_default="PENDING"),
            sa.Column("scanner_name", sa.String(length=128), nullable=False, server_default="hook"),
            sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("result_detail", sa.Text(), nullable=False, server_default=""),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_attachment_scan_jobs_attachment_id", ["attachment_id"]),
        ("ix_attachment_scan_jobs_status", ["status"]),
    ]:
        _create_index_if_missing(inspector, "attachment_scan_jobs", index_name, cols)

    if not _has_table(inspector, "attachment_type_classifications"):
        op.create_table(
            "attachment_type_classifications",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("classification", sa.String(length=64), nullable=False),
            sa.Column("allowed_mime_csv", sa.Text(), nullable=False, server_default=""),
            sa.Column("allowed_extensions_csv", sa.Text(), nullable=False, server_default=""),
            sa.Column("max_size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_file_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("entity_type", "classification", name="uq_attachment_type_classification"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_attachment_type_classifications_entity_type", ["entity_type"]),
        ("ix_attachment_type_classifications_classification", ["classification"]),
        ("ix_attachment_type_classifications_is_enabled", ["is_enabled"]),
    ]:
        _create_index_if_missing(inspector, "attachment_type_classifications", index_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in [
        "attachment_type_classifications",
        "attachment_scan_jobs",
        "supplier_change_proposals",
        "supplier_reliability_breakdowns",
        "supplier_reliability_scores",
        "supplier_product_links",
        "supplier_pickup_points",
        "supplier_links",
        "supplier_contacts",
        "suppliers",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
