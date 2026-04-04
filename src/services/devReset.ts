import { api } from './api'

export type DevPermanentDeleteScope =
  | 'products'
  | 'suppliers'
  | 'pricing'
  | 'matching'
  | 'verification'
  | 'notifications'
  | 'attachments'
  | 'reports'
  | 'logs'
  | 'system_access'
  | 'backups'

export interface DevPermanentDeletePayload {
  delete_all: boolean
  scopes: DevPermanentDeleteScope[]
  product_refs: string[]
  supplier_refs: string[]
  category_refs: string[]
  price_record_refs: string[]
  verification_refs: string[]
  attachment_refs: string[]
}

export interface DevPermanentDeleteResult {
  executed_scopes: string[]
  deleted_counts: Record<string, number>
  filesystem_deleted: Record<string, number>
  unmatched_refs: Record<string, string[]>
  warnings: string[]
  session_invalidated: boolean
}

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

export async function permanentDelete(payload: DevPermanentDeletePayload, password: string) {
  const res = await api.post<DevPermanentDeleteResult>('/dev/reset/permanent-delete', {
    password,
    ...payload,
  })
  return res.data
}
