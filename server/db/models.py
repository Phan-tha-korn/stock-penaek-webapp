from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


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


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="th")

    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
    status: Mapped[StockStatus] = mapped_column(Enum(StockStatus), index=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    supplier: Mapped[str] = mapped_column(String(255), default="")
    barcode: Mapped[str] = mapped_column(String(255), default="", index=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    creator: Mapped[User] = relationship(User)


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    type: Mapped[TxnType] = mapped_column(Enum(TxnType), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), index=True)
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


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_role: Mapped[Role | None] = mapped_column(Enum(Role), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


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

