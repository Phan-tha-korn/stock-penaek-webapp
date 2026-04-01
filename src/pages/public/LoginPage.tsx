import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'

import { login as loginApi, getMe } from '../../services/auth'
import { useAuthStore } from '../../store/authStore'

interface FormValues {
  username: string
  password: string
  totp?: string
  secret_phrase?: string
}

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const setSession = useAuthStore((s) => s.setSession)
  const setTokens = useAuthStore((s) => s.setTokens)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const reauthReason = (location.state as { reason?: string } | null)?.reason

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: { username: '', password: '', totp: '', secret_phrase: '' }
  })

  return (
    <div className="mx-auto flex min-h-screen max-w-lg items-center px-4">
      {busy ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 backdrop-blur-md">
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-[color:var(--color-card)]/90 p-6 text-center shadow-2xl">
            <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-white/15 border-t-[color:var(--color-primary)]" />
            <div className="mt-4 text-base font-semibold">กำลังเข้าสู่ระบบ</div>
            <div className="mt-1 text-sm text-white/60">กรุณารอสักครู่ ระบบกำลังตรวจสอบสิทธิ์และเตรียมข้อมูลให้พร้อม</div>
          </div>
        </div>
      ) : null}
      <div className="card w-full rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-5 backdrop-blur animate-fade-in">
        <div className="mb-4 text-lg font-semibold">{t('auth.loginTitle')}</div>
        {reauthReason === 'session_expired' ? (
          <div className="mb-3 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            เซสชันครบ 24 ชั่วโมงแล้ว กรุณาเข้าสู่ระบบใหม่เพื่อใช้งานต่อ
          </div>
        ) : null}
        {error ? (
          <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        ) : null}
        <form
          className="space-y-3"
          onSubmit={handleSubmit(async (values) => {
            setError(null)
            setBusy(true)
            try {
              const tokens = await loginApi(values)
              setTokens(tokens)
              const me = await getMe()
              setSession(me, tokens, { freshLogin: true })
              navigate('/')
            } catch (e: any) {
              const msg = e?.response?.data?.detail
              setError(typeof msg === 'string' ? msg : t('auth.invalidCredentials'))
            } finally {
              setBusy(false)
            }
          })}
        >
          <label className="block">
            <div className="mb-1 text-xs text-white/70">{t('auth.username')}</div>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              autoComplete="username"
              required
              {...register('username')}
            />
          </label>
          <label className="block">
            <div className="mb-1 text-xs text-white/70">{t('auth.password')}</div>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              autoComplete="current-password"
              type="password"
              required
              {...register('password')}
            />
          </label>
          <label className="block">
            <div className="mb-1 text-xs text-white/70">{t('auth.totp')}</div>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              inputMode="numeric"
              placeholder="123456"
              {...register('totp')}
            />
          </label>
          <div className="hidden">
            <label className="block">
              <div className="mb-1 text-xs text-white/70">{t('auth.secretPhrase')}</div>
              <input {...register('secret_phrase')} />
            </label>
          </div>
          <button
            className="w-full rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
            type="submit"
            disabled={busy}
          >
            {t('auth.submit')}
          </button>
        </form>
      </div>
    </div>
  )
}

