import { api } from './api'

export interface PriceRecordItem {
  id: string
  product_id: string
  supplier_id: string
  branch_id: string
  source_type: string
  status: string
  delivery_mode: string
  area_scope: string
  price_dimension: string
  quantity_min: number
  quantity_max: number | null
  original_currency: string
  original_amount: string
  normalized_currency: string
  normalized_amount: string
  exchange_rate: string
  base_price: string
  vat_percent: string
  vat_amount: string
  shipping_cost: string
  fuel_cost: string
  labor_cost: string
  utility_cost: string
  distance_meter: string
  distance_cost: string
  supplier_fee: string
  discount: string
  final_total_cost: string
  effective_at: string | null
  expire_at: string | null
  note: string
  created_at: string
  updated_at: string
  // Joined fields
  product_sku?: string
  product_name_th?: string
  supplier_name?: string
}

export interface PriceRecordListParams {
  product_id?: string
  supplier_id?: string
  status?: string
  include_archived?: boolean
  limit?: number
  offset?: number
}

export interface PriceRecordPayload {
  product_id: string
  supplier_id: string
  source_type?: string
  status?: string
  delivery_mode?: string
  area_scope?: string
  price_dimension?: string
  quantity_min?: number
  quantity_max?: number | null
  original_currency?: string
  original_amount?: number
  exchange_rate?: number
  vat_percent?: number
  shipping_cost?: number
  fuel_cost?: number
  labor_cost?: number
  utility_cost?: number
  distance_meter?: number
  distance_cost?: number
  supplier_fee?: number
  discount?: number
  effective_at?: string | null
  expire_at?: string | null
  note?: string
}

export interface DropdownProduct {
  id: string
  sku: string
  name_th: string
  name_en: string
  unit: string
}

export interface DropdownSupplier {
  id: string
  code: string
  name: string
}

export async function listPriceRecords(params: PriceRecordListParams = {}) {
  const { data } = await api.get<{ items: PriceRecordItem[]; total: number }>('/price-records', { params })
  return { items: Array.isArray(data?.items) ? data.items : [], total: data?.total ?? 0 }
}

export async function createPriceRecord(payload: PriceRecordPayload) {
  const { data } = await api.post<PriceRecordItem>('/price-records', payload)
  return data
}

export async function updatePriceRecord(id: string, payload: Partial<PriceRecordPayload>) {
  const { data } = await api.put<PriceRecordItem>(`/price-records/${encodeURIComponent(id)}`, payload)
  return data
}

export async function archivePriceRecord(id: string) {
  const { data } = await api.delete<{ status: string; id: string }>(`/price-records/${encodeURIComponent(id)}`)
  return data
}

export async function dropdownProducts(q = '') {
  const { data } = await api.get<DropdownProduct[]>('/price-records/dropdown/products', { params: { q, limit: 50 } })
  return Array.isArray(data) ? data : []
}

export async function dropdownSuppliers(q = '') {
  const { data } = await api.get<DropdownSupplier[]>('/price-records/dropdown/suppliers', { params: { q, limit: 50 } })
  return Array.isArray(data) ? data : []
}
