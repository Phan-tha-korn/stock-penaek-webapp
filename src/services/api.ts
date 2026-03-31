import axios from 'axios'

import { useAuthStore } from '../store/authStore'

export const api = axios.create({
  baseURL: (import.meta as any).env?.VITE_API_URL || '/api',
  timeout: 20_000
})

api.interceptors.request.use((config) => {
  const tokens = useAuthStore.getState().tokens
  if (tokens?.access_token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${tokens.access_token}`
  }
  return config
})

