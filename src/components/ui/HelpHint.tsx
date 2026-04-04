import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { SupportedLocale } from '../../services/i18n'
import { loadHelpEntry } from '../../services/helpContent'
import { useUiPreferencesStore } from '../../store/uiPreferencesStore'

export function HelpHint(props: { helpKey: string }) {
  const { i18n, t } = useTranslation()
  const helpMode = useUiPreferencesStore((state) => state.helpMode)
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [entry, setEntry] = useState<Awaited<ReturnType<typeof loadHelpEntry>>>(null)

  if (!helpMode) return null

  async function toggleOpen() {
    if (open) {
      setOpen(false)
      return
    }
    if (!entry) {
      setLoading(true)
      try {
        const loaded = await loadHelpEntry((i18n.language === 'en' ? 'en' : 'th') as SupportedLocale, props.helpKey)
        setEntry(loaded)
      } finally {
        setLoading(false)
      }
    }
    setOpen(true)
  }

  return (
    <span className="relative inline-flex items-center">
      <button
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-[color:var(--color-border)] bg-black/20 text-[11px] font-semibold text-white/80 hover:bg-white/10"
        type="button"
        aria-label={t('help.open')}
        onClick={() => void toggleOpen()}
      >
        ?
      </button>
      {open ? (
        <div className="absolute left-0 top-7 z-30 w-72 rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-3 text-xs text-white shadow-2xl">
          {loading ? (
            <div className="text-white/70">{t('help.loading')}</div>
          ) : entry ? (
            <div className="space-y-2">
              <div className="font-semibold text-white">{entry.title}</div>
              <div className="text-white/75">{entry.body}</div>
              {entry.example ? <div className="rounded-lg bg-black/20 px-2 py-1 text-white/65">{entry.example}</div> : null}
            </div>
          ) : (
            <div className="text-white/70">{t('help.empty')}</div>
          )}
        </div>
      ) : null}
    </span>
  )
}
