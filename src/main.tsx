import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App'
import './styles/global.css'
import { initI18n, readLanguagePreference } from './services/i18n'
import { useBootstrap } from './hooks/useBootstrap'

initI18n(readLanguagePreference('th'))

const LAST_APP_ERROR_KEY = 'last_app_runtime_error'

function captureRuntimeError(payload: { name?: string; message?: string; stack?: string }) {
  try {
    const detail = {
      name: payload.name || 'RuntimeError',
      message: payload.message || 'unknown_error',
      stack: payload.stack || '',
      path: window.location.pathname,
      capturedAt: new Date().toISOString(),
    }
    window.sessionStorage.setItem(LAST_APP_ERROR_KEY, JSON.stringify(detail))
    ;(window as Window & { __lastAppError?: unknown }).__lastAppError = detail
  } catch {
  }
}

window.addEventListener('error', (event) => {
  captureRuntimeError({
    name: event.error?.name || 'WindowError',
    message: event.error?.message || event.message,
    stack: event.error?.stack || '',
  })
})

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason
  captureRuntimeError({
    name: reason instanceof Error ? reason.name : 'UnhandledPromiseRejection',
    message: reason instanceof Error ? reason.message : String(reason || 'unknown_rejection'),
    stack: reason instanceof Error ? reason.stack || '' : '',
  })
})

function Root() {
  const { ready } = useBootstrap()
  if (!ready) {
    return (
      <div className="bg-app auth-shell">
        <div className="loading-overlay">
          <div className="card loading-card p-6 text-center shadow-2xl">
            <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-white/15 border-t-[color:var(--color-primary)]" />
            <div className="mt-4 text-base font-semibold">กำลังโหลดระบบ</div>
            <div className="mt-1 text-sm text-[color:var(--color-muted)]">กรุณารอสักครู่ ระบบกำลังเตรียมข้อมูลให้พร้อมใช้งาน</div>
          </div>
        </div>
      </div>
    )
  }
  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
)

