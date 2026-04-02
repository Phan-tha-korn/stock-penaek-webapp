import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchGoogleSetupConfig, startGoogleOAuthLogin, updateGoogleSetupConfig, type GoogleSetupConfig } from '../../services/configSecure'
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

const EMPTY_GOOGLE_CFG: GoogleSetupConfig = {
  configured: false,
  usable: false,
  error: '',
  workspace_email: '',
  drive_folder_name: '',
  default_sheet_title: '',
  service_account_key_path: '',
  oauth_client_id: '',
  oauth_client_secret_masked: '',
  oauth_redirect_uri: '',
  oauth_token_path: '',
  oauth_connected: false,
  current_sheet_id: '',
  current_sheet_url: '',
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
  const [googleCfg, setGoogleCfg] = useState<GoogleSetupConfig | null>(null)
  const [googleBusy, setGoogleBusy] = useState(false)
  const [googleOauthSecretDraft, setGoogleOauthSecretDraft] = useState('')
  const [googleWizardOpen, setGoogleWizardOpen] = useState(false)
  const [googleResultOpen, setGoogleResultOpen] = useState(false)
  const [googleResultOk, setGoogleResultOk] = useState(false)

  useEffect(() => {
    if (config) setForm(config)
  }, [config])

  useEffect(() => {
    if (!canManageGlobal) return
    fetchGoogleSetupConfig()
      .then((data) => {
        setGoogleCfg(data)
        setGoogleOauthSecretDraft('')
        setGoogleWizardOpen(!data.usable)
        const pending = window.localStorage.getItem('google_oauth_pending')
        if (pending) {
          window.localStorage.removeItem('google_oauth_pending')
          setGoogleResultOk(Boolean(data.usable))
          setGoogleResultOpen(true)
          window.setTimeout(() => setGoogleResultOpen(false), 3000)
        }
      })
      .catch((e: any) => {
        setError(e?.response?.data?.detail || 'โหลด Google setup ไม่สำเร็จ')
      })
  }, [canManageGlobal])

  if (!form) {
    return (
      <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-4 text-sm text-white/70">
        {t('app.loading')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {googleResultOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-md">
          <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[color:var(--color-card)]/95 p-6 text-center shadow-2xl">
            <div className="text-xl font-semibold">{googleResultOk ? 'เชื่อม Google สำเร็จ' : 'เชื่อม Google ไม่สำเร็จ'}</div>
            <div className="mt-2 text-sm text-white/65">
              {googleResultOk ? 'เชื่อมแล้วและข้อมูลพร้อมใช้งาน สามารถกลับไปใช้งานโซน Google Sheets ได้เลย' : 'ข้อมูลยังไม่พร้อมใช้งาน กรุณาตรวจสอบ Client ID/Secret และ Redirect URI แล้วลองใหม่'}
            </div>
          </div>
        </div>
      ) : null}
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
          <Field label="สีไล่เฉดเริ่มต้น">
            <input
              className="h-10 w-full rounded border border-[color:var(--color-border)] bg-black/30"
              type="color"
              value={form.background_gradient_from}
              onChange={(e) => setForm({ ...form, background_gradient_from: e.target.value })}
            />
          </Field>
          <Field label="สีไล่เฉดปลายทาง">
            <input
              className="h-10 w-full rounded border border-[color:var(--color-border)] bg-black/30"
              type="color"
              value={form.background_gradient_to}
              onChange={(e) => setForm({ ...form, background_gradient_to: e.target.value })}
            />
          </Field>
          <Field label="สีแสงเสริม">
            <input
              className="h-10 w-full rounded border border-[color:var(--color-border)] bg-black/30"
              type="color"
              value={form.background_gradient_accent}
              onChange={(e) => setForm({ ...form, background_gradient_accent: e.target.value })}
            />
          </Field>
          <Field label="ความเบลอพื้นหลัง (px)">
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              type="number"
              min={0}
              max={48}
              value={form.background_blur_px}
              onChange={(e) => setForm({ ...form, background_blur_px: Number(e.target.value) })}
            />
          </Field>
          <Field label="ความเข้ม overlay (%)">
            <input
              className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
              type="number"
              min={0}
              max={95}
              value={form.background_overlay_opacity}
              onChange={(e) => setForm({ ...form, background_overlay_opacity: Number(e.target.value) })}
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

      {canManageGlobal ? (
        <div id="google-setup" className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Google Sheets Setup Wizard</div>
              <div className="mt-1 text-xs text-white/60">เชื่อม Google เพื่อให้ระบบสร้างชีตอัตโนมัติ และ sync ข้อมูลขึ้น Google Sheets</div>
            </div>
            {googleCfg?.usable ? (
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-xs text-white/80 hover:bg-white/10"
                type="button"
                onClick={() => setGoogleWizardOpen((prev) => !prev)}
              >
                {googleWizardOpen ? 'ยุบ' : 'แก้ไข/เปลี่ยน Google'}
              </button>
            ) : null}
          </div>

          <div className={`mt-3 rounded border ${googleCfg?.usable ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100' : 'border-amber-500/30 bg-amber-500/10 text-amber-100'} px-3 py-2 text-xs`}>
            {googleCfg?.usable
              ? `เชื่อมแล้วและข้อมูลใช้ได้ • Sheet: ${googleCfg.current_sheet_id || '-'}`
              : `ยังใช้ Google Sheets ไม่ได้ • สาเหตุ: ${googleCfg?.error || 'not_configured'}`}
          </div>
          {!googleCfg?.usable ? (
            <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3 text-xs text-white/65">
              <div className="font-semibold text-white/85">วิธีแก้แบบเร็ว</div>
              <div className="mt-2 space-y-1">
                <div>- ใส่ OAuth Client ID/Secret ให้ครบ แล้วกด Sign in with Google</div>
                <div>- ตรวจว่า Redirect URI ใน Google Cloud Console ตรงกับที่ใส่ในช่อง OAuth Redirect URI</div>
                <div>- ถ้า Sheet หาย/ลิงก์เสีย ให้กด “เชื่อม Google และสร้าง Sheets อัตโนมัติ” เพื่อสร้างใหม่ แล้วระบบจะ sync ข้อมูลจากฐานข้อมูลขึ้นชีตใหม่ให้</div>
                <div>- ถ้าข้อมูลเก่าอยู่ในชีตเดิมอย่างเดียว ให้ไปหน้า Dev แล้วกด Import Stock → DB จากชีตเดิมก่อน จากนั้นค่อย sync ไปชีตใหม่</div>
              </div>
            </div>
          ) : null}

          {!googleWizardOpen && googleCfg?.usable ? null : (
            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label="Gmail ที่ใช้ดูแล Google Drive">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.workspace_email || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), workspace_email: e.target.value }))}
                placeholder="owner@gmail.com"
              />
            </Field>
            <Field label="ชื่อโฟลเดอร์ใน Google Drive">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.drive_folder_name || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), drive_folder_name: e.target.value }))}
                placeholder="Stock Penaek Drive"
              />
            </Field>
            <Field label="ชื่อไฟล์ Sheets หลัก">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.default_sheet_title || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), default_sheet_title: e.target.value }))}
                placeholder="Stock Penaek Master"
              />
            </Field>
            <Field label="Path ไฟล์ Google credentials">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.service_account_key_path || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), service_account_key_path: e.target.value }))}
                placeholder="C:\Stock Penaek Webapp\credentials\google_key.json"
              />
            </Field>
            <Field label="Google OAuth Client ID">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.oauth_client_id || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), oauth_client_id: e.target.value }))}
                placeholder="Google OAuth Client ID"
              />
            </Field>
            <Field label="Google OAuth Client Secret">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                type="password"
                value={googleOauthSecretDraft}
                onChange={(e) => setGoogleOauthSecretDraft(e.target.value)}
                placeholder={googleCfg?.oauth_client_secret_masked ? `ตั้งค่าแล้ว ${googleCfg.oauth_client_secret_masked}` : 'Google OAuth Client Secret'}
              />
            </Field>
            <Field label="OAuth Redirect URI">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.oauth_redirect_uri || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), oauth_redirect_uri: e.target.value }))}
                placeholder="https://api.example.com/api/config/google-oauth/callback"
              />
            </Field>
            <Field label="OAuth Token Path">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={googleCfg?.oauth_token_path || ''}
                onChange={(e) => setGoogleCfg((prev) => ({ ...(prev || EMPTY_GOOGLE_CFG), oauth_token_path: e.target.value }))}
                placeholder="C:\Stock Penaek Webapp\credentials\google_oauth_token.json"
              />
            </Field>
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-50"
              type="button"
              disabled={googleBusy || !googleCfg}
              onClick={async () => {
                if (!googleCfg) return
                setGoogleBusy(true)
                setError(null)
                setOk(null)
                try {
                  const next = await updateGoogleSetupConfig({
                    workspace_email: googleCfg.workspace_email,
                    drive_folder_name: googleCfg.drive_folder_name,
                    default_sheet_title: googleCfg.default_sheet_title,
                    service_account_key_path: googleCfg.service_account_key_path,
                    oauth_client_id: googleCfg.oauth_client_id,
                    oauth_client_secret: googleOauthSecretDraft,
                    oauth_redirect_uri: googleCfg.oauth_redirect_uri,
                    oauth_token_path: googleCfg.oauth_token_path,
                    create_new_sheet: false,
                    migrate_existing_data: false,
                  })
                  setGoogleCfg(next)
                  setGoogleOauthSecretDraft('')
                  setOk('บันทึกข้อมูล Google แล้ว')
                } catch (e: any) {
                  setError(e?.response?.data?.detail || 'บันทึก Google config ไม่สำเร็จ')
                } finally {
                  setGoogleBusy(false)
                }
              }}
            >
              บันทึกข้อมูล Google
            </button>
            <button
              className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-50"
              type="button"
              disabled={googleBusy || !googleCfg}
              onClick={async () => {
                if (!googleCfg) return
                setGoogleBusy(true)
                setError(null)
                setOk(null)
                try {
                  const next = await updateGoogleSetupConfig({
                    workspace_email: googleCfg.workspace_email,
                    drive_folder_name: googleCfg.drive_folder_name,
                    default_sheet_title: googleCfg.default_sheet_title,
                    service_account_key_path: googleCfg.service_account_key_path,
                    oauth_client_id: googleCfg.oauth_client_id,
                    oauth_client_secret: googleOauthSecretDraft,
                    oauth_redirect_uri: googleCfg.oauth_redirect_uri,
                    oauth_token_path: googleCfg.oauth_token_path,
                    create_new_sheet: true,
                    migrate_existing_data: true,
                  })
                  setGoogleCfg(next)
                  setGoogleOauthSecretDraft('')
                  setOk('สร้าง/สลับ Google Sheets ใหม่และ sync ข้อมูลแล้ว')
                } catch (e: any) {
                  setError(e?.response?.data?.detail || 'ตั้งค่า Google ไม่สำเร็จ')
                } finally {
                  setGoogleBusy(false)
                }
              }}
            >
              {googleBusy ? 'กำลังเชื่อม Google...' : 'เชื่อม Google และสร้าง Sheets อัตโนมัติ'}
            </button>
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-50"
              type="button"
              disabled={
                googleBusy ||
                !googleCfg?.oauth_client_id ||
                (!googleOauthSecretDraft.trim() && !googleCfg?.oauth_client_secret_masked) ||
                !((googleCfg?.oauth_redirect_uri || '').trim() || (form?.web_url || '').trim())
              }
              onClick={async () => {
                if (!googleCfg) return
                setGoogleBusy(true)
                setError(null)
                setOk(null)
                try {
                  const apiBaseUrl = String((import.meta as any).env?.VITE_API_URL || `${window.location.origin}/api`).replace(/\/+$/, '')
                  const apiOrigin = apiBaseUrl.endsWith('/api') ? apiBaseUrl.slice(0, -4) : apiBaseUrl
                  const savedRedirectUri = (googleCfg.oauth_redirect_uri || '').trim()
                  let redirectUri = `${apiOrigin}/api/config/google-oauth/callback`
                  if (savedRedirectUri) {
                    try {
                      const saved = new URL(savedRedirectUri)
                      const current = new URL(apiOrigin)
                      const sameOrigin = saved.origin === current.origin
                      redirectUri = sameOrigin ? savedRedirectUri : `${apiOrigin}/api/config/google-oauth/callback`
                    } catch {
                      redirectUri = `${apiOrigin}/api/config/google-oauth/callback`
                    }
                  }
                  const next = await updateGoogleSetupConfig({
                    workspace_email: googleCfg.workspace_email || '',
                    drive_folder_name: googleCfg.drive_folder_name || '',
                    default_sheet_title: googleCfg.default_sheet_title || '',
                    service_account_key_path: googleCfg.service_account_key_path || '',
                    oauth_client_id: googleCfg.oauth_client_id || '',
                    oauth_client_secret: googleOauthSecretDraft,
                    oauth_redirect_uri: redirectUri,
                    oauth_token_path: googleCfg.oauth_token_path || '',
                    create_new_sheet: false,
                    migrate_existing_data: false,
                  })
                  setGoogleCfg(next)
                  setGoogleOauthSecretDraft('')
                  window.localStorage.setItem('google_oauth_pending', '1')
                  const returnTo = `${window.location.origin}/settings#google-setup`
                  const res = await startGoogleOAuthLogin(returnTo)
                  setOk('กำลังพาไปหน้า Sign in with Google...')
                  window.location.assign(res.auth_url)
                } catch (e: any) {
                  setError(e?.response?.data?.detail || 'เริ่ม Google OAuth ไม่สำเร็จ')
                } finally {
                  setGoogleBusy(false)
                }
              }}
            >
              Sign in with Google
            </button>
            {googleCfg?.current_sheet_url ? (
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={() => window.open(googleCfg.current_sheet_url, '_blank', 'noopener,noreferrer')}
              >
                เปิดชีตปัจจุบัน
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
