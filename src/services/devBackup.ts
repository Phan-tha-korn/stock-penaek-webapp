import { api } from './api'

export type DevBackupCreateResult = {
  ok: boolean
  file_name: string
  size_bytes: number
  download_url: string
  counts: Record<string, number>
}

export type DevBackupRestoreResult = {
  ok: boolean
  restored: Record<string, number>
}

export async function createDevBackup(password: string) {
  const form = new FormData()
  form.append('password', password)
  const res = await api.post<DevBackupCreateResult>('/dev/backup/create', form)
  return res.data
}

export async function restoreDevBackup(password: string, file: File) {
  const form = new FormData()
  form.append('password', password)
  form.append('file', file)
  const res = await api.post<DevBackupRestoreResult>('/dev/backup/restore', form)
  return res.data
}

export function getDevBackupDownloadUrl(downloadUrl: string) {
  const baseUrl = ((import.meta as any).env?.VITE_API_URL || '/api').replace(/\/+$/, '')
  if (downloadUrl.startsWith('http://') || downloadUrl.startsWith('https://')) return downloadUrl
  if (downloadUrl.startsWith('/api')) return `${baseUrl.replace(/\/api$/, '')}${downloadUrl}`
  return `${baseUrl}${downloadUrl.startsWith('/') ? '' : '/'}${downloadUrl}`
}
