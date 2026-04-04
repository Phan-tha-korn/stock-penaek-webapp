import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'

import { FieldLabel } from '../../../components/ui/FieldLabel'
import { fetchZoneVerificationQueue, type VerificationQueueItem } from '../../../services/zones'
import { useAuthStore } from '../../../store/authStore'

function fieldClass() {
  return 'w-full rounded border border-[color:var(--color-border)] bg-black/20 px-3 py-2 text-sm text-[color:var(--color-fg)]'
}

export function VerificationWorkspacePage() {
  const { t } = useTranslation()
  const role = useAuthStore((s) => s.role)
  const [params, setParams] = useSearchParams()
  const [items, setItems] = useState<VerificationQueueItem[]>([])
  const [busy, setBusy] = useState(true)

  const requestId = params.get('requestId') || ''
  const status = params.get('status') || ''
  const risk = params.get('risk') || ''
  const assignee = params.get('assignee') || ''

  async function reload() {
    setBusy(true)
    try {
      const queue = await fetchZoneVerificationQueue({
        q: requestId || undefined,
        statuses: status || undefined,
        risk_levels: risk || undefined,
        assignee_user_id: assignee || undefined,
      })
      setItems(queue)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void reload()
    const timer = window.setInterval(() => void reload(), 15_000)
    return () => window.clearInterval(timer)
  }, [requestId, status, risk, assignee])

  function patchSearch(next: Record<string, string>) {
    const draft = new URLSearchParams(params)
    Object.entries(next).forEach(([key, value]) => {
      if (!value) draft.delete(key)
      else draft.set(key, value)
    })
    setParams(draft)
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('zones.verification.title')}</h1>
          <p className="text-sm text-[color:var(--color-muted)]">{t('zones.verification.subtitle')}</p>
        </div>
        <button className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm" onClick={() => void reload()} type="button">
          {t('zones.verification.refresh')}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <FieldLabel label={t('zones.verification.requestLabel')} example={t('zones.verification.requestPlaceholder')} helpKey="verification.queue">
          <input className={fieldClass()} value={requestId} onChange={(e) => patchSearch({ requestId: e.target.value })} placeholder={t('zones.verification.requestPlaceholder')} />
        </FieldLabel>
        <FieldLabel label={t('zones.verification.statusLabel')} example={t('zones.verification.statusPlaceholder')} helpKey="verification.filters">
          <input className={fieldClass()} value={status} onChange={(e) => patchSearch({ status: e.target.value })} placeholder={t('zones.verification.statusPlaceholder')} />
        </FieldLabel>
        <FieldLabel label={t('zones.verification.riskLabel')} example={t('zones.verification.riskPlaceholder')}>
          <input className={fieldClass()} value={risk} onChange={(e) => patchSearch({ risk: e.target.value })} placeholder={t('zones.verification.riskPlaceholder')} />
        </FieldLabel>
        <FieldLabel label={t('zones.verification.assigneeLabel')} example={role === 'DEV' ? 'me' : t('zones.verification.assigneePlaceholder')}>
          <input
            className={fieldClass()}
            value={assignee}
            onChange={(e) => patchSearch({ assignee: e.target.value })}
            placeholder={role === 'DEV' ? 'me' : t('zones.verification.assigneePlaceholder')}
          />
        </FieldLabel>
      </div>

      <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.request_id} className="rounded border border-white/10 px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{item.request_code}</div>
                <div className="text-[color:var(--color-muted)]">
                  {item.workflow_status} - {item.risk_level}
                </div>
              </div>
              <div className="mt-1 text-[color:var(--color-muted)]">
                {item.subject_domain} - {item.is_overdue ? t('zones.verification.overdueYes') : t('zones.verification.overdueNo')} -{' '}
                {item.has_blocking_dependency ? t('zones.verification.blockingYes') : t('zones.verification.blockingNo')}
              </div>
            </div>
          ))}
          {!busy && items.length === 0 ? <div className="text-sm text-[color:var(--color-muted)]">{t('zones.verification.empty')}</div> : null}
        </div>
      </div>
    </section>
  )
}
