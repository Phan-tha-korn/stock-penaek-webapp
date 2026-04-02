import { Component, type ReactNode } from 'react'

type AppErrorBoundaryProps = {
  children: ReactNode
}

type AppErrorBoundaryState = {
  hasError: boolean
  errorName: string
  errorMessage: string
  currentPath: string
}

const LAST_APP_ERROR_KEY = 'last_app_runtime_error'

function readCapturedError() {
  try {
    const raw = window.sessionStorage.getItem(LAST_APP_ERROR_KEY)
    if (!raw) return null
    return JSON.parse(raw) as {
      name?: string
      message?: string
      path?: string
    }
  } catch {
    return null
  }
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    hasError: false,
    errorName: '',
    errorMessage: '',
    currentPath: '',
  }

  static getDerivedStateFromError() {
    const captured = typeof window !== 'undefined' ? readCapturedError() : null
    return {
      hasError: true,
      errorName: captured?.name || '',
      errorMessage: captured?.message || '',
      currentPath: captured?.path || (typeof window !== 'undefined' ? window.location.pathname : ''),
    }
  }

  componentDidCatch(error: unknown, info: { componentStack?: string }) {
    console.error('AppErrorBoundary caught an error', error)
    const detail = {
      name: error instanceof Error ? error.name : 'UnknownError',
      message: error instanceof Error ? error.message : String(error || 'unknown_error'),
      path: window.location.pathname,
      stack: error instanceof Error ? error.stack || '' : '',
      componentStack: info?.componentStack || '',
      capturedAt: new Date().toISOString(),
    }
    try {
      window.sessionStorage.setItem(LAST_APP_ERROR_KEY, JSON.stringify(detail))
      ;(window as Window & { __lastAppError?: unknown }).__lastAppError = detail
    } catch {
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[40vh] items-center justify-center px-4 py-10">
          <div className="w-full max-w-lg rounded-2xl border border-red-500/20 bg-black/40 p-6 text-center shadow-2xl backdrop-blur">
            <div className="text-lg font-semibold text-red-100">เกิดข้อผิดพลาดระหว่างโหลดหน้า</div>
            <div className="mt-2 text-sm text-white/70">
              ระบบกันพังได้หยุด error นี้ไว้แล้ว กรุณารีเฟรชหน้าอีกครั้ง หากยังพบปัญหาให้แจ้งทีม Dev พร้อมหน้าที่ใช้งานอยู่
            </div>
            {this.state.errorMessage ? (
              <div className="mt-4 rounded border border-red-500/20 bg-red-500/5 px-4 py-3 text-left text-xs text-red-100/90">
                <div>Path: {this.state.currentPath || '-'}</div>
                <div>Error: {[this.state.errorName, this.state.errorMessage].filter(Boolean).join(': ') || 'unknown_error'}</div>
              </div>
            ) : null}
            <button
              type="button"
              className="mt-4 rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
              onClick={() => window.location.reload()}
            >
              รีเฟรชหน้า
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
