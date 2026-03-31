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

export async function fetchKpis() {
  const { data } = await api.get<Kpis>('/dashboard/kpis')
  return data
}

export async function fetchActivity() {
  const { data } = await api.get<{ items: ActivityItem[] }>('/dashboard/activity')
  return data
}

export async function fetchTransactions(params: { sku?: string; type?: string; date_from?: string; date_to?: string; limit?: number; offset?: number } = {}) {
  const { data } = await api.get<{ items: TransactionItem[]; total: number }>('/dashboard/transactions', { params })
  return data
}

