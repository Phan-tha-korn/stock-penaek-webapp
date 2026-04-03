import { api } from './api'

export interface Kpis {
  total_products: number
  stock_value: string
  daily_revenue: string
  daily_expense: string
  active_users_online: number
}

export interface ActivityItem {
  id: string
  created_at: string
  actor_username: string | null
  actor_role: string | null
  action: string
  message: string
}

export interface TransactionItem {
  id: string
  created_at: string
  type: 'STOCK_IN' | 'STOCK_OUT' | 'ADJUST'
  sku: string
  product_name: string
  qty: string
  unit: string
  note: string
  actor_username: string | null
}

export interface StockSummary {
  total_products: number
  full: number
  normal: number
  low: number
  critical: number
  out: number
}

export interface OwnerChartSlice {
  name: string
  value: number
}

export interface OwnerTimelinePoint {
  key: string
  label: string
  activity_count: number
  transaction_count: number
  stock_in_qty: string
  stock_out_qty: string
  adjust_qty: string
}

export interface OwnerSummary {
  period: 'day' | 'week' | 'month' | 'year'
  total_products: number
  stock_value: string
  sales_value: string
  user_total: number
  active_users_online: number
  activity_total: number
  transaction_total: number
  status_chart: OwnerChartSlice[]
  category_chart: OwnerChartSlice[]
  timeline: OwnerTimelinePoint[]
}

export async function fetchKpis() {
  const { data } = await api.get<Kpis>('/dashboard/kpis')
  return data
}

export async function fetchStockSummary() {
  const { data } = await api.get<StockSummary>('/dashboard/stock_summary')
  return data
}

export async function fetchActivity() {
  const { data } = await api.get<{ items: ActivityItem[] }>('/dashboard/activity')
  return {
    items: Array.isArray(data?.items) ? data.items : [],
  }
}

export async function fetchTransactions(params: { sku?: string; type?: string; date_from?: string; date_to?: string; limit?: number; offset?: number } = {}) {
  const { data } = await api.get<{ items: TransactionItem[]; total: number }>('/dashboard/transactions', { params })
  return {
    items: Array.isArray(data?.items) ? data.items : [],
    total: Number(data?.total || 0),
  }
}

export async function fetchOwnerSummary(period: OwnerSummary['period'] = 'week') {
  const { data } = await api.get<OwnerSummary>('/dashboard/owner_summary', { params: { period } })
  return data
}

