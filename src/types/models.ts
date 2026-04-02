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
  created_at: string
  updated_at: string
  created_by: string
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

