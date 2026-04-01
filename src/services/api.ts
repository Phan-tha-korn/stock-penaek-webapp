import axios from 'axios'

import { useAuthStore } from '../store/authStore'

export const api = axios.create({
  baseURL: (import.meta as any).env?.VITE_API_URL || '/api',
  timeout: 20_000
})

const refreshClient = axios.create({
  baseURL: (import.meta as any).env?.VITE_API_URL || '/api',
  timeout: 20_000
})

let refreshPromise: Promise<any> | null = null

function isMutationRequest(method?: string) {
  return ['post', 'put', 'patch', 'delete'].includes(String(method || '').toLowerCase())
}

function isAuthEndpoint(url?: string) {
  const value = String(url || '')
  return value.includes('/auth/login') || value.includes('/auth/refresh')
}

api.interceptors.request.use((config) => {
  const store = useAuthStore.getState()
  const tokens = store.tokens
  if (tokens?.access_token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${tokens.access_token}`
  }
  if (isMutationRequest(config.method) && !isAuthEndpoint(config.url)) {
    ;(config as any).__countedMutation = true
    store.incrementPendingMutation()
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    if ((response.config as any)?.__countedMutation) {
      useAuthStore.getState().decrementPendingMutation()
    }
    return response
  },
  async (error) => {
    const original = error?.config
    if ((original as any)?.__countedMutation) {
      useAuthStore.getState().decrementPendingMutation()
      ;(original as any).__countedMutation = false
    }

    if (error?.response?.status !== 401 || !original || (original as any)._retry || isAuthEndpoint(original.url)) {
      return Promise.reject(error)
    }

    const store = useAuthStore.getState()
    const refreshToken = store.tokens?.refresh_token
    if (!refreshToken) {
      store.markReauthRequired(true)
      return Promise.reject(error)
    }

    try {
      ;(original as any)._retry = true
      if (!refreshPromise) {
        refreshPromise = refreshClient
          .post('/auth/refresh', { refresh_token: refreshToken })
          .then((res) => res.data)
          .finally(() => {
            refreshPromise = null
          })
      }
      const newTokens = await refreshPromise
      store.setTokens(newTokens)
      original.headers = original.headers ?? {}
      original.headers.Authorization = `Bearer ${newTokens.access_token}`
      return api(original)
    } catch (refreshError) {
      store.markReauthRequired(true)
      return Promise.reject(refreshError)
    }
  }
)

