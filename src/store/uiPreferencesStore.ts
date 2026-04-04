import { create } from 'zustand'

export type ThemePreference = 'light' | 'dark' | 'system'

interface UiPreferencesState {
  helpMode: boolean
  themePreference: ThemePreference
  setHelpMode: (next: boolean) => void
  toggleHelpMode: () => void
  setThemePreference: (next: ThemePreference) => void
}

const HELP_MODE_KEY = 'esp_help_mode_v1'
const THEME_PREFERENCE_KEY = 'esp_theme_preference_v1'

function readHelpMode(): boolean {
  try {
    return window.localStorage.getItem(HELP_MODE_KEY) === '1'
  } catch {
    return false
  }
}

function readThemePreference(): ThemePreference {
  try {
    const value = window.localStorage.getItem(THEME_PREFERENCE_KEY)
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
  }
  return 'system'
}

export const useUiPreferencesStore = create<UiPreferencesState>((set) => ({
  helpMode: typeof window !== 'undefined' ? readHelpMode() : false,
  themePreference: typeof window !== 'undefined' ? readThemePreference() : 'system',
  setHelpMode: (next) =>
    set(() => {
      try {
        window.localStorage.setItem(HELP_MODE_KEY, next ? '1' : '0')
      } catch {
      }
      return { helpMode: next }
    }),
  toggleHelpMode: () =>
    set((state) => {
      const next = !state.helpMode
      try {
        window.localStorage.setItem(HELP_MODE_KEY, next ? '1' : '0')
      } catch {
      }
      return { helpMode: next }
    }),
  setThemePreference: (next) =>
    set(() => {
      try {
        window.localStorage.setItem(THEME_PREFERENCE_KEY, next)
      } catch {
      }
      return { themePreference: next }
    }),
}))
