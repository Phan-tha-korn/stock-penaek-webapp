import { Component, type ReactNode } from 'react'

type AppErrorBoundaryProps = {
  children: ReactNode
}

type AppErrorBoundaryState = {
  hasError: boolean
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    hasError: false,
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: unknown) {
    console.error('AppErrorBoundary caught an error', error)
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
