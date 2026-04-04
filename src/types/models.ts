export type Role = 'STOCK' | 'ADMIN' | 'ACCOUNTANT' | 'OWNER' | 'DEV'

export interface AppConfig {
  app_name: string
  app_logo_url: string
  web_url: string
  primary_color: string
  secondary_color: string
  default_language: 'th' | 'en'
  currency: string
  timezone: string
  session_max_per_user: number
  min_stock_threshold: number
  max_backup_files: number
  backup_interval_hours: number
  background_mode: 'gradient' | 'plain' | 'image'
  background_color: string
  background_image_url: string
  background_gradient_from: string
  background_gradient_to: string
  background_gradient_accent: string
  background_blur_px: number
  background_overlay_opacity: number
}

export interface User {
  id: string
  username: string
  display_name: string
  role: Role
  is_active: boolean
  language: 'th' | 'en'
  has_secret_key?: boolean
  created_at: string
  updated_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in: number
}

export type StockStatus = 'FULL' | 'NORMAL' | 'LOW' | 'CRITICAL' | 'OUT' | 'TEST'

export interface ProductName {
  th: string
  en: string
}

export interface Product {
  id: string
  sku: string
  branch_id: string | null
  category_id: string | null
  name: ProductName
  category: string
  type: string
  unit: string
  cost_price: string
  selling_price: string | null
  stock_qty: string
  min_stock: string
  max_stock: string
  status: StockStatus
  is_test: boolean
  supplier: string
  barcode: string
  image_url: string | null
  notes: string
  archived_at?: string | null
  deleted_at?: string | null
  delete_reason?: string | null
  created_at: string
  updated_at: string
  created_by: string
}

export interface Branch {
  id: string
  code: string
  name: string
  description: string
  is_default: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AttachmentItem {
  id: string
  original_filename: string
  content_type: string
  size_bytes: number
  classification: string
  storage_driver: string
  storage_bucket: string
  storage_key: string
  status: string
  malware_status: string
  owner_user_id?: string | null
  created_at: string
  archived_at?: string | null
  deleted_at?: string | null
}

export interface SupplierContact {
  id?: string
  contact_type: string
  label: string
  value: string
  is_primary: boolean
  sort_order?: number
  created_at?: string
  archived_at?: string | null
}

export interface SupplierLink {
  id?: string
  link_type: string
  label: string
  url: string
  is_primary: boolean
  sort_order?: number
  created_at?: string
  archived_at?: string | null
}

export interface SupplierPickupPoint {
  id?: string
  label: string
  address: string
  details: string
  is_primary: boolean
  created_at?: string
  archived_at?: string | null
}

export interface SupplierReliabilityBreakdown {
  metric_key: string
  score_value: number
  weight: number
  detail_text: string
}

export interface SupplierReliability {
  overall_score: number
  auto_score: number
  effective_score: number
  breakdown: SupplierReliabilityBreakdown[]
}

export interface Supplier {
  id: string
  branch_id: string | null
  code: string
  name: string
  normalized_name: string
  phone: string
  line_id: string
  facebook_url: string
  website_url: string
  address: string
  pickup_notes: string
  source_details: string
  purchase_history_notes: string
  reliability_note: string
  status: string
  is_verified: boolean
  archived_at?: string | null
  deleted_at?: string | null
  delete_reason?: string | null
  created_at: string
  updated_at: string
  product_count: number
  contacts: SupplierContact[]
  links: SupplierLink[]
  pickup_points: SupplierPickupPoint[]
  reliability?: SupplierReliability | null
  attachments: AttachmentItem[]
}

export interface SupplierProposal {
  id: string
  supplier_id?: string | null
  action: string
  status: string
  proposed_by_user_id?: string | null
  reviewed_by_user_id?: string | null
  approved_supplier_id?: string | null
  requires_dev_review: boolean
  proposed_payload?: Record<string, unknown> | null
  current_payload?: Record<string, unknown> | null
  review_note: string
  created_at: string
  updated_at: string
  reviewed_at?: string | null
}

export interface ProductCategory {
  id: string
  name: string
  description: string
  is_deleted: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export interface InventoryRuleSettings {
  max_multiplier: number
  min_divisor: number
}

export type TxnType = 'STOCK_IN' | 'STOCK_OUT' | 'ADJUST'

export interface StockTransaction {
  id: string
  type: TxnType
  product_id: string
  sku: string
  qty: string
  unit_cost: string | null
  unit_price: string | null
  reason: string
  approval_required: boolean
  approved_by: string | null
  created_at: string
  created_by: string
}

export interface AuditLog {
  id: string
  actor_user_id: string | null
  actor_username: string | null
  actor_role: Role | null
  action: string
  entity: string
  entity_id: string | null
  ip: string | null
  user_agent: string | null
  success: boolean
  before_json: unknown | null
  after_json: unknown | null
  message: string
  created_at: string
}

