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
  accounting_tab_url: string
  logs_tab_url: string
  users_tab_url: string
  stock_download_url: string
  accounting_download_url: string
  logs_download_url: string
  users_download_url: string
}

export type DevSheetCreateResult = {
  sheet_id: string
  sheet_url: string
  download_xlsx_url: string
}

export async function getDevSheetsConfig() {
  const res = await api.get<DevSheetsConfig>('/dev/sheets/config')
  return res.data
}

export async function createDevSheet(payload: { title: string; share_emails: string[]; set_as_default: boolean }) {
  const res = await api.post<DevSheetCreateResult>('/dev/sheets/create', payload)
  return res.data
}

export function resolveDevSheetUrl(url: string) {
  return resolveApiUrl(url)
}
