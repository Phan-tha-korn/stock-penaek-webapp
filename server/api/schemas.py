from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from server.db.models import Role, StockStatus, TxnType


class PublicConfig(BaseModel):
    app_name: str
    app_logo_url: str = ""
    web_url: str = ""
    primary_color: str
    secondary_color: str
    default_language: str = "th"
    currency: str = "THB"
    timezone: str = "Asia/Bangkok"
    session_max_per_user: int = 3
    min_stock_threshold: int = 10
    max_backup_files: int = 30
    backup_interval_hours: int = 6
    background_mode: str = "gradient"
    background_color: str = "#0D0D0D"
    background_image_url: str = ""
    background_gradient_from: str = "#0D0D0D"
    background_gradient_to: str = "#101826"
    background_gradient_accent: str = "#1E6FD9"
    background_blur_px: int = 0
    background_overlay_opacity: int = 35


class ConfigUpdateIn(BaseModel):
    app_name: str
    app_logo_url: str = ""
    web_url: str = ""
    primary_color: str
    secondary_color: str
    default_language: str = "th"
    currency: str = "THB"
    timezone: str = "Asia/Bangkok"
    session_max_per_user: int = 3
    min_stock_threshold: int = 10
    max_backup_files: int = 30
    backup_interval_hours: int = 6
    background_mode: str = "gradient"
    background_color: str = "#0D0D0D"
    background_image_url: str = ""
    background_gradient_from: str = "#0D0D0D"
    background_gradient_to: str = "#101826"
    background_gradient_accent: str = "#1E6FD9"
    background_blur_px: int = 0
    background_overlay_opacity: int = 35


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    is_active: bool
    language: str
    has_secret_key: bool
    created_at: datetime
    updated_at: datetime


class UserListOut(BaseModel):
    items: list[UserOut]
    total: int


class UserCreateIn(BaseModel):
    username: str
    display_name: str = ""
    role: Role
    password: str
    secret_key: str | None = None
    language: str = "th"


class UserUpdateIn(BaseModel):
    username: str | None = None
    display_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    language: str | None = None


class UserResetPasswordIn(BaseModel):
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginIn(BaseModel):
    username: str
    password: str
    totp: str | None = None
    secret_phrase: str | None = Field(default=None, alias="secret_phrase")


class RefreshIn(BaseModel):
    refresh_token: str


class ProductName(BaseModel):
    th: str
    en: str


class ProductOut(BaseModel):
    id: str
    sku: str
    name: ProductName
    category: str
    type: str
    unit: str
    cost_price: str
    selling_price: str | None
    stock_qty: str
    min_stock: str
    max_stock: str
    status: StockStatus
    is_test: bool
    supplier: str
    barcode: str
    image_url: str | None
    notes: str
    created_at: datetime
    updated_at: datetime
    created_by: str


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int


class KpisOut(BaseModel):
    total_products: int
    stock_value: str
    daily_revenue: str
    daily_expense: str
    active_users_online: int


class StockSummaryOut(BaseModel):
    total_products: int
    full: int
    normal: int
    low: int
    critical: int
    out: int


class ActivityItemOut(BaseModel):
    id: str
    created_at: datetime
    actor_username: str | None
    actor_role: Role | None
    action: str
    message: str


class ActivityListOut(BaseModel):
    items: list[ActivityItemOut]


class StockAdjustIn(BaseModel):
    qty: float = Field(ge=0)
    type: TxnType
    reason: str = ""


class ProductCreateIn(BaseModel):
    sku: str
    name_th: str
    name_en: str = ""
    category: str = ""
    type: str = ""
    unit: str = ""
    cost_price: float = 0
    selling_price: float | None = None
    stock_qty: float = 0
    min_stock: float = 0
    max_stock: float = 0
    is_test: bool = False
    supplier: str = ""
    barcode: str = ""
    image_url: str | None = None
    notes: str = ""


class ProductUpdateIn(BaseModel):
    name_th: str | None = None
    name_en: str | None = None
    category: str | None = None
    type: str | None = None
    unit: str | None = None
    cost_price: float | None = None
    selling_price: float | None = None
    min_stock: float | None = None
    max_stock: float | None = None
    supplier: str | None = None
    barcode: str | None = None
    image_url: str | None = None
    notes: str | None = None


class ProductDeleteIn(BaseModel):
    reason: str = ""


class SheetsImportIn(BaseModel):
    overwrite_stock_qty: bool = False
    overwrite_prices: bool = False


class SheetsImportOut(BaseModel):
    ok: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    error: str | None = None


class SheetsSyncOut(BaseModel):
    ok: bool
    error: str | None = None


class ProductBulkRowResult(BaseModel):
    row: int
    sku: str
    ok: bool
    action: str = ""
    error: str | None = None


class ProductBulkImportOut(BaseModel):
    ok: bool
    created: int = 0
    updated: int = 0
    failed: int = 0
    items: list[ProductBulkRowResult] = []


class TransactionOut(BaseModel):
    id: str
    created_at: datetime
    type: TxnType
    sku: str
    product_name: str
    qty: str
    unit: str
    note: str = ""
    actor_username: str | None = None


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int


class GarbageFileOut(BaseModel):
    id: str
    path: str
    absolute_path: str
    category: str
    file_type: str
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    whitelisted: bool = False


class GarbageScanOut(BaseModel):
    items: list[GarbageFileOut]
    total_files: int
    total_size_bytes: int


class GarbageWhitelistOut(BaseModel):
    items: list[str]


class GarbageWhitelistUpdateIn(BaseModel):
    items: list[str]


class GarbageDeleteIn(BaseModel):
    paths: list[str]
    mode: str = "backup"
    confirm: bool = False


class GarbageDeleteOut(BaseModel):
    ok: bool
    deleted_count: int
    failed_count: int
    moved_to_backup: bool
    backup_path: str | None = None
    errors: list[str] = []


class NotificationConfigOut(BaseModel):
    enabled: bool
    low_levels_pct: list[int]
    high_levels_pct: list[int]
    roles: list[str]
    line_token_status: dict[str, str] = {}
    include_name: bool = True
    include_sku: bool = True
    include_status: bool = True
    include_current_qty: bool = True
    include_target_qty: bool = True
    include_restock_qty: bool = True
    include_actor: bool = True
    include_reason: bool = True
    include_image_url: bool = False


class NotificationConfigUpdateIn(BaseModel):
    enabled: bool = False
    low_levels_pct: list[int] = []
    high_levels_pct: list[int] = []
    roles: list[str] = []
    line_tokens: dict[str, str] = {}
    include_name: bool = True
    include_sku: bool = True
    include_status: bool = True
    include_current_qty: bool = True
    include_target_qty: bool = True
    include_restock_qty: bool = True
    include_actor: bool = True
    include_reason: bool = True
    include_image_url: bool = False


class GoogleSetupOut(BaseModel):
    configured: bool
    workspace_email: str = ""
    drive_folder_name: str = ""
    default_sheet_title: str = ""
    service_account_key_path: str = ""
    oauth_client_id: str = ""
    oauth_client_secret_masked: str = ""
    oauth_redirect_uri: str = ""
    oauth_token_path: str = ""
    oauth_connected: bool = False
    current_sheet_id: str = ""
    current_sheet_url: str = ""


class GoogleSetupIn(BaseModel):
    workspace_email: str = ""
    drive_folder_name: str = ""
    default_sheet_title: str = ""
    service_account_key_path: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = ""
    oauth_token_path: str = ""
    create_new_sheet: bool = True
    migrate_existing_data: bool = True


class GoogleOAuthStartOut(BaseModel):
    auth_url: str

