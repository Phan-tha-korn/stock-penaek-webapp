"""phase 1 foundation

Revision ID: 202604030002
Revises: 202604030001
Create Date: 2026-04-03 12:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604030002"
down_revision = "202604030001"
branch_labels = None
depends_on = None


ROLE_ENUM = sa.Enum("STOCK", "ADMIN", "ACCOUNTANT", "OWNER", "DEV", name="role", native_enum=False)
ATTACHMENT_STORAGE_ENUM = sa.Enum("LOCAL", "OBJECT", name="attachmentstoragedriver", native_enum=False)
ATTACHMENT_STATUS_ENUM = sa.Enum("ACTIVE", "ARCHIVED", "DELETED", name="attachmentstatus", native_enum=False)
ATTACHMENT_MALWARE_ENUM = sa.Enum("PENDING", "CLEAN", "INFECTED", "FAILED", "SKIPPED", name="attachmentmalwarestatus", native_enum=False)
GROUP_LOCK_ENUM = sa.Enum("editable", "review_locked", "owner_locked", name="canonicalgrouplockstate", native_enum=False)
AUDIT_SEVERITY_ENUM = sa.Enum("info", "warning", "critical", name="auditseverity", native_enum=False)


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

    if not _has_table(inspector, "branches"):
        op.create_table(
            "branches",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "branches", "ix_branches_code", ["code"], unique=True)
    _create_index_if_missing(inspector, "branches", "ix_branches_name", ["name"])
    _create_index_if_missing(inspector, "branches", "ix_branches_is_default", ["is_default"])
    _create_index_if_missing(inspector, "branches", "ix_branches_is_active", ["is_active"])

    if not _has_table(inspector, "user_branch_scopes"):
        op.create_table(
            "user_branch_scopes",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=False),
            sa.Column("can_view", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("can_edit", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("scope_source", sa.String(length=32), nullable=False, server_default="system"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "branch_id", name="uq_user_branch_scope_user_branch"),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "user_branch_scopes", "ix_user_branch_scopes_user_id", ["user_id"])
    _create_index_if_missing(inspector, "user_branch_scopes", "ix_user_branch_scopes_branch_id", ["branch_id"])

    for column in [
        sa.Column("branch_id", sa.String(length=36), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_reason", sa.String(length=255), nullable=True),
    ]:
        if not _has_column(inspector, "products", column.name):
            op.add_column("products", column)
            inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "products", "ix_products_branch_id", ["branch_id"])
    _create_index_if_missing(inspector, "products", "ix_products_archived_at", ["archived_at"])
    _create_index_if_missing(inspector, "products", "ix_products_deleted_at", ["deleted_at"])

    for column in [
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delete_reason", sa.String(length=255), nullable=True),
    ]:
        if not _has_column(inspector, "product_categories", column.name):
            op.add_column("product_categories", column)
            inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "product_categories", "ix_product_categories_archived_at", ["archived_at"])
    _create_index_if_missing(inspector, "product_categories", "ix_product_categories_deleted_at", ["deleted_at"])

    if not _has_column(inspector, "stock_transactions", "branch_id"):
        op.add_column("stock_transactions", sa.Column("branch_id", sa.String(length=36), nullable=True))
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "stock_transactions", "ix_stock_transactions_branch_id", ["branch_id"])

    if not _has_column(inspector, "audit_logs", "branch_id"):
        op.add_column("audit_logs", sa.Column("branch_id", sa.String(length=36), nullable=True))
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "audit_logs", "ix_audit_logs_branch_id", ["branch_id"])

    if not _has_table(inspector, "entity_archives"):
        op.create_table(
            "entity_archives",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "entity_archives", "ix_entity_archives_entity_type", ["entity_type"])
    _create_index_if_missing(inspector, "entity_archives", "ix_entity_archives_entity_id", ["entity_id"])
    _create_index_if_missing(inspector, "entity_archives", "ix_entity_archives_branch_id", ["branch_id"])
    _create_index_if_missing(inspector, "entity_archives", "ix_entity_archives_actor_user_id", ["actor_user_id"])
    _create_index_if_missing(inspector, "entity_archives", "ix_entity_archives_created_at", ["created_at"])

    if not _has_table(inspector, "audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("audit_log_id", sa.String(length=36), sa.ForeignKey("audit_logs.id"), nullable=True),
            sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("actor_username", sa.String(length=64), nullable=True),
            sa.Column("actor_role", ROLE_ENUM, nullable=True),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("entity", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=True),
            sa.Column("severity", AUDIT_SEVERITY_ENUM, nullable=False, server_default="info"),
            sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("diff_summary", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("before_json", sa.Text(), nullable=True),
            sa.Column("after_json", sa.Text(), nullable=True),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_audit_events_audit_log_id", ["audit_log_id"]),
        ("ix_audit_events_actor_user_id", ["actor_user_id"]),
        ("ix_audit_events_actor_username", ["actor_username"]),
        ("ix_audit_events_actor_role", ["actor_role"]),
        ("ix_audit_events_branch_id", ["branch_id"]),
        ("ix_audit_events_action", ["action"]),
        ("ix_audit_events_entity", ["entity"]),
        ("ix_audit_events_entity_id", ["entity_id"]),
        ("ix_audit_events_severity", ["severity"]),
        ("ix_audit_events_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "audit_events", index_name, cols)

    if not _has_table(inspector, "attachments"):
        op.create_table(
            "attachments",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("storage_driver", ATTACHMENT_STORAGE_ENUM, nullable=False, server_default="LOCAL"),
            sa.Column("storage_bucket", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("storage_key", sa.String(length=1024), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("content_type", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("checksum_sha256", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("classification", sa.String(length=64), nullable=False, server_default="other"),
            sa.Column("status", ATTACHMENT_STATUS_ENUM, nullable=False, server_default="ACTIVE"),
            sa.Column("malware_status", ATTACHMENT_MALWARE_ENUM, nullable=False, server_default="PENDING"),
            sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_attachments_storage_key", ["storage_key"]),
        ("ix_attachments_checksum_sha256", ["checksum_sha256"]),
        ("ix_attachments_classification", ["classification"]),
        ("ix_attachments_status", ["status"]),
        ("ix_attachments_malware_status", ["malware_status"]),
        ("ix_attachments_owner_user_id", ["owner_user_id"]),
        ("ix_attachments_archived_at", ["archived_at"]),
        ("ix_attachments_deleted_at", ["deleted_at"]),
    ]:
        _create_index_if_missing(inspector, "attachments", index_name, cols)

    if not _has_table(inspector, "attachment_bindings"):
        op.create_table(
            "attachment_bindings",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("attachment_id", sa.String(length=36), sa.ForeignKey("attachments.id"), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=False),
            sa.Column("relation_type", sa.String(length=32), nullable=False, server_default="primary"),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("attachment_id", "entity_type", "entity_id", name="uq_attachment_binding_entity"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_attachment_bindings_attachment_id", ["attachment_id"]),
        ("ix_attachment_bindings_entity_type", ["entity_type"]),
        ("ix_attachment_bindings_entity_id", ["entity_id"]),
        ("ix_attachment_bindings_branch_id", ["branch_id"]),
        ("ix_attachment_bindings_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "attachment_bindings", index_name, cols)

    if not _has_table(inspector, "product_aliases"):
        op.create_table(
            "product_aliases",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("alias", sa.String(length=255), nullable=False),
            sa.Column("normalized_alias", sa.String(length=255), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("product_id", "normalized_alias", name="uq_product_alias_product_normalized"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_product_aliases_product_id", ["product_id"]),
        ("ix_product_aliases_normalized_alias", ["normalized_alias"]),
        ("ix_product_aliases_deleted_at", ["deleted_at"]),
    ]:
        _create_index_if_missing(inspector, "product_aliases", index_name, cols)

    if not _has_table(inspector, "tags"):
        op.create_table(
            "tags",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("normalized_name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "tags", "ix_tags_normalized_name", ["normalized_name"], unique=True)
    _create_index_if_missing(inspector, "tags", "ix_tags_archived_at", ["archived_at"])

    if not _has_table(inspector, "product_tag_links"):
        op.create_table(
            "product_tag_links",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("tag_id", sa.String(length=36), sa.ForeignKey("tags.id"), nullable=False),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("product_id", "tag_id", name="uq_product_tag_link"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_product_tag_links_product_id", ["product_id"]),
        ("ix_product_tag_links_tag_id", ["tag_id"]),
        ("ix_product_tag_links_deleted_at", ["deleted_at"]),
    ]:
        _create_index_if_missing(inspector, "product_tag_links", index_name, cols)

    if not _has_table(inspector, "product_specs"):
        op.create_table(
            "product_specs",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("spec_key", sa.String(length=128), nullable=False),
            sa.Column("spec_value", sa.Text(), nullable=False, server_default=""),
            sa.Column("value_type", sa.String(length=32), nullable=False, server_default="text"),
            sa.Column("unit", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_product_specs_product_id", ["product_id"]),
        ("ix_product_specs_spec_key", ["spec_key"]),
        ("ix_product_specs_deleted_at", ["deleted_at"]),
    ]:
        _create_index_if_missing(inspector, "product_specs", index_name, cols)

    if not _has_table(inspector, "canonical_product_groups"):
        op.create_table(
            "canonical_product_groups",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("system_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("lock_state", GROUP_LOCK_ENUM, nullable=False, server_default="editable"),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "canonical_product_groups", "ix_canonical_product_groups_code", ["code"], unique=True)
    _create_index_if_missing(inspector, "canonical_product_groups", "ix_canonical_product_groups_lock_state", ["lock_state"])
    _create_index_if_missing(inspector, "canonical_product_groups", "ix_canonical_product_groups_archived_at", ["archived_at"])

    if not _has_table(inspector, "canonical_group_members"):
        op.create_table(
            "canonical_group_members",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("group_id", sa.String(length=36), sa.ForeignKey("canonical_product_groups.id"), nullable=False),
            sa.Column("product_id", sa.String(length=36), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("group_id", "product_id", name="uq_canonical_group_product"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_canonical_group_members_group_id", ["group_id"]),
        ("ix_canonical_group_members_product_id", ["product_id"]),
        ("ix_canonical_group_members_archived_at", ["archived_at"]),
    ]:
        _create_index_if_missing(inspector, "canonical_group_members", index_name, cols)

    if not _has_table(inspector, "supplier_reliability_profiles"):
        op.create_table(
            "supplier_reliability_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("supplier_id", sa.String(length=36), nullable=True),
            sa.Column("legacy_supplier_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("legacy_supplier_key", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("overall_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("auto_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("price_competitiveness_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("purchase_frequency_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("delivery_reliability_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("data_completeness_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("verification_confidence_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("dispute_reject_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("dev_override_score", sa.Numeric(5, 2), nullable=True),
            sa.Column("owner_override_score", sa.Numeric(5, 2), nullable=True),
            sa.Column("override_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("overridden_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("legacy_supplier_key", name="uq_supplier_reliability_legacy_key"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols, unique in [
        ("ix_supplier_reliability_profiles_supplier_id", ["supplier_id"], False),
        ("ix_supplier_reliability_profiles_legacy_supplier_name", ["legacy_supplier_name"], False),
        ("ix_supplier_reliability_profiles_legacy_supplier_key", ["legacy_supplier_key"], True),
    ]:
        _create_index_if_missing(inspector, "supplier_reliability_profiles", index_name, cols, unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in [
        "supplier_reliability_profiles",
        "canonical_group_members",
        "canonical_product_groups",
        "product_specs",
        "product_tag_links",
        "tags",
        "product_aliases",
        "attachment_bindings",
        "attachments",
        "audit_events",
        "entity_archives",
        "user_branch_scopes",
        "branches",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
