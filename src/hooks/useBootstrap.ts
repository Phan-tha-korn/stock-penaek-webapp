import { useEffect, useState } from 'react'

import { useAuthStore } from '../store/authStore'
import { useConfigStore } from '../store/configStore'
import { fetchConfig } from '../services/config'
import { getMe, refresh as refreshTokens } from '../services/auth'
import { initI18n, readLanguagePreference } from '../services/i18n'
import { useUiPreferencesStore } from '../store/uiPreferencesStore'
import { applyTheme, applyThemePreference } from '../utils/theme'

export function useBootstrap() {
  const [ready, setReady] = useState(false)
  const setConfig = useConfigStore((s) => s.setConfig)
  const themePreference = useUiPreferencesStore((s) => s.themePreference)
  const { tokens, setSession, clearSession } = useAuthStore()

  useEffect(() => {
    let cancelled = false

    async function run() {
      try {
        const cfg = await fetchConfig()
        setConfig(cfg)
        applyTheme(cfg)
        document.title = cfg.app_name
        applyThemePreference(themePreference)
        initI18n(readLanguagePreference(cfg.default_language))

        if (tokens?.access_token) {
          try {
            const me = await getMe()
            setSession(me, tokens)
          } catch {
            if (tokens?.refresh_token) {
              try {
                const newTokens = await refreshTokens(tokens.refresh_token)
                const me = await getMe()
                setSession(me, newTokens)
              } catch {
                clearSession()
              }
            } else {
              clearSession()
            }
          }
        }
      } finally {
        if (!cancelled) setReady(true)
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [themePreference])

  return { ready }
}

