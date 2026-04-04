import { api } from './api'

export interface ZoneLanding {
  role: string
  landing_path: string
}

export interface ZoneSummary {
  zone: string
  landing_path: string
  verification?: { pending: number; overdue: number; assigned_to_me?: number }
  notifications?: { failed: number; retrying: number }
  pricing?: { active_prices: number }
  comparison?: { active_group_count: number }
  matching?: { warning_count: number }
  suppliers?: { linked_products: number }
  catalog?: { product_count: number }
  recent_changes?: Array<{
    id: string
    action: string
    entity: string
    entity_id: string | null
    severity: string
    reason: string
    diff_summary: string
    created_at: string
  }>
}

export interface QuickSearchItem {
  product_id: string
  branch_id: string | null
  canonical_group_id: string | null
  canonical_group_name: string
  sku: string
  name_th: string
  name_en: string
  category_text: string
  alias_text: string
  tag_text: string
  supplier_text: string
  lifecycle_status: string
  active_price_count: number
  verified_supplier_count: number
  latest_effective_at: string | null
  latest_final_total_cost_thb: number | null
  cheapest_active_final_total_cost_thb: number | null
}

export interface CompareResultRow {
  price_record_id: string
  product_id: string
  supplier_id: string
  canonical_group_id: string | null
  canonical_group_name: string
  sku: string
  product_name_th: string
  product_name_en: string
  supplier_name: string
  status: string
  delivery_mode: string
  area_scope: string
  quantity_min: number
  quantity_max: number | null
  final_total_cost_thb: number
  normalized_amount_thb: number
  effective_at: string | null
  selection_mode: string
}

export interface CompareResult {
  scope_product_id: string | null
  scope_canonical_group_id: string | null
  selection_mode: string
  compare_currency: 'THB'
  as_of: string
  row_count: number
  rows: CompareResultRow[]
}

export interface HistoricalPriceItem {
  price_record_id: string
  product_id: string
  canonical_group_id: string | null
  supplier_id: string
  status: string
  effective_at: string | null
  expire_at: string | null
  normalized_amount_thb: number
  final_total_cost_thb: number
}

export interface VerificationQueueItem {
  request_id: string
  request_code: string
  branch_id: string | null
  workflow_status: string
  risk_level: string
  risk_score: number | null
  subject_domain: string
  queue_key: string
  assignee_user_id: string | null
  assignee_role: string | null
  is_overdue: boolean
  has_blocking_dependency: boolean
  latest_action_at: string | null
  current_escalation_level: number
}

export interface NotificationCenterItem {
  outbox_id: string
  event_id: string
  event_type: string
  source_domain: string
  source_entity_type: string
  source_entity_id: string | null
  status: string
  severity: string
  routing_role: string | null
  recipient_user_id: string | null
  message_title: string
  target_path: string
  updated_at: string
}

export interface NotificationCenterSummary {
  summary: { pending_total: number; failed_total: number }
  items: NotificationCenterItem[]
}

export async function fetchZoneLanding() {
  const { data } = await api.get<ZoneLanding>('/zones/landing')
  return data
}

export async function fetchZoneSummary(zone: 'owner' | 'dev' | 'admin' | 'stock', branchId?: string) {
  const { data } = await api.get<ZoneSummary>(`/zones/${zone}/summary`, { params: branchId ? { branch_id: branchId } : undefined })
  return data
}

export async function fetchZoneQuickSearch(params: Record<string, unknown>) {
  const { data } = await api.get<{ items: QuickSearchItem[] }>('/zones/search/quick', { params })
  return Array.isArray(data?.items) ? data.items : []
}

export async function fetchZoneCompare(params: Record<string, unknown>) {
  const normalizedParams = { ...params }
  if ('productId' in normalizedParams && !('product_id' in normalizedParams)) {
    normalizedParams.product_id = normalizedParams.productId
    delete normalizedParams.productId
  }
  if ('groupId' in normalizedParams && !('canonical_group_id' in normalizedParams)) {
    normalizedParams.canonical_group_id = normalizedParams.groupId
    delete normalizedParams.groupId
  }
  const { data } = await api.get<CompareResult>('/zones/search/compare', { params: normalizedParams })
  return data
}

export async function fetchZoneHistory(params: Record<string, unknown>) {
  const { data } = await api.get<{ items: HistoricalPriceItem[] }>('/zones/search/history', { params })
  return Array.isArray(data?.items) ? data.items : []
}

export async function fetchZoneVerificationQueue(params: Record<string, unknown>) {
  const { data } = await api.get<{ items: VerificationQueueItem[] }>('/zones/verification/queue', { params })
  return Array.isArray(data?.items) ? data.items : []
}

export async function fetchZoneNotifications(branchId?: string) {
  const { data } = await api.get<NotificationCenterSummary>('/zones/notifications/summary', {
    params: branchId ? { branch_id: branchId } : undefined,
  })
  return data
}
