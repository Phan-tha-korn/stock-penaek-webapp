import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useAuthStore } from '../../store/authStore'

const REAUTH_MS = 24 * 60 * 60 * 1000

function isEditableElement(target: EventTarget | null) {
  const el = target as HTMLElement | null
  if (!el) return false
  if (el.isContentEditable) return true
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

function formatRemaining(ms: number) {
  const totalMinutes = Math.max(0, Math.ceil(ms / 60000))
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours <= 0) return `${minutes} นาที`
  return `${hours} ชม. ${minutes} นาที`
}

export function SessionGuard() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const sessionStartedAt = useAuthStore((s) => s.sessionStartedAt)
  const reauthRequired = useAuthStore((s) => s.reauthRequired)
  const pendingMutationCount = useAuthStore((s) => s.pendingMutationCount)
  const markReauthRequired = useAuthStore((s) => s.markReauthRequired)
  const clearSession = useAuthStore((s) => s.clearSession)
  const [editingActive, setEditingActive] = useState(false)
  const [remainingMs, setRemainingMs] = useState(REAUTH_MS)

  const deadline = useMemo(() => {
    if (!sessionStartedAt) return null
    const startedAt = new Date(sessionStartedAt).getTime()
    if (Number.isNaN(startedAt)) return null
    return startedAt + REAUTH_MS
  }, [sessionStartedAt])

  useEffect(() => {
    const onFocusIn = (event: FocusEvent) => {
      setEditingActive(isEditableElement(event.target))
    }
    const onFocusOut = () => {
      window.setTimeout(() => {
        setEditingActive(isEditableElement(document.activeElement))
      }, 150)
    }
    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('focusout', onFocusOut)
    return () => {
      document.removeEventListener('focusin', onFocusIn)
      document.removeEventListener('focusout', onFocusOut)
    }
  }, [])

  useEffect(() => {
    if (!user || !deadline) return
    const run = () => {
      const diff = deadline - Date.now()
      setRemainingMs(Math.max(0, diff))
      if (diff <= 0) {
        markReauthRequired(true)
      }
    }
    run()
    const timer = window.setInterval(run, 30000)
    return () => window.clearInterval(timer)
  }, [deadline, markReauthRequired, user])

  useEffect(() => {
    if (!user || location.pathname === '/login' || !reauthRequired) return
    if (editingActive || pendingMutationCount > 0) return
    const timer = window.setTimeout(() => {
      const state = useAuthStore.getState()
      if (!state.reauthRequired || state.pendingMutationCount > 0) return
      clearSession()
      navigate('/login', { replace: true, state: { reason: 'session_expired' } })
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [clearSession, editingActive, location.pathname, navigate, pendingMutationCount, reauthRequired, user])

  if (!user || location.pathname === '/login') return null

  if (reauthRequired) {
    return (
      <div className="fixed inset-x-0 top-0 z-[120] px-4 pt-3">
        <div className="mx-auto max-w-5xl rounded border border-amber-500/40 bg-amber-500/15 px-4 py-3 text-sm text-amber-100 shadow-2xl backdrop-blur">
          {editingActive || pendingMutationCount > 0
            ? 'เซสชันครบ 24 ชั่วโมงแล้ว ระบบจะให้เข้าสู่ระบบใหม่หลังจากบันทึกหรือแก้ไขงานปัจจุบันเสร็จ'
            : 'เซสชันครบ 24 ชั่วโมงแล้ว กำลังพาไปเข้าสู่ระบบใหม่'}
        </div>
      </div>
    )
  }

  if (remainingMs > 60 * 60 * 1000) return null

  return (
    <div className="fixed inset-x-0 top-0 z-[120] px-4 pt-3">
      <div className="mx-auto max-w-5xl rounded border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-100 shadow-2xl backdrop-blur">
        เซสชันนี้จะให้ล็อกอินใหม่ภายใน {formatRemaining(remainingMs)}
      </div>
    </div>
  )
}
