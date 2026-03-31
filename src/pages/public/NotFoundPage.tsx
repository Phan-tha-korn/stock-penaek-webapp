import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-lg items-center px-4">
      <div className="w-full rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-5 text-sm text-white/80">
        ไม่พบหน้านี้ <Link to="/" className="text-[color:var(--color-primary)]">กลับหน้าหลัก</Link>
      </div>
    </div>
  )
}

