import { api } from './api'
import type { AuthTokens, User } from '../types/models'

export interface LoginRequest {
  username: string
  password: string
  totp?: string
  secret_phrase?: string
}

export async function login(req: LoginRequest) {
  const { data } = await api.post<AuthTokens>('/auth/login', req)
  return data
}

export async function refresh(refresh_token: string) {
  const { data } = await api.post<AuthTokens>('/auth/refresh', { refresh_token })
  return data
}

export async function getMe() {
  const { data } = await api.get<User>('/auth/me')
  return data
}

export async function listUsers(params: { q?: string; limit?: number; offset?: number } = {}) {
  const { data } = await api.get<{ items: User[]; total: number }>('/users', { params })
  return data
}

export async function createUser(data: {
  username: string
  display_name?: string
  role: string
  password: string
  secret_key?: string
  language?: string
}) {
  const res = await api.post<User>('/users', data)
  return res.data
}

export async function updateUser(id: string, data: { username?: string; display_name?: string; role?: string; is_active?: boolean; language?: string }) {
  const res = await api.patch<User>(`/users/${encodeURIComponent(id)}`, data)
  return res.data
}

export async function resetUserPassword(id: string, password: string) {
  const res = await api.post<User>(`/users/${encodeURIComponent(id)}/reset-password`, { password })
  return res.data
}

export async function deleteUser(id: string) {
  const res = await api.delete<{ ok: boolean }>(`/users/${encodeURIComponent(id)}`)
  return res.data
}

