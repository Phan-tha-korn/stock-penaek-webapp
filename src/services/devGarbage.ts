import { api } from './api'

export interface GarbageFileItem {
  id: string
  path: string
  absolute_path: string
  category: string
  file_type: string
  size_bytes: number
  created_at: string
  modified_at: string
  whitelisted: boolean
}

export interface GarbageScanResult {
  items: GarbageFileItem[]
  total_files: number
  total_size_bytes: number
}

export async function scanGarbage(includeWhitelisted = false) {
  const { data } = await api.get<GarbageScanResult>('/dev/garbage/scan', { params: { include_whitelisted: includeWhitelisted } })
  return {
    items: Array.isArray(data?.items) ? data.items : [],
    total_files: Number(data?.total_files || 0),
    total_size_bytes: Number(data?.total_size_bytes || 0),
  }
}

export async function getGarbageWhitelist() {
  const { data } = await api.get<{ items: string[] }>('/dev/garbage/whitelist')
  return {
    items: Array.isArray(data?.items) ? data.items : [],
  }
}

export async function updateGarbageWhitelist(items: string[]) {
  const { data } = await api.put<{ items: string[] }>('/dev/garbage/whitelist', { items })
  return {
    items: Array.isArray(data?.items) ? data.items : [],
  }
}

export async function deleteGarbage(paths: string[], mode: 'backup' | 'permanent', confirm = true) {
  const { data } = await api.post<{
    ok: boolean
    deleted_count: number
    failed_count: number
    moved_to_backup: boolean
    backup_path?: string | null
    errors: string[]
  }>('/dev/garbage/delete', { paths, mode, confirm })
  return data
}

