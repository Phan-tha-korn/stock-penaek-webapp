"""phase 6 search projections

Revision ID: 202604030007
Revises: 202604030006
Create Date: 2026-04-03 23:59:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202604030007"
down_revision = "202604030006"
branch_labels = None
depends_on = None


WORKFLOW_STATUS_ENUM = sa.Enum(
    "pending",
    "approved",
    "rejected",
    "returned_for_revision",
    "cancelled",
    name="verificationworkflowstatus",
    native_enum=False,
)
RISK_LEVEL_ENUM = sa.Enum("low", "medium", "high", "critical", name="verificationrisklevel", native_enum=False)
SAFETY_STATUS_ENUM = sa.Enum("safe", "warning", "blocked", name="verificationsafetystatus", native_enum=False)
PRICE_STATUS_ENUM = sa.Enum(
    "draft",
    "pending_verify",
    "active",
    "inactive",
    "replaced",
    "expired",
    "archived",
    "rejected",
    name="pricerecordstatus",
    native_enum=False,
)
PRICE_SOURCE_ENUM = sa.Enum(
    "actual_purchase",
    "supplier_quote",
    "phone_inquiry",
    "chat_confirmation",
    "manual_entry",
    "imported",
    "estimated",
    name="pricesourcetype",
    native_enum=False,
)
CURRENCY_ENUM = sa.Enum("THB", "USD", name="currencycode", native_enum=False)
JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


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

    if not _has_table(inspector, "catalog_search_documents"):
        op.create_table(
            "catalog_search_documents",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("canonical_group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=True),
            sa.Column("canonical_group_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("sku", sa.String(length=64), nullable=False),
            sa.Column("name_th", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("name_en", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("category_text", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("alias_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("tag_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("supplier_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("active_price_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("verified_supplier_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("latest_effective_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("latest_price_record_id", sa.String(length=36), sa.ForeignKey("price_records.id"), nullable=True),
            sa.Column("latest_normalized_amount_thb", sa.Numeric(18, 6), nullable=True),
            sa.Column("latest_final_total_cost_thb", sa.Numeric(18, 6), nullable=True),
            sa.Column("cheapest_active_price_record_id", sa.String(length=36), sa.ForeignKey("price_records.id"), nullable=True),
            sa.Column("cheapest_active_normalized_amount_thb", sa.Numeric(18, 6), nullable=True),
            sa.Column("cheapest_active_final_total_cost_thb", sa.Numeric(18, 6), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("product_id", name="uq_catalog_search_documents_product"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_catalog_search_documents_product_id", ["product_id"]),
        ("ix_catalog_search_documents_branch_id", ["branch_id"]),
        ("ix_catalog_search_documents_canonical_group_id", ["canonical_group_id"]),
        ("ix_catalog_search_documents_canonical_group_name", ["canonical_group_name"]),
        ("ix_catalog_search_documents_sku", ["sku"]),
        ("ix_catalog_search_documents_name_th", ["name_th"]),
        ("ix_catalog_search_documents_name_en", ["name_en"]),
        ("ix_catalog_search_documents_category_text", ["category_text"]),
        ("ix_catalog_search_documents_lifecycle_status", ["lifecycle_status"]),
        ("ix_catalog_search_documents_latest_effective_at", ["latest_effective_at"]),
        ("ix_catalog_search_documents_latest_price_record_id", ["latest_price_record_id"]),
        ("ix_catalog_search_documents_latest_final_total_cost_thb", ["latest_final_total_cost_thb"]),
        ("ix_catalog_search_documents_cheapest_active_price_record_id", ["cheapest_active_price_record_id"]),
        ("ix_catalog_search_documents_cheapest_active_final_total_cost_thb", ["cheapest_active_final_total_cost_thb"]),
        ("ix_catalog_search_documents_updated_at", ["updated_at"]),
    ]:
        _create_index_if_missing(inspector, "catalog_search_documents", index_name, cols)

    if not _has_table(inspector, "price_search_projections"):
        op.create_table(
            "price_search_projections",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("price_record_id", sa.String(length=36), sa.ForeignKey("price_records.id"), nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("canonical_group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=True),
            sa.Column("canonical_group_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("sku", sa.String(length=64), nullable=False),
            sa.Column("product_name_th", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("product_name_en", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("category_text", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("tag_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("supplier_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("supplier_is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("supplier_effective_score", sa.Numeric(5, 2), nullable=True),
            sa.Column("status", PRICE_STATUS_ENUM, nullable=False),
            sa.Column("source_type", PRICE_SOURCE_ENUM, nullable=False),
            sa.Column("delivery_mode", sa.String(length=64), nullable=False, server_default="standard"),
            sa.Column("area_scope", sa.String(length=128), nullable=False, server_default="global"),
            sa.Column("price_dimension", sa.String(length=64), nullable=False, server_default="real_total_cost"),
            sa.Column("quantity_min", sa.Integer(), nullable=False),
            sa.Column("quantity_max", sa.Integer(), nullable=True),
            sa.Column("original_currency", CURRENCY_ENUM, nullable=False),
            sa.Column("normalized_currency", CURRENCY_ENUM, nullable=False, server_default="THB"),
            sa.Column("normalized_amount_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("vat_amount_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("shipping_cost_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("fuel_cost_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("labor_cost_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("utility_cost_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("supplier_fee_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("discount_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("final_total_cost_thb", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("verification_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("price_record_id", name="uq_price_search_projections_price_record"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_price_search_projections_price_record_id", ["price_record_id"]),
        ("ix_price_search_projections_product_id", ["product_id"]),
        ("ix_price_search_projections_branch_id", ["branch_id"]),
        ("ix_price_search_projections_supplier_id", ["supplier_id"]),
        ("ix_price_search_projections_canonical_group_id", ["canonical_group_id"]),
        ("ix_price_search_projections_canonical_group_name", ["canonical_group_name"]),
        ("ix_price_search_projections_sku", ["sku"]),
        ("ix_price_search_projections_product_name_th", ["product_name_th"]),
        ("ix_price_search_projections_product_name_en", ["product_name_en"]),
        ("ix_price_search_projections_category_text", ["category_text"]),
        ("ix_price_search_projections_supplier_name", ["supplier_name"]),
        ("ix_price_search_projections_supplier_is_verified", ["supplier_is_verified"]),
        ("ix_price_search_projections_supplier_effective_score", ["supplier_effective_score"]),
        ("ix_price_search_projections_status", ["status"]),
        ("ix_price_search_projections_source_type", ["source_type"]),
        ("ix_price_search_projections_delivery_mode", ["delivery_mode"]),
        ("ix_price_search_projections_area_scope", ["area_scope"]),
        ("ix_price_search_projections_price_dimension", ["price_dimension"]),
        ("ix_price_search_projections_quantity_min", ["quantity_min"]),
        ("ix_price_search_projections_quantity_max", ["quantity_max"]),
        ("ix_price_search_projections_original_currency", ["original_currency"]),
        ("ix_price_search_projections_normalized_currency", ["normalized_currency"]),
        ("ix_price_search_projections_normalized_amount_thb", ["normalized_amount_thb"]),
        ("ix_price_search_projections_final_total_cost_thb", ["final_total_cost_thb"]),
        ("ix_price_search_projections_verification_required", ["verification_required"]),
        ("ix_price_search_projections_effective_at", ["effective_at"]),
        ("ix_price_search_projections_expire_at", ["expire_at"]),
        ("ix_price_search_projections_archived_at", ["archived_at"]),
        ("ix_price_search_projections_updated_at", ["updated_at"]),
    ]:
        _create_index_if_missing(inspector, "price_search_projections", index_name, cols)
    for index_name, cols in [
        ("ix_price_search_projections_compare_lookup", ["canonical_group_id", "branch_id", "delivery_mode", "area_scope", "status"]),
        ("ix_price_search_projections_compare_product_lookup", ["product_id", "branch_id", "status", "effective_at"]),
        ("ix_price_search_projections_compare_supplier_lookup", ["supplier_id", "status", "effective_at"]),
    ]:
        _create_index_if_missing(inspector, "price_search_projections", index_name, cols)

    if not _has_table(inspector, "verification_queue_projections"):
        op.create_table(
            "verification_queue_projections",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=False),
            sa.Column("request_code", sa.String(length=32), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("workflow_status", WORKFLOW_STATUS_ENUM, nullable=False),
            sa.Column("risk_level", RISK_LEVEL_ENUM, nullable=False),
            sa.Column("risk_score", sa.Integer(), nullable=True),
            sa.Column("subject_domain", sa.String(length=64), nullable=False),
            sa.Column("queue_key", sa.String(length=64), nullable=False),
            sa.Column("safety_status", SAFETY_STATUS_ENUM, nullable=False),
            sa.Column("assignee_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assignee_role", sa.String(length=32), nullable=True),
            sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("dependency_warning_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_escalation_level", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("has_blocking_dependency", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_overdue", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("primary_entity_type", sa.String(length=64), nullable=True),
            sa.Column("primary_entity_id", sa.String(length=36), nullable=True),
            sa.Column("latest_action_type", sa.String(length=64), nullable=True),
            sa.Column("latest_action_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sla_deadline_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("request_id", name="uq_verification_queue_projections_request"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_verification_queue_projections_request_id", ["request_id"]),
        ("ix_verification_queue_projections_request_code", ["request_code"]),
        ("ix_verification_queue_projections_branch_id", ["branch_id"]),
        ("ix_verification_queue_projections_workflow_status", ["workflow_status"]),
        ("ix_verification_queue_projections_risk_level", ["risk_level"]),
        ("ix_verification_queue_projections_risk_score", ["risk_score"]),
        ("ix_verification_queue_projections_subject_domain", ["subject_domain"]),
        ("ix_verification_queue_projections_queue_key", ["queue_key"]),
        ("ix_verification_queue_projections_safety_status", ["safety_status"]),
        ("ix_verification_queue_projections_assignee_user_id", ["assignee_user_id"]),
        ("ix_verification_queue_projections_assignee_role", ["assignee_role"]),
        ("ix_verification_queue_projections_requested_by_user_id", ["requested_by_user_id"]),
        ("ix_verification_queue_projections_current_escalation_level", ["current_escalation_level"]),
        ("ix_verification_queue_projections_has_blocking_dependency", ["has_blocking_dependency"]),
        ("ix_verification_queue_projections_is_overdue", ["is_overdue"]),
        ("ix_verification_queue_projections_primary_entity_type", ["primary_entity_type"]),
        ("ix_verification_queue_projections_primary_entity_id", ["primary_entity_id"]),
        ("ix_verification_queue_projections_latest_action_type", ["latest_action_type"]),
        ("ix_verification_queue_projections_latest_action_at", ["latest_action_at"]),
        ("ix_verification_queue_projections_sla_deadline_at", ["sla_deadline_at"]),
        ("ix_verification_queue_projections_created_at", ["created_at"]),
        ("ix_verification_queue_projections_resolved_at", ["resolved_at"]),
        ("ix_verification_queue_projections_updated_at", ["updated_at"]),
    ]:
        _create_index_if_missing(inspector, "verification_queue_projections", index_name, cols)
    _create_index_if_missing(
        inspector,
        "verification_queue_projections",
        "ix_verification_queue_projections_queue_status_risk_deadline",
        ["queue_key", "workflow_status", "risk_level", "sla_deadline_at"],
    )

    if _has_table(inspector, "price_records"):
        for index_name, cols in [
            ("ix_price_records_compare_active_lookup", ["product_id", "branch_id", "status", "delivery_mode", "area_scope", "effective_at"]),
            ("ix_price_records_compare_supplier_lookup", ["supplier_id", "status", "effective_at"]),
            ("ix_price_records_branch_final_total_cost", ["branch_id", "status", "final_total_cost"]),
        ]:
            _create_index_if_missing(inspector, "price_records", index_name, cols)
    if _has_table(inspector, "verification_requests"):
        _create_index_if_missing(
            inspector,
            "verification_requests",
            "ix_verification_requests_queue_status_risk_deadline",
            ["queue_key", "workflow_status", "risk_level", "sla_deadline_at"],
        )

    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_catalog_search_documents_search_text_trgm "
            "ON catalog_search_documents USING gin (search_text gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_price_search_projections_supplier_name_trgm "
            "ON price_search_projections USING gin (supplier_name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_verification_queue_projections_search_text_trgm "
            "ON verification_queue_projections USING gin (search_text gin_trgm_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if bind.dialect.name == "postgresql":
        for index_name in [
            "ix_verification_queue_projections_search_text_trgm",
            "ix_price_search_projections_supplier_name_trgm",
            "ix_catalog_search_documents_search_text_trgm",
        ]:
            op.execute(f"DROP INDEX IF EXISTS {index_name}")

    for table_name in [
        "verification_queue_projections",
        "price_search_projections",
        "catalog_search_documents",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
