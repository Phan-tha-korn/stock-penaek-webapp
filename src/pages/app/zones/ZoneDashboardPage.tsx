import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { fetchZoneSummary, type ZoneSummary } from '../../../services/zones'
import { useAuthStore } from '../../../store/authStore'

function cardClass() {
  return 'rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4'
}

const refreshMsByZone: Record<string, number> = {
  owner: 60_000,
  dev: 30_000,
  admin: 60_000,
  stock: 120_000,
}

export function ZoneDashboardPage(props: { zone: 'owner' | 'dev' | 'admin' | 'stock' }) {
  const { t } = useTranslation()
  const role = useAuthStore((s) => s.role)
  const [busy, setBusy] = useState(true)
  const [summary, setSummary] = useState<ZoneSummary | null>(null)

  async function reload() {
    setBusy(true)
    try {
      setSummary(await fetchZoneSummary(props.zone))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void reload()
    const timer = window.setInterval(() => void reload(), refreshMsByZone[props.zone] ?? 60_000)
    return () => window.clearInterval(timer)
  }, [props.zone])

  const links = useMemo(() => {
    if (props.zone === 'owner') {
      return [
        { to: '/zones/search', label: t('dashboard.quickLinks.ownerSearch') },
        { to: '/zones/verification', label: t('dashboard.quickLinks.ownerVerification') },
        { to: '/zones/notifications', label: t('dashboard.quickLinks.ownerNotifications') },
      ]
    }
    if (props.zone === 'dev') {
      return [
        { to: '/zones/verification?assignee=me', label: t('dashboard.quickLinks.devQueue') },
        { to: '/zones/search', label: t('dashboard.quickLinks.devSearch') },
        { to: '/zones/notifications', label: t('dashboard.quickLinks.devNotifications') },
      ]
    }
    if (props.zone === 'admin') {
      return [
        { to: '/suppliers', label: t('dashboard.quickLinks.adminSuppliers') },
        { to: '/zones/verification', label: t('dashboard.quickLinks.adminVerification') },
        { to: '/zones/notifications', label: t('dashboard.quickLinks.adminNotifications') },
      ]
    }
    return [
      { to: '/dashboard', label: t('dashboard.quickLinks.stockQuickSearch') },
      { to: '/zones/search?view=compare', label: t('dashboard.quickLinks.stockCompare') },
      { to: '/products', label: t('dashboard.quickLinks.stockProducts') },
    ]
  }, [props.zone, t])

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('dashboard.zoneTitle', { zone: props.zone })}</h1>
          <p className="text-sm text-[color:var(--color-muted)]">{t('dashboard.roleLabel', { role })}</p>
        </div>
        <button className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm" onClick={() => void reload()} type="button">
          {t('dashboard.refresh')}
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className={cardClass()}>
          <div className="text-xs text-[color:var(--color-muted)]">{t('dashboard.verificationPending')}</div>
          <div className="mt-2 text-2xl font-semibold">{busy ? '...' : summary?.verification?.pending ?? 0}</div>
        </div>
        <div className={cardClass()}>
          <div className="text-xs text-[color:var(--color-muted)]">{t('dashboard.overdueRetry')}</div>
          <div className="mt-2 text-2xl font-semibold">{busy ? '...' : `${summary?.verification?.overdue ?? 0} / ${summary?.notifications?.retrying ?? 0}`}</div>
        </div>
        <div className={cardClass()}>
          <div className="text-xs text-[color:var(--color-muted)]">{t('dashboard.activePrices')}</div>
          <div className="mt-2 text-2xl font-semibold">{busy ? '...' : summary?.pricing?.active_prices ?? 0}</div>
        </div>
        <div className={cardClass()}>
          <div className="text-xs text-[color:var(--color-muted)]">{props.zone === 'stock' ? t('dashboard.products') : t('dashboard.matchingWarnings')}</div>
          <div className="mt-2 text-2xl font-semibold">
            {busy ? '...' : props.zone === 'stock' ? summary?.catalog?.product_count ?? 0 : summary?.matching?.warning_count ?? 0}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className={cardClass()}>
          <h2 className="text-lg font-semibold">{t('dashboard.shortcuts')}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {links.map((link) => (
              <Link key={link.to} to={link.to} className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-medium text-black">
                {link.label}
              </Link>
            ))}
          </div>
        </div>
        <div className={cardClass()}>
          <h2 className="text-lg font-semibold">{t('dashboard.recentCriticalChanges')}</h2>
          <div className="mt-3 space-y-2 text-sm">
            {(summary?.recent_changes ?? []).slice(0, 5).map((item) => (
              <div key={item.id} className="rounded border border-white/10 px-3 py-2">
                <div className="font-medium">{item.action}</div>
                <div className="text-[color:var(--color-muted)]">
                  {item.entity} {item.entity_id ? `#${item.entity_id}` : ''}
                </div>
              </div>
            ))}
            {!busy && (summary?.recent_changes?.length ?? 0) === 0 ? <div className="text-[color:var(--color-muted)]">{t('dashboard.noRecentChanges')}</div> : null}
          </div>
        </div>
      </div>
    </section>
  )
}
