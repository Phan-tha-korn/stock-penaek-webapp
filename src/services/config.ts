import { api } from './api'
import type { AppConfig } from '../types/models'

export async function fetchConfig() {
  const { data } = await api.get<AppConfig>('/config')
  return data
}

export async function updateConfig(cfg: AppConfig) {
  const { data } = await api.put<AppConfig>('/config', cfg)
  return data
}

