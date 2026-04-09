import { api } from './api'

export type NotificationConfig = {
  enabled: boolean
  low_levels_pct: number[]
  high_levels_pct: number[]
  roles: string[]
  line_token_status?: Record<string, string>
  include_name: boolean
  include_sku: boolean
  include_status: boolean
  include_current_qty: boolean
  include_target_qty: boolean
  include_restock_qty: boolean
  include_actor: boolean
  include_reason: boolean
  include_image_url: boolean
  line_tokens?: Record<string, string>
}

export async function getNotificationConfig() {
  const res = await api.get<NotificationConfig>('/dev/notifications/config')
  return res.data
}

export async function updateNotificationConfig(payload: NotificationConfig) {
  const res = await api.put<NotificationConfig>('/dev/notifications/config', payload)
  return res.data
}

