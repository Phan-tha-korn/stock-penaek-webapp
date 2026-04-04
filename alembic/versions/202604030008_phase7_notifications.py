"""phase 7 notifications

Revision ID: 202604030008
Revises: 202604030007
Create Date: 2026-04-03 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202604030008"
down_revision = "202604030007"
branch_labels = None
depends_on = None


JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
NOTIFICATION_SEVERITY_ENUM = sa.Enum("low", "medium", "high", "critical", name="notificationseverity", native_enum=False)
NOTIFICATION_CHANNEL_ENUM = sa.Enum("line", "email", "discord", name="notificationchannel", native_enum=False)
NOTIFICATION_TYPE_ENUM = sa.Enum("immediate", "delayed", "retryable", name="notificationtype", native_enum=False)
NOTIFICATION_EVENT_STATUS_ENUM = sa.Enum("pending", "processed", "cancelled", name="notificationeventstatus", native_enum=False)
NOTIFICATION_OUTBOX_STATUS_ENUM = sa.Enum(
    "pending",
    "processing",
    "sent",
    "failed",
    "retry_scheduled",
    "cancelled",
    name="notificationoutboxstatus",
    native_enum=False,
)
NOTIFICATION_DELIVERY_STATUS_ENUM = sa.Enum("sent", "failed", "retry_scheduled", name="notificationdeliverystatus", native_enum=False)
NOTIFICATION_FAILURE_TYPE_ENUM = sa.Enum(
    "config_error",
    "network_error",
    "provider_error",
    "unexpected_error",
    name="notificationfailuretype",
    native_enum=False,
)
NOTIFICATION_ASSIGNMENT_MODE_ENUM = sa.Enum("role", "user", "address", name="notificationassignmentmode", native_enum=False)


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

    if not _has_table(inspector, "notification_events"):
        op.create_table(
            "notification_events",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("notification_type", NOTIFICATION_TYPE_ENUM, nullable=False, server_default="immediate"),
            sa.Column("source_domain", sa.String(length=64), nullable=False),
            sa.Column("source_entity_type", sa.String(length=64), nullable=False),
            sa.Column("source_entity_id", sa.String(length=36), nullable=True),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("severity", NOTIFICATION_SEVERITY_ENUM, nullable=False, server_default="low"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="25"),
            sa.Column("status", NOTIFICATION_EVENT_STATUS_ENUM, nullable=False, server_default="pending"),
            sa.Column("payload_json", JSON_VARIANT, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("triggered_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("related_request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("dedupe_key", name="uq_notification_events_dedupe_key"),
            sa.CheckConstraint("priority >= 0", name="ck_notification_events_priority_non_negative"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_notification_events_event_type", ["event_type"]),
        ("ix_notification_events_source_domain", ["source_domain"]),
        ("ix_notification_events_source_entity_type", ["source_entity_type"]),
        ("ix_notification_events_source_entity_id", ["source_entity_id"]),
        ("ix_notification_events_branch_id", ["branch_id"]),
        ("ix_notification_events_severity", ["severity"]),
        ("ix_notification_events_priority", ["priority"]),
        ("ix_notification_events_status", ["status"]),
        ("ix_notification_events_dedupe_key", ["dedupe_key"]),
        ("ix_notification_events_triggered_by_user_id", ["triggered_by_user_id"]),
        ("ix_notification_events_related_request_id", ["related_request_id"]),
        ("ix_notification_events_occurred_at", ["occurred_at"]),
        ("ix_notification_events_processed_at", ["processed_at"]),
        ("ix_notification_events_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "notification_events", index_name, cols)

    if not _has_table(inspector, "notification_outbox"):
        op.create_table(
            "notification_outbox",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("event_id", sa.String(length=36), sa.ForeignKey("notification_events.id"), nullable=False),
            sa.Column("channel", NOTIFICATION_CHANNEL_ENUM, nullable=False),
            sa.Column("assignment_mode", NOTIFICATION_ASSIGNMENT_MODE_ENUM, nullable=False, server_default="role"),
            sa.Column("recipient_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("recipient_address", sa.String(length=255), nullable=True),
            sa.Column("routing_role", sa.String(length=32), nullable=True),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("severity", NOTIFICATION_SEVERITY_ENUM, nullable=False, server_default="low"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="25"),
            sa.Column("status", NOTIFICATION_OUTBOX_STATUS_ENUM, nullable=False, server_default="pending"),
            sa.Column("message_title", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("message_body", sa.Text(), nullable=False, server_default=""),
            sa.Column("payload_json", JSON_VARIANT, nullable=False, server_default=sa.text("'{}'")),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("worker_token", sa.String(length=64), nullable=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="4"),
            sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
            sa.CheckConstraint("priority >= 0", name="ck_notification_outbox_priority_non_negative"),
            sa.CheckConstraint("attempt_count >= 0", name="ck_notification_outbox_attempt_count_non_negative"),
            sa.CheckConstraint("max_attempts >= 1", name="ck_notification_outbox_max_attempts_positive"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_notification_outbox_event_id", ["event_id"]),
        ("ix_notification_outbox_channel", ["channel"]),
        ("ix_notification_outbox_assignment_mode", ["assignment_mode"]),
        ("ix_notification_outbox_recipient_user_id", ["recipient_user_id"]),
        ("ix_notification_outbox_recipient_address", ["recipient_address"]),
        ("ix_notification_outbox_routing_role", ["routing_role"]),
        ("ix_notification_outbox_branch_id", ["branch_id"]),
        ("ix_notification_outbox_severity", ["severity"]),
        ("ix_notification_outbox_priority", ["priority"]),
        ("ix_notification_outbox_status", ["status"]),
        ("ix_notification_outbox_dedupe_key", ["dedupe_key"]),
        ("ix_notification_outbox_scheduled_at", ["scheduled_at"]),
        ("ix_notification_outbox_locked_at", ["locked_at"]),
        ("ix_notification_outbox_worker_token", ["worker_token"]),
        ("ix_notification_outbox_last_attempt_at", ["last_attempt_at"]),
        ("ix_notification_outbox_next_retry_at", ["next_retry_at"]),
        ("ix_notification_outbox_sent_at", ["sent_at"]),
        ("ix_notification_outbox_created_at", ["created_at"]),
        ("ix_notification_outbox_updated_at", ["updated_at"]),
        ("ix_notification_outbox_dispatch_lookup", ["status", "priority", "scheduled_at"]),
    ]:
        _create_index_if_missing(inspector, "notification_outbox", index_name, cols)

    if not _has_table(inspector, "notification_deliveries"):
        op.create_table(
            "notification_deliveries",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("outbox_id", sa.String(length=36), sa.ForeignKey("notification_outbox.id"), nullable=False),
            sa.Column("event_id", sa.String(length=36), sa.ForeignKey("notification_events.id"), nullable=False),
            sa.Column("channel", NOTIFICATION_CHANNEL_ENUM, nullable=False),
            sa.Column("delivery_status", NOTIFICATION_DELIVERY_STATUS_ENUM, nullable=False),
            sa.Column("provider_message_id", sa.String(length=255), nullable=True),
            sa.Column("response_code", sa.String(length=64), nullable=True),
            sa.Column("response_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_notification_deliveries_outbox_id", ["outbox_id"]),
        ("ix_notification_deliveries_event_id", ["event_id"]),
        ("ix_notification_deliveries_channel", ["channel"]),
        ("ix_notification_deliveries_delivery_status", ["delivery_status"]),
        ("ix_notification_deliveries_provider_message_id", ["provider_message_id"]),
        ("ix_notification_deliveries_sent_at", ["sent_at"]),
        ("ix_notification_deliveries_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "notification_deliveries", index_name, cols)

    if not _has_table(inspector, "notification_failures"):
        op.create_table(
            "notification_failures",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("outbox_id", sa.String(length=36), sa.ForeignKey("notification_outbox.id"), nullable=False),
            sa.Column("event_id", sa.String(length=36), sa.ForeignKey("notification_events.id"), nullable=False),
            sa.Column("failure_type", NOTIFICATION_FAILURE_TYPE_ENUM, nullable=False),
            sa.Column("failure_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_notification_failures_outbox_id", ["outbox_id"]),
        ("ix_notification_failures_event_id", ["event_id"]),
        ("ix_notification_failures_failure_type", ["failure_type"]),
        ("ix_notification_failures_retryable", ["retryable"]),
        ("ix_notification_failures_attempt_no", ["attempt_no"]),
        ("ix_notification_failures_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "notification_failures", index_name, cols)

    if not _has_table(inspector, "notification_preferences"):
        op.create_table(
            "notification_preferences",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("channel", NOTIFICATION_CHANNEL_ENUM, nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id", "channel", "event_type", "branch_id", name="uq_notification_preferences_scope"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_notification_preferences_user_id", ["user_id"]),
        ("ix_notification_preferences_channel", ["channel"]),
        ("ix_notification_preferences_event_type", ["event_type"]),
        ("ix_notification_preferences_branch_id", ["branch_id"]),
        ("ix_notification_preferences_is_enabled", ["is_enabled"]),
    ]:
        _create_index_if_missing(inspector, "notification_preferences", index_name, cols)

    if not _has_table(inspector, "notification_templates"):
        op.create_table(
            "notification_templates",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("channel", NOTIFICATION_CHANNEL_ENUM, nullable=False),
            sa.Column("title_template", sa.Text(), nullable=False, server_default=""),
            sa.Column("body_template", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("event_type", "channel", name="uq_notification_templates_event_channel"),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_notification_templates_event_type", ["event_type"]),
        ("ix_notification_templates_channel", ["channel"]),
        ("ix_notification_templates_is_active", ["is_active"]),
    ]:
        _create_index_if_missing(inspector, "notification_templates", index_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name in [
        "notification_templates",
        "notification_preferences",
        "notification_failures",
        "notification_deliveries",
        "notification_outbox",
        "notification_events",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
