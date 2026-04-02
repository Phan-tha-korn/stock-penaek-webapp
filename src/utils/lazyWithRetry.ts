import { lazy } from 'react'

const RETRY_KEY = 'lazy_chunk_retry_once'

export function lazyWithRetry<T extends { default: React.ComponentType<any> }>(
  importer: () => Promise<T>
) {
  return lazy(async () => {
    try {
      const mod = await importer()
      window.sessionStorage.removeItem(RETRY_KEY)
      return mod
    } catch (error) {
      const hasRetried = window.sessionStorage.getItem(RETRY_KEY) === '1'
      if (!hasRetried) {
        window.sessionStorage.setItem(RETRY_KEY, '1')
        window.location.reload()
        return new Promise<T>(() => {})
      }
      throw error
    }
  })
}
