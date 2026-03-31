import { api } from './api'

export type NotificationConfig = {
  enabled: boolean
  low_levels_pct: number[]
  high_levels_pct: number[]
  roles: string[]
}

export async function getNotificationConfig() {
  const res = await api.get<NotificationConfig>('/dev/notifications/config')
  return res.data
}

export async function updateNotificationConfig(payload: NotificationConfig) {
  const res = await api.put<NotificationConfig>('/dev/notifications/config', payload)
  return res.data
}

