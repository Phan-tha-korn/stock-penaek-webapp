import { api } from './api'

export async function resetStock() {
  const res = await api.post<{ deleted_products: number; deleted_transactions: number; deleted_alert_states: number }>('/dev/reset/stock')
  return res.data
}

