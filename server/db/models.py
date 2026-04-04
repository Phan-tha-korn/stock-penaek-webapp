from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


json_variant = JSON().with_variant(JSONB, "postgresql")


class Role(str, enum.Enum):
    STOCK = "STOCK"
    ADMIN = "ADMIN"
    ACCOUNTANT = "ACCOUNTANT"
    OWNER = "OWNER"
    DEV = "DEV"


class StockStatus(str, enum.Enum):
    FULL = "FULL"
    NORMAL = "NORMAL"
    LOW = "LOW"
    CRITICAL = "CRITICAL"
    OUT = "OUT"
    TEST = "TEST"


class TxnType(str, enum.Enum):
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    ADJUST = "ADJUST"


class AttachmentStorageDriver(str, enum.Enum):
    LOCAL = "LOCAL"
    OBJECT = "OBJECT"


class AttachmentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class AttachmentMalwareStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SupplierStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class SupplierProposalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class AttachmentScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    FAILED = "FAILED"


class CurrencyCode(str, enum.Enum):
    THB = "THB"
    USD = "USD"


class PriceRecordStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_VERIFY = "pending_verify"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REPLACED = "replaced"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class PriceSourceType(str, enum.Enum):
    ACTUAL_PURCHASE = "actual_purchase"
    SUPPLIER_QUOTE = "supplier_quote"
    PHONE_INQUIRY = "phone_inquiry"
    CHAT_CONFIRMATION = "chat_confirmation"
    MANUAL_ENTRY = "manual_entry"
    IMPORTED = "imported"
    ESTIMATED = "estimated"


class DeliveryMode(str, enum.Enum):
    STANDARD = "standard"
    EXPRESS = "express"
    PICKUP = "pickup"
    FREIGHT = "freight"


class AreaScope(str, enum.Enum):
    GLOBAL = "global"
    LOCAL = "local"
    BRANCH = "branch"
    CUSTOM = "custom"


class PriceDimension(str, enum.Enum):
    BASE_PRICE = "base_price"
    AFTER_VAT = "after_vat"
    WITH_SHIPPING = "with_shipping"
    REAL_TOTAL_COST = "real_total_cost"


class FormulaScopeType(str, enum.Enum):
    GLOBAL = "global"
    CATEGORY = "category"
    PRODUCT = "product"
    SUPPLIER = "supplier"
    BRANCH = "branch"
    AREA = "area"


class FormulaStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class CanonicalGroupLockState(str, enum.Enum):
    EDITABLE = "editable"
    REVIEW_LOCKED = "review_locked"
    OWNER_LOCKED = "owner_locked"


class MatchingGroupStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MatchingOperationType(str, enum.Enum):
    ADD_PRODUCT = "add_product"
    REMOVE_PRODUCT = "remove_product"
    MOVE_PRODUCT = "move_product"
    MERGE_GROUPS = "merge_groups"
    SPLIT_GROUP = "split_group"
    LOCK_CHANGE = "lock_change"
    REVERSE_OPERATION = "reverse_operation"


class MatchingOperationStatus(str, enum.Enum):
    COMPLETED = "completed"
    REVERSED = "reversed"
    CANCELLED = "cancelled"


class MatchingSnapshotSide(str, enum.Enum):
    BEFORE = "before"
    AFTER = "after"


class MatchingDependencyType(str, enum.Enum):
    PRICING = "pricing"
    SEARCH = "search"
    REPORTING = "reporting"


class MatchingDependencyStatus(str, enum.Enum):
    CLEAR = "clear"
    WARNING = "warning"
    BLOCKED = "blocked"


class VerificationWorkflowStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED_FOR_REVISION = "returned_for_revision"
    CANCELLED = "cancelled"


class VerificationRiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationSafetyStatus(str, enum.Enum):
    SAFE = "safe"
    WARNING = "warning"
    BLOCKED = "blocked"


class VerificationActionType(str, enum.Enum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    RETURN_FOR_REVISION = "return_for_revision"
    ESCALATE = "escalate"
    CANCEL_REQUEST = "cancel_request"
    ASSIGN = "assign"
    REASSIGN = "reassign"
    COMMENT = "comment"
    MARK_OVERDUE = "mark_overdue"


class VerificationApprovalStrategy(str, enum.Enum):
    DOMAIN_HANDLER = "domain_handler"
    MANUAL_FOLLOW_UP = "manual_follow_up"


class VerificationAssignmentSource(str, enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"
    ESCALATION = "escalation"
    QUEUE_DEFAULT = "queue_default"


class VerificationEscalationType(str, enum.Enum):
    SLA_OVERDUE = "sla_overdue"
    MANUAL_ESCALATE = "manual_escalate"
    AUTO_REMINDER = "auto_reminder"


class VerificationEscalationAlertState(str, enum.Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AuditSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationChannel(str, enum.Enum):
    LINE = "line"
    EMAIL = "email"
    DISCORD = "discord"


class NotificationType(str, enum.Enum):
    IMMEDIATE = "immediate"
    DELAYED = "delayed"
    RETRYABLE = "retryable"


class NotificationEventStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    CANCELLED = "cancelled"


class NotificationOutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    CANCELLED = "cancelled"


class NotificationDeliveryStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"


class NotificationFailureType(str, enum.Enum):
    CONFIG_ERROR = "config_error"
    NETWORK_ERROR = "network_error"
    PROVIDER_ERROR = "provider_error"
    UNEXPECTED_ERROR = "unexpected_error"


class NotificationAssignmentMode(str, enum.Enum):
    ROLE = "role"
    USER = "user"
    ADDRESS = "address"


class ReportSnapshotType(str, enum.Enum):
    REPORT = "report"
    AUDIT_BUNDLE = "audit_bundle"
    DECISION_TRACE = "decision_trace"
    HISTORICAL_COMPARE = "historical_compare"


class ReportSnapshotStatus(str, enum.Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReportSnapshotItemType(str, enum.Enum):
    VERIFICATION_STATE = "verification_state"
    REQUEST_ITEM = "request_item"
    DEPENDENCY_WARNING = "dependency_warning"
    PRICE_RECORD = "price_record"
    FORMULA_VERSION = "formula_version"
    SUPPLIER_STATE = "supplier_state"
    MATCHING_GROUP = "matching_group"
    PRODUCT_STATE = "product_state"


class ReportSnapshotLinkRole(str, enum.Enum):
    PRIMARY = "primary"
    RELATED = "related"
    DEPENDENCY = "dependency"


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="th")

    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class UserBranchScope(Base):
    __tablename__ = "user_branch_scopes"
    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branch_scope_user_branch"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), ForeignKey("branches.id"), index=True)
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_source: Mapped[str] = mapped_column(String(32), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship(User)
    branch: Mapped[Branch] = relationship(Branch)


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    delete_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship(User)


class LoginLock(Base):
    __tablename__ = "login_locks"
    __table_args__ = (UniqueConstraint("username", "ip", name="uq_login_lock_username_ip"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(64), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    category_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    last_category_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    name_th: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[str] = mapped_column(String(255), default="")
    unit: Mapped[str] = mapped_column(String(32))
    cost_price: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    selling_price: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    stock_qty: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    min_stock: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    max_stock: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    status: Mapped[StockStatus] = mapped_column(Enum(StockStatus, native_enum=False), index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    supplier: Mapped[str] = mapped_column(String(255), default="")
    barcode: Mapped[str] = mapped_column(String(255), default="", index=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    delete_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    creator: Mapped[User] = relationship(User)
    branch: Mapped[Branch | None] = relationship(Branch)


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (UniqueConstraint("product_id", "normalized_alias", name="uq_product_alias_product_normalized"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    alias: Mapped[str] = mapped_column(String(255))
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    normalized_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ProductTagLink(Base):
    __tablename__ = "product_tag_links"
    __table_args__ = (UniqueConstraint("product_id", "tag_id", name="uq_product_tag_link"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id"), index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ProductSpec(Base):
    __tablename__ = "product_specs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    spec_key: Mapped[str] = mapped_column(String(128), index=True)
    spec_value: Mapped[str] = mapped_column(Text, default="")
    value_type: Mapped[str] = mapped_column(String(32), default="text")
    unit: Mapped[str] = mapped_column(String(32), default="")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class CanonicalProductGroup(Base):
    __tablename__ = "canonical_product_groups"
    __table_args__ = (
        CheckConstraint("version_no >= 1", name="ck_canonical_product_groups_version_no_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    system_name: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[MatchingGroupStatus] = mapped_column(
        Enum(MatchingGroupStatus, native_enum=False, values_callable=enum_values),
        default=MatchingGroupStatus.ACTIVE,
        index=True,
    )
    lock_state: Mapped[CanonicalGroupLockState] = mapped_column(
        Enum(CanonicalGroupLockState, native_enum=False, values_callable=enum_values),
        default=CanonicalGroupLockState.EDITABLE,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    merged_into_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), nullable=True, index=True)
    last_operation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("matching_operations.id"), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    archived_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    archive_reason: Mapped[str] = mapped_column(Text, default="")


class CanonicalGroupMember(Base):
    __tablename__ = "canonical_group_members"
    __table_args__ = (
        Index(
            "ux_canonical_group_members_active_product",
            "product_id",
            unique=True,
            sqlite_where=text("removed_at IS NULL AND archived_at IS NULL"),
            postgresql_where=text("removed_at IS NULL AND archived_at IS NULL"),
        ),
        Index(
            "ux_canonical_group_members_active_group_product",
            "group_id",
            "product_id",
            unique=True,
            sqlite_where=text("removed_at IS NULL AND archived_at IS NULL"),
            postgresql_where=text("removed_at IS NULL AND archived_at IS NULL"),
        ),
        Index(
            "ux_canonical_group_members_active_primary_group",
            "group_id",
            unique=True,
            sqlite_where=text("is_primary = 1 AND removed_at IS NULL AND archived_at IS NULL"),
            postgresql_where=text("is_primary AND removed_at IS NULL AND archived_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    assigned_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    source_operation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("matching_operations.id"), nullable=True, index=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    removed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    end_operation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("matching_operations.id"), nullable=True, index=True)
    removal_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class MatchingOperation(Base):
    __tablename__ = "matching_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    operation_type: Mapped[MatchingOperationType] = mapped_column(
        Enum(MatchingOperationType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    status: Mapped[MatchingOperationStatus] = mapped_column(
        Enum(MatchingOperationStatus, native_enum=False, values_callable=enum_values),
        default=MatchingOperationStatus.COMPLETED,
        index=True,
    )
    source_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), nullable=True, index=True)
    target_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), nullable=True, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    before_snapshot_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    after_snapshot_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    reversal_of_operation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("matching_operations.id"), nullable=True, index=True)
    reversed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    dependency_status: Mapped[MatchingDependencyStatus] = mapped_column(
        Enum(MatchingDependencyStatus, native_enum=False, values_callable=enum_values),
        default=MatchingDependencyStatus.CLEAR,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class MatchingOperationGroupState(Base):
    __tablename__ = "matching_operation_group_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("matching_operations.id"), index=True)
    snapshot_side: Mapped[MatchingSnapshotSide] = mapped_column(
        Enum(MatchingSnapshotSide, native_enum=False, values_callable=enum_values),
        index=True,
    )
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[MatchingGroupStatus] = mapped_column(
        Enum(MatchingGroupStatus, native_enum=False, values_callable=enum_values),
        default=MatchingGroupStatus.ACTIVE,
        index=True,
    )
    lock_state: Mapped[CanonicalGroupLockState] = mapped_column(
        Enum(CanonicalGroupLockState, native_enum=False, values_callable=enum_values),
        default=CanonicalGroupLockState.EDITABLE,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    merged_into_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), nullable=True, index=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class MatchingOperationMembershipState(Base):
    __tablename__ = "matching_operation_membership_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("matching_operations.id"), index=True)
    snapshot_side: Mapped[MatchingSnapshotSide] = mapped_column(
        Enum(MatchingSnapshotSide, native_enum=False, values_callable=enum_values),
        index=True,
    )
    membership_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("canonical_group_members.id"), nullable=True, index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("canonical_product_groups.id"), nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    active_flag: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class MatchingDependencyCheck(Base):
    __tablename__ = "matching_dependency_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("matching_operations.id"), index=True)
    dependency_type: Mapped[MatchingDependencyType] = mapped_column(
        Enum(MatchingDependencyType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    check_status: Mapped[MatchingDependencyStatus] = mapped_column(
        Enum(MatchingDependencyStatus, native_enum=False, values_callable=enum_values),
        default=MatchingDependencyStatus.CLEAR,
        index=True,
    )
    affected_entity_count: Mapped[int] = mapped_column(Integer, default=0)
    detail_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class VerificationRequest(Base):
    __tablename__ = "verification_requests"
    __table_args__ = (
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)", name="ck_verification_requests_risk_score_range"),
        CheckConstraint("priority_rank >= 0", name="ck_verification_requests_priority_rank_non_negative"),
        CheckConstraint("item_count >= 0", name="ck_verification_requests_item_count_non_negative"),
        CheckConstraint(
            "dependency_warning_count >= 0",
            name="ck_verification_requests_dependency_warning_count_non_negative",
        ),
        CheckConstraint(
            "current_escalation_level >= 0",
            name="ck_verification_requests_current_escalation_level_non_negative",
        ),
        CheckConstraint(
            "(workflow_status <> 'approved' AND workflow_status <> 'rejected' AND workflow_status <> 'returned_for_revision') "
            "OR resolved_at IS NOT NULL",
            name="ck_verification_requests_resolved_requires_timestamp",
        ),
        CheckConstraint(
            "(workflow_status <> 'cancelled') OR cancelled_at IS NOT NULL",
            name="ck_verification_requests_cancelled_requires_timestamp",
        ),
        Index(
            "ux_verification_requests_pending_dedupe_key",
            "dedupe_key",
            unique=True,
            sqlite_where=text("dedupe_key IS NOT NULL AND workflow_status = 'pending'"),
            postgresql_where=text("dedupe_key IS NOT NULL AND workflow_status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    workflow_status: Mapped[VerificationWorkflowStatus] = mapped_column(
        Enum(VerificationWorkflowStatus, native_enum=False, values_callable=enum_values),
        default=VerificationWorkflowStatus.PENDING,
        index=True,
    )
    risk_level: Mapped[VerificationRiskLevel] = mapped_column(
        Enum(VerificationRiskLevel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    risk_flags_json: Mapped[list] = mapped_column(json_variant, default=list)
    subject_domain: Mapped[str] = mapped_column(String(64), index=True)
    queue_key: Mapped[str] = mapped_column(String(64), index=True)
    priority_rank: Mapped[int] = mapped_column(Integer, default=0, index=True)
    safety_status: Mapped[VerificationSafetyStatus] = mapped_column(
        Enum(VerificationSafetyStatus, native_enum=False, values_callable=enum_values),
        default=VerificationSafetyStatus.SAFE,
        index=True,
    )
    change_summary: Mapped[str] = mapped_column(Text, default="")
    request_reason: Mapped[str] = mapped_column(Text, default="")
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    submitted_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    supersedes_request_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("verification_requests.id"),
        nullable=True,
        index=True,
    )
    origin_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    origin_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    dependency_warning_count: Mapped[int] = mapped_column(Integer, default=0)
    current_escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    sla_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    first_overdue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class VerificationRequestItem(Base):
    __tablename__ = "verification_request_items"
    __table_args__ = (
        UniqueConstraint("request_id", "sequence_no", name="uq_verification_request_items_request_sequence"),
        CheckConstraint(
            "entity_id IS NOT NULL OR subject_key IS NOT NULL",
            name="ck_verification_request_items_subject_required",
        ),
        CheckConstraint(
            "before_json IS NOT NULL OR proposed_after_json IS NOT NULL",
            name="ck_verification_request_items_state_payload_required",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("verification_requests.id"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    subject_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(64), index=True)
    handler_key: Mapped[str] = mapped_column(String(128), index=True)
    entity_version_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_strategy: Mapped[VerificationApprovalStrategy] = mapped_column(
        Enum(VerificationApprovalStrategy, native_enum=False, values_callable=enum_values),
        default=VerificationApprovalStrategy.DOMAIN_HANDLER,
        index=True,
    )
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    risk_level: Mapped[VerificationRiskLevel] = mapped_column(
        Enum(VerificationRiskLevel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    safety_status: Mapped[VerificationSafetyStatus] = mapped_column(
        Enum(VerificationSafetyStatus, native_enum=False, values_callable=enum_values),
        default=VerificationSafetyStatus.SAFE,
        index=True,
    )
    before_json: Mapped[dict | None] = mapped_column(json_variant, nullable=True)
    proposed_after_json: Mapped[dict | None] = mapped_column(json_variant, nullable=True)
    handler_payload_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    diff_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class VerificationAction(Base):
    __tablename__ = "verification_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("verification_requests.id"), index=True)
    request_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("verification_request_items.id"), nullable=True, index=True)
    action_type: Mapped[VerificationActionType] = mapped_column(
        Enum(VerificationActionType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    from_status: Mapped[VerificationWorkflowStatus | None] = mapped_column(
        Enum(VerificationWorkflowStatus, native_enum=False, values_callable=enum_values),
        nullable=True,
        index=True,
    )
    to_status: Mapped[VerificationWorkflowStatus | None] = mapped_column(
        Enum(VerificationWorkflowStatus, native_enum=False, values_callable=enum_values),
        nullable=True,
        index=True,
    )
    action_reason: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    decision_summary: Mapped[str] = mapped_column(Text, default="")
    escalation_level_after: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class VerificationAssignment(Base):
    __tablename__ = "verification_assignments"
    __table_args__ = (
        Index(
            "ux_verification_assignments_current_request",
            "request_id",
            unique=True,
            sqlite_where=text("is_current = 1 AND ended_at IS NULL"),
            postgresql_where=text("is_current IS TRUE AND ended_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("verification_requests.id"), index=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    assigned_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    assignment_source: Mapped[VerificationAssignmentSource] = mapped_column(
        Enum(VerificationAssignmentSource, native_enum=False, values_callable=enum_values),
        default=VerificationAssignmentSource.MANUAL,
        index=True,
    )
    assignment_reason: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class VerificationDependencyWarning(Base):
    __tablename__ = "verification_dependency_warnings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("verification_requests.id"), index=True)
    request_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("verification_request_items.id"), nullable=True, index=True)
    dependency_type: Mapped[str] = mapped_column(String(64), index=True)
    dependency_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dependency_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    safety_status: Mapped[VerificationSafetyStatus] = mapped_column(
        Enum(VerificationSafetyStatus, native_enum=False, values_callable=enum_values),
        default=VerificationSafetyStatus.WARNING,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, default="")
    detail_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class VerificationEscalation(Base):
    __tablename__ = "verification_escalations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("verification_requests.id"), index=True)
    escalation_type: Mapped[VerificationEscalationType] = mapped_column(
        Enum(VerificationEscalationType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    triggered_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    previous_assignee_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    new_assignee_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    target_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    alert_state: Mapped[VerificationEscalationAlertState] = mapped_column(
        Enum(VerificationEscalationAlertState, native_enum=False, values_callable=enum_values),
        default=VerificationEscalationAlertState.PENDING,
        index=True,
    )
    notification_hint_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class CatalogSearchDocument(Base):
    __tablename__ = "catalog_search_documents"
    __table_args__ = (UniqueConstraint("product_id", name="uq_catalog_search_documents_product"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    canonical_group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("canonical_product_groups.id"),
        nullable=True,
        index=True,
    )
    canonical_group_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    name_th: Mapped[str] = mapped_column(String(255), default="", index=True)
    name_en: Mapped[str] = mapped_column(String(255), default="", index=True)
    category_text: Mapped[str] = mapped_column(String(255), default="", index=True)
    alias_text: Mapped[str] = mapped_column(Text, default="")
    tag_text: Mapped[str] = mapped_column(Text, default="")
    supplier_text: Mapped[str] = mapped_column(Text, default="")
    search_text: Mapped[str] = mapped_column(Text, default="")
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    active_price_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_supplier_count: Mapped[int] = mapped_column(Integer, default=0)
    latest_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    latest_price_record_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("price_records.id"), nullable=True, index=True)
    latest_normalized_amount_thb: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    latest_final_total_cost_thb: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True, index=True)
    cheapest_active_price_record_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("price_records.id"),
        nullable=True,
        index=True,
    )
    cheapest_active_normalized_amount_thb: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cheapest_active_final_total_cost_thb: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class PriceSearchProjection(Base):
    __tablename__ = "price_search_projections"
    __table_args__ = (UniqueConstraint("price_record_id", name="uq_price_search_projections_price_record"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    price_record_id: Mapped[str] = mapped_column(String(36), ForeignKey("price_records.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), ForeignKey("branches.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    canonical_group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("canonical_product_groups.id"),
        nullable=True,
        index=True,
    )
    canonical_group_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    product_name_th: Mapped[str] = mapped_column(String(255), default="", index=True)
    product_name_en: Mapped[str] = mapped_column(String(255), default="", index=True)
    category_text: Mapped[str] = mapped_column(String(255), default="", index=True)
    tag_text: Mapped[str] = mapped_column(Text, default="")
    supplier_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    supplier_is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    supplier_effective_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, index=True)
    status: Mapped[PriceRecordStatus] = mapped_column(
        Enum(PriceRecordStatus, native_enum=False, values_callable=enum_values),
        index=True,
    )
    source_type: Mapped[PriceSourceType] = mapped_column(
        Enum(PriceSourceType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    delivery_mode: Mapped[str] = mapped_column(String(64), default=DeliveryMode.STANDARD.value, index=True)
    area_scope: Mapped[str] = mapped_column(String(128), default=AreaScope.GLOBAL.value, index=True)
    price_dimension: Mapped[str] = mapped_column(String(64), default=PriceDimension.REAL_TOTAL_COST.value, index=True)
    quantity_min: Mapped[int] = mapped_column(Integer, index=True)
    quantity_max: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    original_currency: Mapped[CurrencyCode] = mapped_column(
        Enum(CurrencyCode, native_enum=False, values_callable=enum_values),
        index=True,
    )
    normalized_currency: Mapped[CurrencyCode] = mapped_column(
        Enum(CurrencyCode, native_enum=False, values_callable=enum_values),
        default=CurrencyCode.THB,
        index=True,
    )
    normalized_amount_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0, index=True)
    vat_amount_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    shipping_cost_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    fuel_cost_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    labor_cost_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    utility_cost_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    supplier_fee_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    discount_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    final_total_cost_thb: Mapped[float] = mapped_column(Numeric(18, 6), default=0, index=True)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class VerificationQueueProjection(Base):
    __tablename__ = "verification_queue_projections"
    __table_args__ = (UniqueConstraint("request_id", name="uq_verification_queue_projections_request"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("verification_requests.id"), index=True)
    request_code: Mapped[str] = mapped_column(String(32), index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    workflow_status: Mapped[VerificationWorkflowStatus] = mapped_column(
        Enum(VerificationWorkflowStatus, native_enum=False, values_callable=enum_values),
        index=True,
    )
    risk_level: Mapped[VerificationRiskLevel] = mapped_column(
        Enum(VerificationRiskLevel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    subject_domain: Mapped[str] = mapped_column(String(64), index=True)
    queue_key: Mapped[str] = mapped_column(String(64), index=True)
    safety_status: Mapped[VerificationSafetyStatus] = mapped_column(
        Enum(VerificationSafetyStatus, native_enum=False, values_callable=enum_values),
        index=True,
    )
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    assignee_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    dependency_warning_count: Mapped[int] = mapped_column(Integer, default=0)
    current_escalation_level: Mapped[int] = mapped_column(Integer, default=0, index=True)
    has_blocking_dependency: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    primary_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    primary_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    latest_action_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    latest_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sla_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    search_text: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class NotificationEvent(Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_events_dedupe_key"),
        CheckConstraint("priority >= 0", name="ck_notification_events_priority_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, native_enum=False, values_callable=enum_values),
        default=NotificationType.IMMEDIATE,
        index=True,
    )
    source_domain: Mapped[str] = mapped_column(String(64), index=True)
    source_entity_type: Mapped[str] = mapped_column(String(64), index=True)
    source_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    severity: Mapped[NotificationSeverity] = mapped_column(
        Enum(NotificationSeverity, native_enum=False, values_callable=enum_values),
        default=NotificationSeverity.LOW,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=25, index=True)
    status: Mapped[NotificationEventStatus] = mapped_column(
        Enum(NotificationEventStatus, native_enum=False, values_callable=enum_values),
        default=NotificationEventStatus.PENDING,
        index=True,
    )
    payload_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    triggered_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    related_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("verification_requests.id"), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe_key"),
        CheckConstraint("priority >= 0", name="ck_notification_outbox_priority_non_negative"),
        CheckConstraint("attempt_count >= 0", name="ck_notification_outbox_attempt_count_non_negative"),
        CheckConstraint("max_attempts >= 1", name="ck_notification_outbox_max_attempts_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("notification_events.id"), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    assignment_mode: Mapped[NotificationAssignmentMode] = mapped_column(
        Enum(NotificationAssignmentMode, native_enum=False, values_callable=enum_values),
        default=NotificationAssignmentMode.ROLE,
        index=True,
    )
    recipient_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    recipient_address: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    routing_role: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    severity: Mapped[NotificationSeverity] = mapped_column(
        Enum(NotificationSeverity, native_enum=False, values_callable=enum_values),
        default=NotificationSeverity.LOW,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=25, index=True)
    status: Mapped[NotificationOutboxStatus] = mapped_column(
        Enum(NotificationOutboxStatus, native_enum=False, values_callable=enum_values),
        default=NotificationOutboxStatus.PENDING,
        index=True,
    )
    message_title: Mapped[str] = mapped_column(String(255), default="")
    message_body: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(255), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    worker_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    outbox_id: Mapped[str] = mapped_column(String(36), ForeignKey("notification_outbox.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("notification_events.id"), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        Enum(NotificationDeliveryStatus, native_enum=False, values_callable=enum_values),
        index=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    response_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_summary: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class NotificationFailure(Base):
    __tablename__ = "notification_failures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    outbox_id: Mapped[str] = mapped_column(String(36), ForeignKey("notification_outbox.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("notification_events.id"), index=True)
    failure_type: Mapped[NotificationFailureType] = mapped_column(
        Enum(NotificationFailureType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    failure_message: Mapped[str] = mapped_column(Text, default="")
    retryable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "channel",
            "event_type",
            "branch_id",
            name="uq_notification_preferences_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    __table_args__ = (UniqueConstraint("event_type", "channel", name="uq_notification_templates_event_channel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, values_callable=enum_values),
        index=True,
    )
    title_template: Mapped[str] = mapped_column(Text, default="")
    body_template: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_code", name="uq_report_snapshots_snapshot_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    snapshot_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    snapshot_type: Mapped[ReportSnapshotType] = mapped_column(
        Enum(ReportSnapshotType, native_enum=False, values_callable=enum_values),
        default=ReportSnapshotType.DECISION_TRACE,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(64), index=True)
    scope_ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    as_of_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    period_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    period_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    generation_reason: Mapped[str] = mapped_column(Text, default="")
    generated_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    source_consistency_token: Mapped[str] = mapped_column(String(255), default="", index=True)
    status: Mapped[ReportSnapshotStatus] = mapped_column(
        Enum(ReportSnapshotStatus, native_enum=False, values_callable=enum_values),
        default=ReportSnapshotStatus.COMPLETED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class ReportSnapshotItem(Base):
    __tablename__ = "report_snapshot_items"
    __table_args__ = (Index("ix_report_snapshot_items_snapshot_item_type", "snapshot_id", "item_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("report_snapshots.id"), index=True)
    item_type: Mapped[ReportSnapshotItemType] = mapped_column(
        Enum(ReportSnapshotItemType, native_enum=False, values_callable=enum_values),
        index=True,
    )
    source_entity_type: Mapped[str] = mapped_column(String(64), index=True)
    source_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_version_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class ReportSnapshotLink(Base):
    __tablename__ = "report_snapshot_links"
    __table_args__ = (Index("ix_report_snapshot_links_snapshot_role", "snapshot_id", "link_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    snapshot_id: Mapped[str] = mapped_column(String(36), ForeignKey("report_snapshots.id"), index=True)
    linked_entity_type: Mapped[str] = mapped_column(String(64), index=True)
    linked_entity_id: Mapped[str] = mapped_column(String(36), index=True)
    link_role: Mapped[ReportSnapshotLinkRole] = mapped_column(
        Enum(ReportSnapshotLinkRole, native_enum=False, values_callable=enum_values),
        default=ReportSnapshotLinkRole.RELATED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class SupplierReliabilityProfile(Base):
    __tablename__ = "supplier_reliability_profiles"
    __table_args__ = (UniqueConstraint("legacy_supplier_key", name="uq_supplier_reliability_legacy_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    legacy_supplier_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    legacy_supplier_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    auto_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    price_competitiveness_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    purchase_frequency_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    delivery_reliability_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    data_completeness_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    verification_confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    dispute_reject_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    dev_override_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    owner_override_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    override_reason: Mapped[str] = mapped_column(Text, default="")
    overridden_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(64), default="")
    line_id: Mapped[str] = mapped_column(String(255), default="")
    facebook_url: Mapped[str] = mapped_column(String(1024), default="")
    website_url: Mapped[str] = mapped_column(String(1024), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    pickup_notes: Mapped[str] = mapped_column(Text, default="")
    source_details: Mapped[str] = mapped_column(Text, default="")
    purchase_history_notes: Mapped[str] = mapped_column(Text, default="")
    reliability_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[SupplierStatus] = mapped_column(Enum(SupplierStatus, native_enum=False), default=SupplierStatus.ACTIVE, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    delete_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplierContact(Base):
    __tablename__ = "supplier_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    contact_type: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    value: Mapped[str] = mapped_column(String(1024), default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class SupplierLink(Base):
    __tablename__ = "supplier_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    link_type: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class SupplierPickupPoint(Base):
    __tablename__ = "supplier_pickup_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[str] = mapped_column(Text, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class SupplierProductLink(Base):
    __tablename__ = "supplier_product_links"
    __table_args__ = (UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product_link"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    legacy_supplier_name: Mapped[str] = mapped_column(String(255), default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class SupplierReliabilityScore(Base):
    __tablename__ = "supplier_reliability_scores"
    __table_args__ = (UniqueConstraint("supplier_id", name="uq_supplier_reliability_score_supplier"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    auto_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    effective_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SupplierReliabilityBreakdown(Base):
    __tablename__ = "supplier_reliability_breakdowns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_score_id: Mapped[str] = mapped_column(String(36), ForeignKey("supplier_reliability_scores.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    score_value: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    weight: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    detail_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SupplierChangeProposal(Base):
    __tablename__ = "supplier_change_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    supplier_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[SupplierProposalStatus] = mapped_column(Enum(SupplierProposalStatus, native_enum=False), default=SupplierProposalStatus.PENDING, index=True)
    proposed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    approved_supplier_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=True, index=True)
    requires_dev_review: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    proposed_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ExchangeRateSnapshot(Base):
    __tablename__ = "exchange_rate_snapshots"
    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", "captured_at", name="uq_exchange_rate_snapshot_pair_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    base_currency: Mapped[CurrencyCode] = mapped_column(Enum(CurrencyCode, native_enum=False, values_callable=enum_values), index=True)
    quote_currency: Mapped[CurrencyCode] = mapped_column(Enum(CurrencyCode, native_enum=False, values_callable=enum_values), index=True)
    rate_value: Mapped[float] = mapped_column(Numeric(18, 8), default=1)
    source_name: Mapped[str] = mapped_column(String(64), default="manual")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class CostFormula(Base):
    __tablename__ = "cost_formulas"
    __table_args__ = (
        UniqueConstraint("code", name="uq_cost_formula_code"),
        CheckConstraint(
            "(scope_type = 'global' AND scope_ref_id IS NULL) OR (scope_type <> 'global' AND scope_ref_id IS NOT NULL)",
            name="ck_cost_formulas_scope_ref_required",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    scope_type: Mapped[FormulaScopeType] = mapped_column(Enum(FormulaScopeType, native_enum=False, values_callable=enum_values), index=True)
    scope_ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[FormulaStatus] = mapped_column(Enum(FormulaStatus, native_enum=False, values_callable=enum_values), default=FormulaStatus.DRAFT, index=True)
    active_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cost_formula_versions.id"), nullable=True, index=True)
    warning_on_change: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class CostFormulaVersion(Base):
    __tablename__ = "cost_formula_versions"
    __table_args__ = (
        UniqueConstraint("formula_id", "version_no", name="uq_cost_formula_version_formula_version_no"),
        CheckConstraint("version_no >= 1", name="ck_cost_formula_versions_version_no_positive"),
        CheckConstraint(
            "(NOT is_active_version) OR (is_locked AND activated_at IS NOT NULL)",
            name="ck_cost_formula_versions_active_locked",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    formula_id: Mapped[str] = mapped_column(String(36), ForeignKey("cost_formulas.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    expression_text: Mapped[str] = mapped_column(Text)
    variables_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    constants_json: Mapped[dict] = mapped_column(json_variant, default=dict)
    dependency_keys_json: Mapped[list] = mapped_column(json_variant, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active_version: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    replaced_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cost_formula_versions.id"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class PriceRecord(Base):
    __tablename__ = "price_records"
    __table_args__ = (
        CheckConstraint("quantity_min >= 1", name="ck_price_records_quantity_min_positive"),
        CheckConstraint("quantity_max IS NULL OR quantity_max >= quantity_min", name="ck_price_records_quantity_range_valid"),
        CheckConstraint("exchange_rate > 0", name="ck_price_records_exchange_rate_positive"),
        CheckConstraint("vat_percent >= 0 AND vat_percent <= 100", name="ck_price_records_vat_percent_range"),
        CheckConstraint("original_amount >= 0", name="ck_price_records_original_amount_non_negative"),
        CheckConstraint("normalized_amount >= 0", name="ck_price_records_normalized_amount_non_negative"),
        CheckConstraint("base_price >= 0", name="ck_price_records_base_price_non_negative"),
        CheckConstraint("vat_amount >= 0", name="ck_price_records_vat_amount_non_negative"),
        CheckConstraint("shipping_cost >= 0", name="ck_price_records_shipping_cost_non_negative"),
        CheckConstraint("fuel_cost >= 0", name="ck_price_records_fuel_cost_non_negative"),
        CheckConstraint("labor_cost >= 0", name="ck_price_records_labor_cost_non_negative"),
        CheckConstraint("utility_cost >= 0", name="ck_price_records_utility_cost_non_negative"),
        CheckConstraint("distance_meter >= 0", name="ck_price_records_distance_meter_non_negative"),
        CheckConstraint("distance_cost >= 0", name="ck_price_records_distance_cost_non_negative"),
        CheckConstraint("supplier_fee >= 0", name="ck_price_records_supplier_fee_non_negative"),
        CheckConstraint("discount >= 0", name="ck_price_records_discount_non_negative"),
        CheckConstraint("final_total_cost >= 0", name="ck_price_records_final_total_cost_non_negative"),
        CheckConstraint("expire_at IS NULL OR expire_at > effective_at", name="ck_price_records_expire_after_effective"),
        CheckConstraint("normalized_currency = 'THB'", name="ck_price_records_normalized_currency_thb"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), index=True)
    branch_id: Mapped[str] = mapped_column(String(36), ForeignKey("branches.id"), index=True)
    source_type: Mapped[PriceSourceType] = mapped_column(Enum(PriceSourceType, native_enum=False, values_callable=enum_values), index=True)
    status: Mapped[PriceRecordStatus] = mapped_column(Enum(PriceRecordStatus, native_enum=False, values_callable=enum_values), default=PriceRecordStatus.DRAFT, index=True)
    delivery_mode: Mapped[str] = mapped_column(String(64), default=DeliveryMode.STANDARD.value, index=True)
    area_scope: Mapped[str] = mapped_column(String(128), default=AreaScope.GLOBAL.value, index=True)
    price_dimension: Mapped[str] = mapped_column(String(64), default=PriceDimension.REAL_TOTAL_COST.value, index=True)
    quantity_min: Mapped[int] = mapped_column(Integer)
    quantity_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_currency: Mapped[CurrencyCode] = mapped_column(Enum(CurrencyCode, native_enum=False, values_callable=enum_values), index=True)
    original_amount: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    normalized_currency: Mapped[CurrencyCode] = mapped_column(Enum(CurrencyCode, native_enum=False, values_callable=enum_values), default=CurrencyCode.THB, index=True)
    normalized_amount: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    exchange_rate: Mapped[float] = mapped_column(Numeric(18, 8), default=1)
    exchange_rate_source: Mapped[str] = mapped_column(String(64), default="manual")
    exchange_rate_snapshot_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("exchange_rate_snapshots.id"), nullable=True, index=True)
    exchange_rate_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    base_price: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    vat_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    vat_amount: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    shipping_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    fuel_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    labor_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    utility_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    distance_meter: Mapped[float] = mapped_column(Numeric(18, 3), default=0)
    distance_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    supplier_fee: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    discount: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    final_total_cost: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    formula_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cost_formulas.id"), nullable=True, index=True)
    formula_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("cost_formula_versions.id"), nullable=True, index=True)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    replaced_by_price_record_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("price_records.id"), nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    type: Mapped[TxnType] = mapped_column(Enum(TxnType, native_enum=False), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    qty: Mapped[float] = mapped_column(Numeric(18, 3))
    unit_cost: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 3), nullable=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    product: Mapped[Product] = relationship(Product)
    creator: Mapped[User] = relationship(User, foreign_keys=[created_by])
    branch: Mapped[Branch | None] = relationship(Branch)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_role: Mapped[Role | None] = mapped_column(Enum(Role, native_enum=False), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    audit_log_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("audit_logs.id"), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_role: Mapped[Role | None] = mapped_column(Enum(Role, native_enum=False), nullable=True, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    severity: Mapped[AuditSeverity] = mapped_column(Enum(AuditSeverity, native_enum=False), default=AuditSeverity.INFO, index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    diff_summary: Mapped[str] = mapped_column(String(255), default="")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class EntityArchive(Base):
    __tablename__ = "entity_archives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    storage_driver: Mapped[AttachmentStorageDriver] = mapped_column(Enum(AttachmentStorageDriver, native_enum=False), default=AttachmentStorageDriver.LOCAL, index=True)
    storage_bucket: Mapped[str] = mapped_column(String(255), default="")
    storage_key: Mapped[str] = mapped_column(String(1024), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(255), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(128), default="", index=True)
    classification: Mapped[str] = mapped_column(String(64), default="other", index=True)
    status: Mapped[AttachmentStatus] = mapped_column(Enum(AttachmentStatus, native_enum=False), default=AttachmentStatus.ACTIVE, index=True)
    malware_status: Mapped[AttachmentMalwareStatus] = mapped_column(Enum(AttachmentMalwareStatus, native_enum=False), default=AttachmentMalwareStatus.PENDING, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class AttachmentBinding(Base):
    __tablename__ = "attachment_bindings"
    __table_args__ = (UniqueConstraint("attachment_id", "entity_type", "entity_id", name="uq_attachment_binding_entity"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    attachment_id: Mapped[str] = mapped_column(String(36), ForeignKey("attachments.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="primary")
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class AttachmentScanJob(Base):
    __tablename__ = "attachment_scan_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    attachment_id: Mapped[str] = mapped_column(String(36), ForeignKey("attachments.id"), index=True)
    status: Mapped[AttachmentScanStatus] = mapped_column(Enum(AttachmentScanStatus, native_enum=False), default=AttachmentScanStatus.PENDING, index=True)
    scanner_name: Mapped[str] = mapped_column(String(128), default="hook")
    error_message: Mapped[str] = mapped_column(Text, default="")
    result_detail: Mapped[str] = mapped_column(Text, default="")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttachmentTypeClassification(Base):
    __tablename__ = "attachment_type_classifications"
    __table_args__ = (UniqueConstraint("entity_type", "classification", name="uq_attachment_type_classification"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    classification: Mapped[str] = mapped_column(String(64), index=True)
    allowed_mime_csv: Mapped[str] = mapped_column(Text, default="")
    allowed_extensions_csv: Mapped[str] = mapped_column(Text, default="")
    max_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    max_file_count: Mapped[int] = mapped_column(Integer, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class StockAlertState(Base):
    __tablename__ = "stock_alert_states"
    __table_args__ = (UniqueConstraint("product_id", name="uq_stock_alert_product_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
    last_low_level_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_high_level_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_pct: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    product: Mapped[Product] = relationship(Product)


def _prevent_snapshot_mutation(*_: object, **__: object) -> None:
    raise ValueError("report_snapshot_immutable")


for _snapshot_model in (ReportSnapshot, ReportSnapshotItem, ReportSnapshotLink):
    event.listen(_snapshot_model, "before_update", _prevent_snapshot_mutation)
    event.listen(_snapshot_model, "before_delete", _prevent_snapshot_mutation)
