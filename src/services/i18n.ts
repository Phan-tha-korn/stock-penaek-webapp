import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en.json'
import th from '../locales/th.json'

export type SupportedLocale = 'th' | 'en'

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

