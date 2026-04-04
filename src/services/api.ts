import axios, { type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'

import { useAuthStore } from '../store/authStore'
import type { AuthTokens } from '../types/models'

function resolveApiBaseUrl(): string {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  if (typeof window === 'undefined') return '/api'
  const { hostname, protocol } = window.location
  // Use relative URL for localhost, IPs, or when already on the api. subdomain
  if (
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    /^\d+\.\d+\.\d+\.\d+$/.test(hostname) ||
    hostname.startsWith('api.')
  ) {
    return '/api'
  }
  // For custom domains (e.g. penaekapi.xyz or www.penaekapi.xyz),
  // the API is hosted on the api. subdomain served by the cloudflared tunnel.
  const cleanHost = hostname.replace(/^www\./, '')
  return `${protocol}//api.${cleanHost}/api`
}

const API_BASE_URL = resolveApiBaseUrl()

interface RequestConfigExtra extends InternalAxiosRequestConfig {
  __countedMutation?: boolean
  _retry?: boolean
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000
})

const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000
})

type RefreshResponse = Omit<AuthTokens, 'token_type'> & { token_type?: AuthTokens['token_type'] }

let refreshPromise: Promise<AuthTokens> | null = null

function isMutationRequest(method?: string) {
  return ['post', 'put', 'patch', 'delete'].includes(String(method || '').toLowerCase())
}

function isAuthEndpoint(url?: string) {
  const value = String(url || '')
  return value.includes('/auth/login') || value.includes('/auth/refresh')
}

api.interceptors.request.use((config) => {
  const ext = config as RequestConfigExtra
  const store = useAuthStore.getState()
  const tokens = store.tokens
  if (tokens?.access_token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${tokens.access_token}`
  }
  if (isMutationRequest(config.method) && !isAuthEndpoint(config.url)) {
    ext.__countedMutation = true
    store.incrementPendingMutation()
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    if ((response.config as RequestConfigExtra)?.__countedMutation) {
      useAuthStore.getState().decrementPendingMutation()
    }
    return response
  },
  async (error) => {
    const original = error?.config as RequestConfigExtra | undefined
    if (original?.__countedMutation) {
      useAuthStore.getState().decrementPendingMutation()
      original.__countedMutation = false
    }

    if (error?.response?.status !== 401 || !original || original._retry || isAuthEndpoint(original.url)) {
      return Promise.reject(error)
    }

    const store = useAuthStore.getState()
    const refreshToken = store.tokens?.refresh_token
    if (!refreshToken) {
      store.markReauthRequired(true)
      return Promise.reject(error)
    }

    try {
      original._retry = true
      if (!refreshPromise) {
        refreshPromise = refreshClient
          .post<RefreshResponse>('/auth/refresh', { refresh_token: refreshToken })
          .then<AuthTokens>((res) => ({
            token_type: 'bearer' as const,
            ...res.data
          }))
          .finally(() => {
            refreshPromise = null
          })
      }
      const newTokens = await refreshPromise!
      store.setTokens(newTokens)
      original.headers = original.headers ?? {}
      original.headers.Authorization = `Bearer ${newTokens.access_token}`
      return api(original as AxiosRequestConfig)
    } catch (refreshError) {
      store.markReauthRequired(true)
      return Promise.reject(refreshError)
    }
  }
)
