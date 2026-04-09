import { api, resolveApiUrl } from './api'

export type DevSheetsConfig = {
  enabled: boolean
  usable: boolean
  error: string
  sheet_id: string
  key_path: string
  sheet_url: string
  download_xlsx_url: string
  stock_tab_url: string
  import_tab_url: string
  accounting_tab_url: string
  logs_tab_url: string
  users_tab_url: string
  stock_download_url: string
  import_download_url: string
  accounting_download_url: string
  logs_download_url: string
  users_download_url: string
  product_import_template_download_url: string
}

export type DevSheetCreateResult = {
  sheet_id: string
  sheet_url: string
  download_xlsx_url: string
}

export type DevSheetsActionResult = {
  ok: boolean
  error?: string
  snapshot_id?: string | null
  snapshot_created_at?: string | null
  snapshot_backup_file_name?: string | null
}

export type DevSheetSnapshot = {
  id: string
  created_at: string
  operation: string
  note: string
  sheet_id: string
  has_sheet_snapshot: boolean
  tab_count: number
  tab_titles: string[]
  backup_file_name: string
  backup_exists: boolean
  archive_file_name: string
}

export type DevSheetSnapshotList = {
  items: DevSheetSnapshot[]
}

export type DevSheetsRollbackResult = {
  ok: boolean
  snapshot_id: string
  snapshot_created_at: string
  snapshot_operation: string
  snapshot_archive_file_name: string
  rollback_backup_file_name: string
  rollback_backup_download_url: string
  restored_counts: Record<string, number>
  sheet_restored: boolean
  sheet_resynced: boolean
  sheet_error?: string | null
}

export async function getDevSheetsConfig() {
  const res = await api.get<DevSheetsConfig>('/dev/sheets/config')
  return res.data
}

export async function createDevSheet(payload: { title: string; share_emails: string[]; set_as_default: boolean }) {
  const res = await api.post<DevSheetCreateResult>('/dev/sheets/create', payload)
  return res.data
}

export async function prepareDevSheetImportTab() {
  const res = await api.post<DevSheetsActionResult>('/dev/sheets/prepare-import-tab', {})
  return res.data
}

export async function listDevSheetSnapshots() {
  const res = await api.get<DevSheetSnapshotList>('/dev/sheets/snapshots')
  return res.data
}

export async function rollbackDevSheetSnapshot(snapshot_id: string) {
  const res = await api.post<DevSheetsRollbackResult>('/dev/sheets/rollback', { snapshot_id })
  return res.data
}

export function resolveDevSheetUrl(url: string) {
  return resolveApiUrl(url)
}
