import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import i18n from '../../services/i18n'
import { updateConfig } from '../../services/config'
import { useAuthStore } from '../../store/authStore'
import { useConfigStore } from '../../store/configStore'
import type { AppConfig } from '../../types/models'
import { applyTheme, getPersonalBackgroundSettings, setPersonalBackgroundSettings } from '../../utils/theme'

function Field(props: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs text-white/70">{props.label}</div>
      {props.children}
    </label>
  )
}

export function SettingsPage() {
  const { t } = useTranslation()
  const config = useConfigStore((s) => s.config)
  const setConfig = useConfigStore((s) => s.setConfig)
  const role = useAuthStore((s) => s.role)
  const canManageGlobal = role === 'OWNER' || role === 'DEV'

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const initial = useMemo<AppConfig | null>(() => config, [config])
  const [form, setForm] = useState<AppConfig | null>(initial)
  const [personal, setPersonal] = useState(getPersonalBackgroundSettings())

  useEffect(() => {
    if (config) setForm(config)
  }, [config])

  if (!form) {
    return (
      <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-4 text-sm text-white/70">
        {t('app.loading')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">{t('settings.title')}</div>
        <div className="mt-1 text-xs text-white/60">{t('settings.subtitle')}</div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="mb-3 text-sm font-semibold">พื้นหลังส่วนตัว (ผู้ใช้คนนี้)</div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Field label="โหมดพื้นหลัง">
            <select
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={personal.mode}
              onChange={(e) =>
                setPersonal((prev) => ({ ...prev, mode: e.target.value as 'gradient' | 'plain' | 'image' }))
              }
            >
              <option value="gradient">ใช้ธีมระบบ</option>
              <option value="plain">สีพื้นเรียบ</option>
              <option value="image">รูปภาพพื้นหลัง</option>
            </select>
          </Field>
          <Field label="สีพื้นหลังส่วนตัว">
            <input
              className="h-10 w-full rounded border border-[color:var(--color-border)] bg-black/30"
              type="color"
              value={personal.color}
              onChange={(e) => setPersonal((prev) => ({ ...prev, color: e.target.value }))}
            />
          </Field>
          <Field label="URL รูปภาพพื้นหลังส่วนตัว">
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={personal.imageUrl}
              onChange={(e) => setPersonal((prev) => ({ ...prev, imageUrl: e.target.value }))}
              placeholder="https://..."
            />
            <input
              className="mt-2 block w-full text-xs text-white/70 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-black/30 file:px-3 file:py-2 file:text-xs file:text-white/80"
              type="file"
              accept="image/*"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (!file) return
                const reader = new FileReader()
                reader.onload = () => {
                  setPersonal((prev) => ({ ...prev, mode: 'image', imageUrl: String(reader.result || '') }))
                }
                reader.readAsDataURL(file)
              }}
            />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
            type="button"
            onClick={() => {
              const reset = { mode: 'gradient' as const, color: '#0D0D0D', imageUrl: '' }
              setPersonal(reset)
              setPersonalBackgroundSettings(reset)
              if (config) applyTheme(config)
            }}
          >
            รีเซ็ตพื้นหลังส่วนตัว
          </button>
          <button
            className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
            type="button"
            onClick={() => {
              setPersonalBackgroundSettings(personal)
              if (config) applyTheme(config)
            }}
          >
            บันทึกพื้นหลังส่วนตัว
          </button>
        </div>
      </div>

      {canManageGlobal ? (
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="mb-3 text-sm font-semibold">ตั้งค่าระบบหลัก (OWNER/DEV)</div>
        {error ? (
          <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        ) : null}
        {ok ? (
          <div className="mb-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
            {ok}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label={t('settings.appName')}>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={form.app_name}
              onChange={(e) => setForm({ ...form, app_name: e.target.value })}
            />
          </Field>

          <Field label={t('settings.webUrl')}>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={form.web_url}
              onChange={(e) => setForm({ ...form, web_url: e.target.value })}
              placeholder="https://example.com"
            />
          </Field>

          <Field label={t('settings.defaultLanguage')}>
            <select
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={form.default_language}
              onChange={(e) => setForm({ ...form, default_language: e.target.value as 'th' | 'en' })}
            >
              <option value="th">Thai</option>
              <option value="en">English</option>
            </select>
          </Field>

          <Field label={t('settings.primaryColor')}>
            <div className="flex items-center gap-2">
              <input
                className="h-10 w-12 rounded border border-[color:var(--color-border)] bg-black/30"
                type="color"
                value={form.primary_color}
                onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm font-mono outline-none focus:border-[color:var(--color-primary)]"
                value={form.primary_color}
                onChange={(e) => setForm({ ...form, primary_color: e.target.value })}
              />
            </div>
          </Field>

          <Field label={t('settings.secondaryColor')}>
            <div className="flex items-center gap-2">
              <input
                className="h-10 w-12 rounded border border-[color:var(--color-border)] bg-black/30"
                type="color"
                value={form.secondary_color}
                onChange={(e) => setForm({ ...form, secondary_color: e.target.value })}
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm font-mono outline-none focus:border-[color:var(--color-primary)]"
                value={form.secondary_color}
                onChange={(e) => setForm({ ...form, secondary_color: e.target.value })}
              />
            </div>
          </Field>

          <Field label={t('settings.sessionMax')}>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              type="number"
              min={1}
              max={10}
              value={form.session_max_per_user}
              onChange={(e) => setForm({ ...form, session_max_per_user: Number(e.target.value) })}
            />
          </Field>

          <Field label={t('settings.minStockThreshold')}>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              type="number"
              min={0}
              value={form.min_stock_threshold}
              onChange={(e) => setForm({ ...form, min_stock_threshold: Number(e.target.value) })}
            />
          </Field>

          <Field label={t('settings.backupIntervalHours')}>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              type="number"
              min={1}
              max={48}
              value={form.backup_interval_hours}
              onChange={(e) => setForm({ ...form, backup_interval_hours: Number(e.target.value) })}
            />
          </Field>

          <Field label={t('settings.maxBackupFiles')}>
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              type="number"
              min={1}
              max={120}
              value={form.max_backup_files}
              onChange={(e) => setForm({ ...form, max_backup_files: Number(e.target.value) })}
            />
          </Field>

          <Field label="โหมดพื้นหลังระบบ">
            <select
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={form.background_mode}
              onChange={(e) =>
                setForm({ ...form, background_mode: e.target.value as 'gradient' | 'plain' | 'image' })
              }
            >
              <option value="gradient">ไล่เฉดสีระบบ</option>
              <option value="plain">สีพื้นเรียบ</option>
              <option value="image">รูปพื้นหลังระบบ</option>
            </select>
          </Field>

          <Field label="สีพื้นหลังระบบ">
            <input
              className="h-10 w-full rounded border border-[color:var(--color-border)] bg-black/30"
              type="color"
              value={form.background_color}
              onChange={(e) => setForm({ ...form, background_color: e.target.value })}
            />
          </Field>

          <Field label="URL รูปพื้นหลังระบบ">
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              value={form.background_image_url}
              onChange={(e) => setForm({ ...form, background_image_url: e.target.value })}
              placeholder="https://..."
            />
          </Field>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <button
            className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
            type="button"
            onClick={() => {
              if (!config) return
              setForm(config)
              setError(null)
              setOk(null)
              applyTheme(config)
              document.title = config.app_name
              i18n.changeLanguage(config.default_language)
            }}
          >
            {t('settings.reset')}
          </button>
          <button
            className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              setError(null)
              setOk(null)
              try {
                const updated = await updateConfig(form)
                setConfig(updated)
                applyTheme(updated)
                document.title = updated.app_name
                i18n.changeLanguage(updated.default_language)
                setOk(t('settings.saved'))
              } catch (e: any) {
                const msg = e?.response?.data?.detail
                setError(typeof msg === 'string' ? msg : t('settings.saveFailed'))
              } finally {
                setBusy(false)
              }
            }}
          >
            {t('settings.save')}
          </button>
        </div>
        </div>
      ) : null}
    </div>
  )
}
