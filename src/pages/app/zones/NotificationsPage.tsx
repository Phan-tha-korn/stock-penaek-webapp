import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { fetchZoneNotifications, type NotificationCenterSummary } from '../../../services/zones'

function buildNotificationTargetPath(item: NotificationCenterSummary['items'][number]) {
  if (item.target_path) {
    return item.target_path
  }
  if (item.source_domain === 'verification' && item.source_entity_id) {
    return `/zones/verification?requestId=${encodeURIComponent(item.source_entity_id)}`
  }
  if (item.source_domain === 'pricing' && item.source_entity_id) {
    return `/zones/search?view=compare&productId=${encodeURIComponent(item.source_entity_id)}&mode=active&quantity=1`
  }
  if (item.source_domain === 'supplier' && item.source_entity_id) {
    return `/suppliers?proposalId=${encodeURIComponent(item.source_entity_id)}`
  }
  return '/zones/search'
}

export function NotificationsPage() {
  const [busy, setBusy] = useState(true)
  const [data, setData] = useState<NotificationCenterSummary | null>(null)

  async function reload() {
    setBusy(true)
    try {
      setData(await fetchZoneNotifications())
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void reload()
    const timer = window.setInterval(() => void reload(), 30_000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Notification Center</h1>
          <p className="text-sm text-white/60">Summary widgets poll. Heavy drill-down stays manual.</p>
        </div>
        <button className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm" onClick={() => void reload()} type="button">
          Refresh
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
          <div className="text-xs text-white/60">Pending / Retrying</div>
          <div className="mt-2 text-2xl font-semibold">{busy ? '...' : data?.summary.pending_total ?? 0}</div>
        </div>
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
          <div className="text-xs text-white/60">Failed</div>
          <div className="mt-2 text-2xl font-semibold">{busy ? '...' : data?.summary.failed_total ?? 0}</div>
        </div>
      </div>

      <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
        <div className="space-y-2">
          {(data?.items ?? []).map((item) => (
            <div key={item.outbox_id} className="rounded border border-white/10 px-3 py-2 text-sm">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{item.message_title || item.event_type}</div>
                <div className="text-white/60">{item.status} · {item.severity}</div>
              </div>
              <div className="mt-1 text-white/70">{item.source_domain} · {item.routing_role || '-'}</div>
              <div className="mt-2">
                <Link className="rounded border border-white/15 px-2 py-1" to={buildNotificationTargetPath(item)}>
                  Open related item
                </Link>
              </div>
            </div>
          ))}
          {!busy && (data?.items.length ?? 0) === 0 ? <div className="text-sm text-white/50">No recent notifications.</div> : null}
        </div>
      </div>
    </section>
  )
}
