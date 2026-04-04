"""phase 3 pricing and formulas

Revision ID: 202604030004
Revises: 202604030003
Create Date: 2026-04-03 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202604030004"
down_revision = "202604030003"
branch_labels = None
depends_on = None


CURRENCY_ENUM = sa.Enum("THB", "USD", name="currencycode", native_enum=False)
PRICE_STATUS_ENUM = sa.Enum("draft", "pending_verify", "active", "inactive", "replaced", "expired", "archived", "rejected", name="pricerecordstatus", native_enum=False)
PRICE_SOURCE_ENUM = sa.Enum("actual_purchase", "supplier_quote", "phone_inquiry", "chat_confirmation", "manual_entry", "imported", "estimated", name="pricesourcetype", native_enum=False)
FORMULA_SCOPE_ENUM = sa.Enum("global", "category", "product", "supplier", "branch", "area", name="formulascopetype", native_enum=False)
FORMULA_STATUS_ENUM = sa.Enum("draft", "active", "inactive", "archived", name="formulastatus", native_enum=False)
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

    if not _has_table(inspector, "exchange_rate_snapshots"):
        op.create_table(
            "exchange_rate_snapshots",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("base_currency", CURRENCY_ENUM, nullable=False),
            sa.Column("quote_currency", CURRENCY_ENUM, nullable=False),
            sa.Column("rate_value", sa.Numeric(18, 8), nullable=False, server_default="1"),
            sa.Column("source_name", sa.String(length=64), nullable=False, server_default="manual"),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("base_currency", "quote_currency", "captured_at", name="uq_exchange_rate_snapshot_pair_time"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_exchange_rate_snapshots_base_currency", ["base_currency"]),
        ("ix_exchange_rate_snapshots_quote_currency", ["quote_currency"]),
        ("ix_exchange_rate_snapshots_captured_at", ["captured_at"]),
    ]:
        _create_index_if_missing(inspector, "exchange_rate_snapshots", index_name, cols)

    if not _has_table(inspector, "cost_formulas"):
        op.create_table(
            "cost_formulas",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("scope_type", FORMULA_SCOPE_ENUM, nullable=False),
            sa.Column("scope_ref_id", sa.String(length=36), nullable=True),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("is_override", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", FORMULA_STATUS_ENUM, nullable=False, server_default="draft"),
            sa.Column("active_version_id", sa.String(length=36), nullable=True),
            sa.Column("warning_on_change", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("code", name="uq_cost_formula_code"),
            sa.CheckConstraint("(scope_type = 'global' AND scope_ref_id IS NULL) OR (scope_type <> 'global' AND scope_ref_id IS NOT NULL)", name="ck_cost_formulas_scope_ref_required"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols, unique in [
        ("ix_cost_formulas_code", ["code"], True),
        ("ix_cost_formulas_name", ["name"], False),
        ("ix_cost_formulas_scope_type", ["scope_type"], False),
        ("ix_cost_formulas_scope_ref_id", ["scope_ref_id"], False),
        ("ix_cost_formulas_branch_id", ["branch_id"], False),
        ("ix_cost_formulas_is_override", ["is_override"], False),
        ("ix_cost_formulas_status", ["status"], False),
        ("ix_cost_formulas_active_version_id", ["active_version_id"], False),
        ("ix_cost_formulas_archived_at", ["archived_at"], False),
    ]:
        _create_index_if_missing(inspector, "cost_formulas", index_name, cols, unique=unique)

    if not _has_table(inspector, "cost_formula_versions"):
        op.create_table(
            "cost_formula_versions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("formula_id", sa.String(length=36), sa.ForeignKey("cost_formulas.id"), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("expression_text", sa.Text(), nullable=False),
            sa.Column("variables_json", JSON_VARIANT, nullable=False),
            sa.Column("constants_json", JSON_VARIANT, nullable=False),
            sa.Column("dependency_keys_json", JSON_VARIANT, nullable=False),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_active_version", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_version_id", sa.String(length=36), sa.ForeignKey("cost_formula_versions.id"), nullable=True),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("formula_id", "version_no", name="uq_cost_formula_version_formula_version_no"),
            sa.CheckConstraint("version_no >= 1", name="ck_cost_formula_versions_version_no_positive"),
            sa.CheckConstraint(
                "(NOT is_active_version) OR (is_locked AND activated_at IS NOT NULL)",
                name="ck_cost_formula_versions_active_locked",
            ),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_cost_formula_versions_formula_id", ["formula_id"]),
        ("ix_cost_formula_versions_version_no", ["version_no"]),
        ("ix_cost_formula_versions_is_active_version", ["is_active_version"]),
        ("ix_cost_formula_versions_is_locked", ["is_locked"]),
        ("ix_cost_formula_versions_activated_at", ["activated_at"]),
        ("ix_cost_formula_versions_replaced_version_id", ["replaced_version_id"]),
        ("ix_cost_formula_versions_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "cost_formula_versions", index_name, cols)
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_cost_formulas_active_version_id",
            "cost_formulas",
            "cost_formula_versions",
            ["active_version_id"],
            ["id"],
        )

    if not _has_table(inspector, "price_records"):
        op.create_table(
            "price_records",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("supplier_id", sa.String(length=36), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("source_type", PRICE_SOURCE_ENUM, nullable=False),
            sa.Column("status", PRICE_STATUS_ENUM, nullable=False, server_default="draft"),
            sa.Column("delivery_mode", sa.String(length=64), nullable=False, server_default="standard"),
            sa.Column("area_scope", sa.String(length=128), nullable=False, server_default="global"),
            sa.Column("price_dimension", sa.String(length=64), nullable=False, server_default="real_total_cost"),
            sa.Column("quantity_min", sa.Integer(), nullable=False),
            sa.Column("quantity_max", sa.Integer(), nullable=True),
            sa.Column("original_currency", CURRENCY_ENUM, nullable=False),
            sa.Column("original_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("normalized_currency", CURRENCY_ENUM, nullable=False, server_default="THB"),
            sa.Column("normalized_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("exchange_rate", sa.Numeric(18, 8), nullable=False, server_default="1"),
            sa.Column("exchange_rate_source", sa.String(length=64), nullable=False, server_default="manual"),
            sa.Column("exchange_rate_snapshot_id", sa.String(length=36), sa.ForeignKey("exchange_rate_snapshots.id"), nullable=True),
            sa.Column("exchange_rate_snapshot_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("base_price", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("vat_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("vat_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("shipping_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("fuel_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("labor_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("utility_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("distance_meter", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("distance_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("supplier_fee", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("discount", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("final_total_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
            sa.Column("formula_id", sa.String(length=36), sa.ForeignKey("cost_formulas.id"), nullable=True),
            sa.Column("formula_version_id", sa.String(length=36), sa.ForeignKey("cost_formula_versions.id"), nullable=True),
            sa.Column("verification_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replaced_by_price_record_id", sa.String(length=36), sa.ForeignKey("price_records.id"), nullable=True),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("quantity_min >= 1", name="ck_price_records_quantity_min_positive"),
            sa.CheckConstraint("quantity_max IS NULL OR quantity_max >= quantity_min", name="ck_price_records_quantity_range_valid"),
            sa.CheckConstraint("exchange_rate > 0", name="ck_price_records_exchange_rate_positive"),
            sa.CheckConstraint("vat_percent >= 0 AND vat_percent <= 100", name="ck_price_records_vat_percent_range"),
            sa.CheckConstraint("original_amount >= 0", name="ck_price_records_original_amount_non_negative"),
            sa.CheckConstraint("normalized_amount >= 0", name="ck_price_records_normalized_amount_non_negative"),
            sa.CheckConstraint("base_price >= 0", name="ck_price_records_base_price_non_negative"),
            sa.CheckConstraint("vat_amount >= 0", name="ck_price_records_vat_amount_non_negative"),
            sa.CheckConstraint("shipping_cost >= 0", name="ck_price_records_shipping_cost_non_negative"),
            sa.CheckConstraint("fuel_cost >= 0", name="ck_price_records_fuel_cost_non_negative"),
            sa.CheckConstraint("labor_cost >= 0", name="ck_price_records_labor_cost_non_negative"),
            sa.CheckConstraint("utility_cost >= 0", name="ck_price_records_utility_cost_non_negative"),
            sa.CheckConstraint("distance_meter >= 0", name="ck_price_records_distance_meter_non_negative"),
            sa.CheckConstraint("distance_cost >= 0", name="ck_price_records_distance_cost_non_negative"),
            sa.CheckConstraint("supplier_fee >= 0", name="ck_price_records_supplier_fee_non_negative"),
            sa.CheckConstraint("discount >= 0", name="ck_price_records_discount_non_negative"),
            sa.CheckConstraint("final_total_cost >= 0", name="ck_price_records_final_total_cost_non_negative"),
            sa.CheckConstraint("expire_at IS NULL OR expire_at > effective_at", name="ck_price_records_expire_after_effective"),
            sa.CheckConstraint("normalized_currency = 'THB'", name="ck_price_records_normalized_currency_thb"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_price_records_product_id", ["product_id"]),
        ("ix_price_records_supplier_id", ["supplier_id"]),
        ("ix_price_records_branch_id", ["branch_id"]),
        ("ix_price_records_source_type", ["source_type"]),
        ("ix_price_records_status", ["status"]),
        ("ix_price_records_delivery_mode", ["delivery_mode"]),
        ("ix_price_records_area_scope", ["area_scope"]),
        ("ix_price_records_price_dimension", ["price_dimension"]),
        ("ix_price_records_original_currency", ["original_currency"]),
        ("ix_price_records_normalized_currency", ["normalized_currency"]),
        ("ix_price_records_exchange_rate_snapshot_id", ["exchange_rate_snapshot_id"]),
        ("ix_price_records_formula_id", ["formula_id"]),
        ("ix_price_records_formula_version_id", ["formula_version_id"]),
        ("ix_price_records_verification_required", ["verification_required"]),
        ("ix_price_records_effective_at", ["effective_at"]),
        ("ix_price_records_expire_at", ["expire_at"]),
        ("ix_price_records_replaced_by_price_record_id", ["replaced_by_price_record_id"]),
        ("ix_price_records_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "price_records", index_name, cols)
    _create_index_if_missing(inspector, "price_records", "ix_price_records_product_status_effective", ["product_id", "status", "effective_at"])
    _create_index_if_missing(inspector, "price_records", "ix_price_records_supplier_status_effective", ["supplier_id", "status", "effective_at"])
    _create_index_if_missing(inspector, "price_records", "ix_price_records_conflict_lookup", ["product_id", "supplier_id", "branch_id", "delivery_mode", "area_scope", "price_dimension", "status"])

    if bind.dialect.name == "postgresql":
        op.create_index(
            "ux_cost_formula_versions_formula_active",
            "cost_formula_versions",
            ["formula_id"],
            unique=True,
            postgresql_where=sa.text("is_active_version AND archived_at IS NULL"),
        )
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute(
            """
            ALTER TABLE price_records
            ADD CONSTRAINT ex_price_records_active_conflict
            EXCLUDE USING gist (
                product_id WITH =,
                supplier_id WITH =,
                branch_id WITH =,
                delivery_mode WITH =,
                area_scope WITH =,
                price_dimension WITH =,
                int4range(quantity_min, COALESCE(quantity_max, 2147483647), '[]') WITH &&,
                tstzrange(effective_at, COALESCE(expire_at, 'infinity'::timestamptz), '[)') WITH &&
            )
            WHERE (
                status = 'active'
                AND archived_at IS NULL
                AND replaced_by_price_record_id IS NULL
            )
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ux_cost_formula_versions_formula_active")
        op.execute("ALTER TABLE price_records DROP CONSTRAINT IF EXISTS ex_price_records_active_conflict")

    for table_name in [
        "price_records",
        "cost_formula_versions",
        "cost_formulas",
        "exchange_rate_snapshots",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
