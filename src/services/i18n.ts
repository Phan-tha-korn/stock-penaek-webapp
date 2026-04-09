import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en.json'
import th from '../locales/th.json'

export type SupportedLocale = 'th' | 'en'
const LANGUAGE_PREFERENCE_KEY = 'esp_language_preference_v1'

export function readLanguagePreference(fallback: SupportedLocale): SupportedLocale {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_PREFERENCE_KEY)
    if (stored === 'th' || stored === 'en') return stored
  } catch {
  }
  return fallback
}

export async function changeLanguagePreference(next: SupportedLocale) {
  try {
    window.localStorage.setItem(LANGUAGE_PREFERENCE_KEY, next)
  } catch {
  }
  await i18n.changeLanguage(next)
}

export function initI18n(initialLng: SupportedLocale) {
  if (i18n.isInitialized) return i18n

  return i18n.use(initReactI18next).init({
    resources: {
      en: { translation: en },
      th: { translation: th }
    },
    lng: initialLng,
    fallbackLng: 'th',
    interpolation: { escapeValue: false }
  })
}

export default i18n

