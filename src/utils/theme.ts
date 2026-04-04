import type { AppConfig } from '../types/models'
import type { ThemePreference } from '../store/uiPreferencesStore'

const PERSONAL_BG_KEY = 'esp_personal_bg_v1'

type BgMode = 'gradient' | 'plain' | 'image'

interface PersonalBackgroundSettings {
  mode: BgMode
  color: string
  imageUrl: string
}

const defaultPersonalSettings: PersonalBackgroundSettings = {
  mode: 'gradient',
  color: '#0D0D0D',
  imageUrl: ''
}

export function resolveThemePreference(preference: ThemePreference): 'light' | 'dark' {
  if (preference === 'light' || preference === 'dark') return preference
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'dark'
  }
}

export function applyThemePreference(preference: ThemePreference) {
  const root = document.documentElement
  const resolved = resolveThemePreference(preference)
  root.setAttribute('data-theme-preference', preference)
  root.setAttribute('data-theme', resolved)
}

export function getPersonalBackgroundSettings(): PersonalBackgroundSettings {
  try {
    const raw = localStorage.getItem(PERSONAL_BG_KEY)
    if (!raw) return defaultPersonalSettings
    const parsed = JSON.parse(raw) as Partial<PersonalBackgroundSettings>
    const mode: BgMode = parsed.mode === 'plain' || parsed.mode === 'image' ? parsed.mode : 'gradient'
    return {
      mode,
      color: parsed.color || defaultPersonalSettings.color,
      imageUrl: parsed.imageUrl || ''
    }
  } catch {
    return defaultPersonalSettings
  }
}

export function setPersonalBackgroundSettings(next: PersonalBackgroundSettings) {
  localStorage.setItem(PERSONAL_BG_KEY, JSON.stringify(next))
}

function applyBackground(mode: BgMode, color: string, imageUrl: string) {
  const root = document.documentElement
  root.setAttribute('data-app-bg-mode', mode)
  root.style.setProperty('--app-bg-mode', mode)
  root.style.setProperty('--app-bg-color', color || '#0D0D0D')
  root.style.setProperty('--app-bg-image', imageUrl ? `url("${imageUrl}")` : 'none')
}

export function applyTheme(
  cfg: Pick<
    AppConfig,
    | 'primary_color'
    | 'secondary_color'
    | 'background_mode'
    | 'background_color'
    | 'background_image_url'
    | 'background_gradient_from'
    | 'background_gradient_to'
    | 'background_gradient_accent'
    | 'background_blur_px'
    | 'background_overlay_opacity'
  >
) {
  const root = document.documentElement
  root.style.setProperty('--color-primary', cfg.primary_color)
  root.style.setProperty('--color-secondary', cfg.secondary_color)
  root.style.setProperty('--app-bg-gradient-from', cfg.background_gradient_from || '#0D0D0D')
  root.style.setProperty('--app-bg-gradient-to', cfg.background_gradient_to || '#101826')
  root.style.setProperty('--app-bg-gradient-accent', cfg.background_gradient_accent || '#1E6FD9')
  root.style.setProperty('--app-bg-blur', `${Math.max(0, Number(cfg.background_blur_px || 0))}px`)
  root.style.setProperty('--app-bg-overlay-opacity', `${Math.max(0, Math.min(95, Number(cfg.background_overlay_opacity || 35))) / 100}`)
  applyBackground(cfg.background_mode, cfg.background_color, cfg.background_image_url)

  const personal = getPersonalBackgroundSettings()
  if (personal.mode !== 'gradient') {
    applyBackground(personal.mode, personal.color, personal.imageUrl)
  }
}

