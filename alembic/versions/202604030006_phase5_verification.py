"""phase 5 verification workflow

Revision ID: 202604030006
Revises: 202604030005
Create Date: 2026-04-03 23:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202604030006"
down_revision = "202604030005"
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
ACTION_TYPE_ENUM = sa.Enum(
    "submit",
    "approve",
    "reject",
    "return_for_revision",
    "escalate",
    "cancel_request",
    "assign",
    "reassign",
    "comment",
    "mark_overdue",
    name="verificationactiontype",
    native_enum=False,
)
APPROVAL_STRATEGY_ENUM = sa.Enum(
    "domain_handler",
    "manual_follow_up",
    name="verificationapprovalstrategy",
    native_enum=False,
)
ASSIGNMENT_SOURCE_ENUM = sa.Enum(
    "manual",
    "auto",
    "escalation",
    "queue_default",
    name="verificationassignmentsource",
    native_enum=False,
)
ESCALATION_TYPE_ENUM = sa.Enum(
    "sla_overdue",
    "manual_escalate",
    "auto_reminder",
    name="verificationescalationtype",
    native_enum=False,
)
ALERT_STATE_ENUM = sa.Enum(
    "pending",
    "acknowledged",
    "resolved",
    name="verificationescalationalertstate",
    native_enum=False,
)
JSON_VARIANT = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "verification_requests"):
        op.create_table(
            "verification_requests",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_code", sa.String(length=32), nullable=False),
            sa.Column("workflow_status", WORKFLOW_STATUS_ENUM, nullable=False, server_default="pending"),
            sa.Column("risk_level", RISK_LEVEL_ENUM, nullable=False),
            sa.Column("risk_score", sa.Integer(), nullable=True),
            sa.Column("risk_flags_json", JSON_VARIANT, nullable=False),
            sa.Column("subject_domain", sa.String(length=64), nullable=False),
            sa.Column("queue_key", sa.String(length=64), nullable=False),
            sa.Column("priority_rank", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("safety_status", SAFETY_STATUS_ENUM, nullable=False, server_default="safe"),
            sa.Column("change_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("request_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("submitted_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assignee_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resolved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("supersedes_request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=True),
            sa.Column("origin_type", sa.String(length=64), nullable=True),
            sa.Column("origin_id", sa.String(length=36), nullable=True),
            sa.Column("dedupe_key", sa.String(length=255), nullable=True),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("dependency_warning_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_escalation_level", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sla_deadline_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("first_overdue_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_escalated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)", name="ck_verification_requests_risk_score_range"),
            sa.CheckConstraint("priority_rank >= 0", name="ck_verification_requests_priority_rank_non_negative"),
            sa.CheckConstraint("item_count >= 0", name="ck_verification_requests_item_count_non_negative"),
            sa.CheckConstraint("dependency_warning_count >= 0", name="ck_verification_requests_dependency_warning_count_non_negative"),
            sa.CheckConstraint("current_escalation_level >= 0", name="ck_verification_requests_current_escalation_level_non_negative"),
            sa.CheckConstraint(
                "(workflow_status NOT IN ('approved', 'rejected', 'returned_for_revision')) OR resolved_at IS NOT NULL",
                name="ck_verification_requests_resolved_requires_timestamp",
            ),
            sa.CheckConstraint(
                "(workflow_status <> 'cancelled') OR cancelled_at IS NOT NULL",
                name="ck_verification_requests_cancelled_requires_timestamp",
            ),
            sa.UniqueConstraint("request_code", name="uq_verification_requests_request_code"),
        )
        inspector = sa.inspect(bind)

    for index_name, cols in [
        ("ix_verification_requests_request_code", ["request_code"]),
        ("ix_verification_requests_workflow_status", ["workflow_status"]),
        ("ix_verification_requests_risk_level", ["risk_level"]),
        ("ix_verification_requests_risk_score", ["risk_score"]),
        ("ix_verification_requests_subject_domain", ["subject_domain"]),
        ("ix_verification_requests_queue_key", ["queue_key"]),
        ("ix_verification_requests_priority_rank", ["priority_rank"]),
        ("ix_verification_requests_safety_status", ["safety_status"]),
        ("ix_verification_requests_branch_id", ["branch_id"]),
        ("ix_verification_requests_requested_by_user_id", ["requested_by_user_id"]),
        ("ix_verification_requests_submitted_by_user_id", ["submitted_by_user_id"]),
        ("ix_verification_requests_assignee_user_id", ["assignee_user_id"]),
        ("ix_verification_requests_resolved_by_user_id", ["resolved_by_user_id"]),
        ("ix_verification_requests_supersedes_request_id", ["supersedes_request_id"]),
        ("ix_verification_requests_origin_type", ["origin_type"]),
        ("ix_verification_requests_origin_id", ["origin_id"]),
        ("ix_verification_requests_sla_deadline_at", ["sla_deadline_at"]),
        ("ix_verification_requests_first_overdue_at", ["first_overdue_at"]),
        ("ix_verification_requests_last_escalated_at", ["last_escalated_at"]),
        ("ix_verification_requests_last_action_at", ["last_action_at"]),
        ("ix_verification_requests_resolved_at", ["resolved_at"]),
        ("ix_verification_requests_cancelled_at", ["cancelled_at"]),
        ("ix_verification_requests_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "verification_requests", index_name, cols)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_verification_requests_pending_dedupe_key "
        "ON verification_requests (dedupe_key) "
        "WHERE dedupe_key IS NOT NULL AND workflow_status = 'pending'"
    )

    if not _has_table(inspector, "verification_request_items"):
        op.create_table(
            "verification_request_items",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=36), nullable=True),
            sa.Column("subject_key", sa.String(length=128), nullable=True),
            sa.Column("change_type", sa.String(length=64), nullable=False),
            sa.Column("handler_key", sa.String(length=128), nullable=False),
            sa.Column("entity_version_token", sa.String(length=128), nullable=True),
            sa.Column("approval_strategy", APPROVAL_STRATEGY_ENUM, nullable=False, server_default="domain_handler"),
            sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
            sa.Column("risk_level", RISK_LEVEL_ENUM, nullable=False),
            sa.Column("safety_status", SAFETY_STATUS_ENUM, nullable=False, server_default="safe"),
            sa.Column("before_json", JSON_VARIANT, nullable=True),
            sa.Column("proposed_after_json", JSON_VARIANT, nullable=True),
            sa.Column("handler_payload_json", JSON_VARIANT, nullable=False),
            sa.Column("diff_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("request_id", "sequence_no", name="uq_verification_request_items_request_sequence"),
            sa.CheckConstraint("entity_id IS NOT NULL OR subject_key IS NOT NULL", name="ck_verification_request_items_subject_required"),
            sa.CheckConstraint(
                "before_json IS NOT NULL OR proposed_after_json IS NOT NULL",
                name="ck_verification_request_items_state_payload_required",
            ),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_verification_request_items_request_id", ["request_id"]),
        ("ix_verification_request_items_entity_type", ["entity_type"]),
        ("ix_verification_request_items_entity_id", ["entity_id"]),
        ("ix_verification_request_items_subject_key", ["subject_key"]),
        ("ix_verification_request_items_change_type", ["change_type"]),
        ("ix_verification_request_items_handler_key", ["handler_key"]),
        ("ix_verification_request_items_approval_strategy", ["approval_strategy"]),
        ("ix_verification_request_items_branch_id", ["branch_id"]),
        ("ix_verification_request_items_risk_level", ["risk_level"]),
        ("ix_verification_request_items_safety_status", ["safety_status"]),
        ("ix_verification_request_items_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "verification_request_items", index_name, cols)

    if not _has_table(inspector, "verification_actions"):
        op.create_table(
            "verification_actions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=False),
            sa.Column("request_item_id", sa.String(length=36), sa.ForeignKey("verification_request_items.id"), nullable=True),
            sa.Column("action_type", ACTION_TYPE_ENUM, nullable=False),
            sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("from_status", WORKFLOW_STATUS_ENUM, nullable=True),
            sa.Column("to_status", WORKFLOW_STATUS_ENUM, nullable=True),
            sa.Column("action_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("comment", sa.Text(), nullable=False, server_default=""),
            sa.Column("decision_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("escalation_level_after", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata_json", JSON_VARIANT, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_verification_actions_request_id", ["request_id"]),
        ("ix_verification_actions_request_item_id", ["request_item_id"]),
        ("ix_verification_actions_action_type", ["action_type"]),
        ("ix_verification_actions_actor_user_id", ["actor_user_id"]),
        ("ix_verification_actions_from_status", ["from_status"]),
        ("ix_verification_actions_to_status", ["to_status"]),
        ("ix_verification_actions_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "verification_actions", index_name, cols)

    if not _has_table(inspector, "verification_assignments"):
        op.create_table(
            "verification_assignments",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=False),
            sa.Column("assigned_to_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assigned_role", sa.String(length=32), nullable=True),
            sa.Column("assigned_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assignment_source", ASSIGNMENT_SOURCE_ENUM, nullable=False, server_default="manual"),
            sa.Column("assignment_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_verification_assignments_request_id", ["request_id"]),
        ("ix_verification_assignments_assigned_to_user_id", ["assigned_to_user_id"]),
        ("ix_verification_assignments_assigned_role", ["assigned_role"]),
        ("ix_verification_assignments_assigned_by_user_id", ["assigned_by_user_id"]),
        ("ix_verification_assignments_assignment_source", ["assignment_source"]),
        ("ix_verification_assignments_started_at", ["started_at"]),
        ("ix_verification_assignments_ended_at", ["ended_at"]),
        ("ix_verification_assignments_is_current", ["is_current"]),
    ]:
        _create_index_if_missing(inspector, "verification_assignments", index_name, cols)
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_verification_assignments_current_request "
            "ON verification_assignments (request_id) "
            "WHERE is_current IS TRUE AND ended_at IS NULL"
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_verification_assignments_current_request "
            "ON verification_assignments (request_id) "
            "WHERE is_current = 1 AND ended_at IS NULL"
        )

    if not _has_table(inspector, "verification_dependency_warnings"):
        op.create_table(
            "verification_dependency_warnings",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=False),
            sa.Column("request_item_id", sa.String(length=36), sa.ForeignKey("verification_request_items.id"), nullable=True),
            sa.Column("dependency_type", sa.String(length=64), nullable=False),
            sa.Column("dependency_entity_type", sa.String(length=64), nullable=True),
            sa.Column("dependency_entity_id", sa.String(length=36), nullable=True),
            sa.Column("safety_status", SAFETY_STATUS_ENUM, nullable=False, server_default="warning"),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("detail_json", JSON_VARIANT, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_verification_dependency_warnings_request_id", ["request_id"]),
        ("ix_verification_dependency_warnings_request_item_id", ["request_item_id"]),
        ("ix_verification_dependency_warnings_dependency_type", ["dependency_type"]),
        ("ix_verification_dependency_warnings_dependency_entity_type", ["dependency_entity_type"]),
        ("ix_verification_dependency_warnings_dependency_entity_id", ["dependency_entity_id"]),
        ("ix_verification_dependency_warnings_safety_status", ["safety_status"]),
        ("ix_verification_dependency_warnings_created_at", ["created_at"]),
    ]:
        _create_index_if_missing(inspector, "verification_dependency_warnings", index_name, cols)

    if not _has_table(inspector, "verification_escalations"):
        op.create_table(
            "verification_escalations",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("request_id", sa.String(length=36), sa.ForeignKey("verification_requests.id"), nullable=False),
            sa.Column("escalation_type", ESCALATION_TYPE_ENUM, nullable=False),
            sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("triggered_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("previous_assignee_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("new_assignee_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("target_role", sa.String(length=32), nullable=True),
            sa.Column("alert_state", ALERT_STATE_ENUM, nullable=False, server_default="pending"),
            sa.Column("notification_hint_json", JSON_VARIANT, nullable=False),
            sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )
        inspector = sa.inspect(bind)
    for index_name, cols in [
        ("ix_verification_escalations_request_id", ["request_id"]),
        ("ix_verification_escalations_escalation_type", ["escalation_type"]),
        ("ix_verification_escalations_triggered_by_user_id", ["triggered_by_user_id"]),
        ("ix_verification_escalations_previous_assignee_user_id", ["previous_assignee_user_id"]),
        ("ix_verification_escalations_new_assignee_user_id", ["new_assignee_user_id"]),
        ("ix_verification_escalations_target_role", ["target_role"]),
        ("ix_verification_escalations_alert_state", ["alert_state"]),
        ("ix_verification_escalations_triggered_at", ["triggered_at"]),
        ("ix_verification_escalations_acknowledged_at", ["acknowledged_at"]),
        ("ix_verification_escalations_resolved_at", ["resolved_at"]),
    ]:
        _create_index_if_missing(inspector, "verification_escalations", index_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for index_name in [
        "ux_verification_assignments_current_request",
        "ux_verification_requests_pending_dedupe_key",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    for table_name in [
        "verification_escalations",
        "verification_dependency_warnings",
        "verification_assignments",
        "verification_actions",
        "verification_request_items",
        "verification_requests",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
