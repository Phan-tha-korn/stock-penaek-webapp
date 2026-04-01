import { api } from './api'

export type DevSheetsConfig = {
  enabled: boolean
  sheet_id: string
  key_path: string
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
