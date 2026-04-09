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
    secret_phrase: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class ProductName(BaseModel):
    th: str
    en: str


class ProductOut(BaseModel):
    id: str
    sku: str
    branch_id: str | None = None
    category_id: str | None = None
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
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    delete_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str


class BranchOut(BaseModel):
    id: str
    code: str
    name: str
    description: str = ""
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AttachmentOut(BaseModel):
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    classification: str
    storage_driver: str
    storage_bucket: str
    storage_key: str
    status: str
    malware_status: str
    owner_user_id: str | None = None
    created_at: datetime
    archived_at: datetime | None = None
    deleted_at: datetime | None = None


class SupplierContactIn(BaseModel):
    contact_type: str = "other"
    label: str = ""
    value: str = ""
    is_primary: bool = False


class SupplierContactOut(SupplierContactIn):
    id: str
    sort_order: int = 0
    created_at: datetime
    archived_at: datetime | None = None


class SupplierLinkIn(BaseModel):
    link_type: str = "other"
    label: str = ""
    url: str = ""
    is_primary: bool = False


class SupplierLinkOut(SupplierLinkIn):
    id: str
    sort_order: int = 0
    created_at: datetime
    archived_at: datetime | None = None


class SupplierPickupPointIn(BaseModel):
    label: str = ""
    address: str = ""
    details: str = ""
    is_primary: bool = False


class SupplierPickupPointOut(SupplierPickupPointIn):
    id: str
    created_at: datetime
    archived_at: datetime | None = None


class SupplierReliabilityBreakdownOut(BaseModel):
    metric_key: str
    score_value: float
    weight: float
    detail_text: str = ""


class SupplierReliabilityOut(BaseModel):
    overall_score: float
    auto_score: float
    effective_score: float
    breakdown: list[SupplierReliabilityBreakdownOut] = []


class SupplierOut(BaseModel):
    id: str
    branch_id: str | None = None
    code: str
    name: str
    normalized_name: str
    phone: str = ""
    line_id: str = ""
    facebook_url: str = ""
    website_url: str = ""
    address: str = ""
    pickup_notes: str = ""
    source_details: str = ""
    purchase_history_notes: str = ""
    reliability_note: str = ""
    status: str
    is_verified: bool = False
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    delete_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    product_count: int = 0
    contacts: list[SupplierContactOut] = []
    links: list[SupplierLinkOut] = []
    pickup_points: list[SupplierPickupPointOut] = []
    reliability: SupplierReliabilityOut | None = None
    attachments: list[AttachmentOut] = []


class SupplierListOut(BaseModel):
    items: list[SupplierOut]
    total: int


class SupplierCreateIn(BaseModel):
    branch_id: str | None = None
    name: str
    phone: str = ""
    line_id: str = ""
    facebook_url: str = ""
    website_url: str = ""
    address: str = ""
    pickup_notes: str = ""
    source_details: str = ""
    purchase_history_notes: str = ""
    reliability_note: str = ""
    status: str = "ACTIVE"
    is_verified: bool = False
    contacts: list[SupplierContactIn] = []
    links: list[SupplierLinkIn] = []
    pickup_points: list[SupplierPickupPointIn] = []


class SupplierUpdateIn(BaseModel):
    branch_id: str | None = None
    name: str | None = None
    phone: str | None = None
    line_id: str | None = None
    facebook_url: str | None = None
    website_url: str | None = None
    address: str | None = None
    pickup_notes: str | None = None
    source_details: str | None = None
    purchase_history_notes: str | None = None
    reliability_note: str | None = None
    status: str | None = None
    is_verified: bool | None = None
    contacts: list[SupplierContactIn] | None = None
    links: list[SupplierLinkIn] | None = None
    pickup_points: list[SupplierPickupPointIn] | None = None


class SupplierProposalOut(BaseModel):
    id: str
    supplier_id: str | None = None
    action: str
    status: str
    proposed_by_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    approved_supplier_id: str | None = None
    requires_dev_review: bool = True
    proposed_payload: dict | None = None
    current_payload: dict | None = None
    review_note: str = ""
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None = None


class SupplierProposalActionIn(BaseModel):
    review_note: str = ""


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
    category_id: str | None = None
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
    category_id: str | None = None
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
    source: str = "stock"
    overwrite_stock_qty: bool = False
    overwrite_prices: bool = False
    sync_after_import: bool = False


class SheetsImportOut(BaseModel):
    ok: bool
    created: int = 0
    updated: int = 0
    skipped: int = 0
    synced: bool = False
    error: str | None = None
    sync_error: str | None = None
    snapshot_id: str | None = None
    snapshot_created_at: str | None = None
    snapshot_backup_file_name: str | None = None


class SheetsSyncOut(BaseModel):
    ok: bool
    error: str | None = None
    snapshot_id: str | None = None
    snapshot_created_at: str | None = None
    snapshot_backup_file_name: str | None = None


class SheetsSnapshotOut(BaseModel):
    id: str
    created_at: str
    operation: str
    note: str = ""
    sheet_id: str = ""
    has_sheet_snapshot: bool = False
    tab_count: int = 0
    tab_titles: list[str] = []
    backup_file_name: str = ""
    backup_exists: bool = False
    archive_file_name: str = ""


class SheetsSnapshotListOut(BaseModel):
    items: list[SheetsSnapshotOut] = []


class SheetsRollbackIn(BaseModel):
    snapshot_id: str


class SheetsRollbackOut(BaseModel):
    ok: bool
    snapshot_id: str
    snapshot_created_at: str = ""
    snapshot_operation: str = ""
    snapshot_archive_file_name: str = ""
    rollback_backup_file_name: str = ""
    rollback_backup_download_url: str = ""
    restored_counts: dict[str, int] = {}
    sheet_restored: bool = False
    sheet_resynced: bool = False
    sheet_error: str | None = None


class ProductBulkCreateItemIn(BaseModel):
    sku: str
    category_id: str | None = None
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
    notes: str = ""


class ProductBulkCreateIn(BaseModel):
    items: list[ProductBulkCreateItemIn]


class ProductCategoryOut(BaseModel):
    id: str
    name: str
    description: str = ""
    is_deleted: bool = False
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class ProductCategoryListOut(BaseModel):
    items: list[ProductCategoryOut]


class ProductCategoryCreateIn(BaseModel):
    name: str
    description: str = ""
    sort_order: int = 0


class ProductCategoryUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class ProductRuleSettingsOut(BaseModel):
    max_multiplier: float = 2
    min_divisor: float = 3


class ProductRuleSettingsIn(BaseModel):
    max_multiplier: float = 2
    min_divisor: float = 3


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


class OwnerTimelinePointOut(BaseModel):
    key: str
    label: str
    activity_count: int
    transaction_count: int
    stock_in_qty: str = "0"
    stock_out_qty: str = "0"
    adjust_qty: str = "0"


class OwnerStatusSliceOut(BaseModel):
    name: str
    value: int


class OwnerSummaryOut(BaseModel):
    period: str
    total_products: int
    stock_value: str
    sales_value: str
    user_total: int
    active_users_online: int
    activity_total: int
    transaction_total: int
    status_chart: list[OwnerStatusSliceOut]
    category_chart: list[OwnerStatusSliceOut]
    timeline: list[OwnerTimelinePointOut]


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
    usable: bool = False
    error: str = ""
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

