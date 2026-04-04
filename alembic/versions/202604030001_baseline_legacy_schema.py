"""baseline legacy schema

Revision ID: 202604030001
Revises:
Create Date: 2026-04-03 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604030001"
down_revision = None
branch_labels = None
depends_on = None


ROLE_ENUM = sa.Enum("STOCK", "ADMIN", "ACCOUNTANT", "OWNER", "DEV", name="role", native_enum=False)
STOCK_STATUS_ENUM = sa.Enum("FULL", "NORMAL", "LOW", "CRITICAL", "OUT", "TEST", name="stockstatus", native_enum=False)
TXN_TYPE_ENUM = sa.Enum("STOCK_IN", "STOCK_OUT", "ADJUST", name="txntype", native_enum=False)


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

    if not _has_table(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("role", ROLE_ENUM, nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("language", sa.String(length=8), nullable=False, server_default="th"),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("totp_secret", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "users", "ix_users_username", ["username"], unique=True)
    _create_index_if_missing(inspector, "users", "ix_users_role", ["role"])
    _create_index_if_missing(inspector, "users", "ix_users_is_active", ["is_active"])

    if not _has_table(inspector, "refresh_sessions"):
        op.create_table(
            "refresh_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("jti", sa.String(length=64), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "refresh_sessions", "ix_refresh_sessions_user_id", ["user_id"])
    _create_index_if_missing(inspector, "refresh_sessions", "ix_refresh_sessions_jti", ["jti"], unique=True)
    _create_index_if_missing(inspector, "refresh_sessions", "ix_refresh_sessions_revoked", ["revoked"])
    _create_index_if_missing(inspector, "refresh_sessions", "ix_refresh_sessions_expires_at", ["expires_at"])

    if not _has_table(inspector, "login_locks"):
        op.create_table(
            "login_locks",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("ip", sa.String(length=64), nullable=False),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("username", "ip", name="uq_login_lock_username_ip"),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "login_locks", "ix_login_locks_username", ["username"])
    _create_index_if_missing(inspector, "login_locks", "ix_login_locks_ip", ["ip"])

    if not _has_table(inspector, "product_categories"):
        op.create_table(
            "product_categories",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "product_categories", "ix_product_categories_name", ["name"], unique=True)
    _create_index_if_missing(inspector, "product_categories", "ix_product_categories_is_deleted", ["is_deleted"])
    _create_index_if_missing(inspector, "product_categories", "ix_product_categories_sort_order", ["sort_order"])

    if not _has_table(inspector, "products"):
        op.create_table(
            "products",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("sku", sa.String(length=64), nullable=False),
            sa.Column("category_id", sa.String(length=36), nullable=True),
            sa.Column("last_category_id", sa.String(length=36), nullable=True),
            sa.Column("name_th", sa.String(length=255), nullable=False),
            sa.Column("name_en", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("type", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("unit", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("cost_price", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("selling_price", sa.Numeric(18, 3), nullable=True),
            sa.Column("stock_qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("min_stock", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("max_stock", sa.Numeric(18, 3), nullable=False, server_default="0"),
            sa.Column("status", STOCK_STATUS_ENUM, nullable=False),
            sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("supplier", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("barcode", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("image_url", sa.String(length=1024), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    else:
        if not _has_column(inspector, "products", "category_id"):
            op.add_column("products", sa.Column("category_id", sa.String(length=36), nullable=True))
        if not _has_column(inspector, "products", "last_category_id"):
            op.add_column("products", sa.Column("last_category_id", sa.String(length=36), nullable=True))
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "products", "ix_products_sku", ["sku"], unique=True)
    _create_index_if_missing(inspector, "products", "ix_products_category", ["category"])
    _create_index_if_missing(inspector, "products", "ix_products_status", ["status"])
    _create_index_if_missing(inspector, "products", "ix_products_is_test", ["is_test"])
    _create_index_if_missing(inspector, "products", "ix_products_barcode", ["barcode"])

    if not _has_table(inspector, "stock_transactions"):
        op.create_table(
            "stock_transactions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("type", TXN_TYPE_ENUM, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("sku", sa.String(length=64), nullable=False),
            sa.Column("qty", sa.Numeric(18, 3), nullable=False),
            sa.Column("unit_cost", sa.Numeric(18, 3), nullable=True),
            sa.Column("unit_price", sa.Numeric(18, 3), nullable=True),
            sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("approved_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "stock_transactions", "ix_stock_transactions_product_id", ["product_id"])
    _create_index_if_missing(inspector, "stock_transactions", "ix_stock_transactions_sku", ["sku"])
    _create_index_if_missing(inspector, "stock_transactions", "ix_stock_transactions_type", ["type"])

    if not _has_table(inspector, "audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("actor_username", sa.String(length=64), nullable=True),
            sa.Column("actor_role", ROLE_ENUM, nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("entity", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=True),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("before_json", sa.Text(), nullable=True),
            sa.Column("after_json", sa.Text(), nullable=True),
            sa.Column("message", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_actor_user_id", ["actor_user_id"])
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_actor_username", ["actor_username"])
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_actor_role", ["actor_role"])
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_action", ["action"])
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_entity", ["entity"])
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_entity_id", ["entity_id"])
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_created_at", ["created_at"])

    if not _has_table(inspector, "stock_alert_states"):
        op.create_table(
            "stock_alert_states",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("last_low_level_pct", sa.Integer(), nullable=True),
            sa.Column("last_high_level_pct", sa.Integer(), nullable=True),
            sa.Column("last_pct", sa.Numeric(8, 3), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("product_id", name="uq_stock_alert_product_id"),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "stock_alert_states", "ix_stock_alert_states_product_id", ["product_id"])


def downgrade() -> None:
    # Baseline is intentionally non-destructive for legacy databases.
    pass
