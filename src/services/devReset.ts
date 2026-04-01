import { api } from './api'

export async function resetStock(password: string) {
  const res = await api.post<{
    deleted_products: number
    deleted_transactions: number
    deleted_alert_states: number
    backup_file_name: string
    backup_download_url: string
  }>('/dev/reset/stock', { password })
  return res.data
}
