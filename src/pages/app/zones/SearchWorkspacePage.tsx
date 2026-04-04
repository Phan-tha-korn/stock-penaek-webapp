import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'

import { FieldLabel } from '../../../components/ui/FieldLabel'
import {
  fetchZoneCompare,
  fetchZoneHistory,
  fetchZoneQuickSearch,
  type CompareResult,
  type HistoricalPriceItem,
  type QuickSearchItem,
} from '../../../services/zones'

function inputClass() {
  return 'input-surface w-full rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-[color:var(--color-fg)]'
}

function viewButtonClass(active: boolean) {
  return `rounded border px-3 py-2 text-sm ${
    active
      ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)] text-black'
      : 'border-[color:var(--color-border)] text-[color:var(--color-muted)]'
  }`
}

export function SearchWorkspacePage() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const [searchItems, setSearchItems] = useState<QuickSearchItem[]>([])
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null)
  const [historyItems, setHistoryItems] = useState<HistoricalPriceItem[]>([])
  const [busy, setBusy] = useState(false)

  const view = params.get('view') || 'quick'
  const query = params.get('q') || ''
  const productId = params.get('product_id') || params.get('productId') || ''
  const canonicalGroupId = params.get('canonical_group_id') || params.get('groupId') || ''
  const quantity = params.get('quantity') || '1'
  const mode = params.get('mode') || 'active'
  const fromAt = params.get('fromAt') || ''
  const toAt = params.get('toAt') || ''

  const compareQuery = useMemo(
    () => ({
      product_id: productId || undefined,
      canonical_group_id: canonicalGroupId || undefined,
      quantity: Number(quantity || 1),
      mode,
    }),
    [canonicalGroupId, mode, productId, quantity]
  )

  async function runQuickSearch() {
    setBusy(true)
    try {
      setSearchItems(await fetchZoneQuickSearch({ q: query || undefined, limit: 20 }))
    } finally {
      setBusy(false)
    }
  }

  async function runCompare() {
    setBusy(true)
    try {
      setCompareResult(await fetchZoneCompare(compareQuery))
    } finally {
      setBusy(false)
    }
  }

  async function runHistory() {
    setBusy(true)
    try {
      setHistoryItems(
        await fetchZoneHistory({
          product_id: productId || undefined,
          canonical_group_id: canonicalGroupId || undefined,
          from_at: fromAt || undefined,
          to_at: toAt || undefined,
        })
      )
    } finally {
      setBusy(false)
    }
  }

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
          <h1 className="text-2xl font-semibold">{t('zones.search.title')}</h1>
          <p className="text-sm text-[color:var(--color-muted)]">{t('zones.search.subtitle')}</p>
        </div>
        <div className="flex gap-2 text-sm">
          <button className={viewButtonClass(view === 'quick')} onClick={() => patchSearch({ view: 'quick' })} type="button">
            {t('zones.search.quickTab')}
          </button>
          <button className={viewButtonClass(view === 'compare')} onClick={() => patchSearch({ view: 'compare' })} type="button">
            {t('zones.search.compareTab')}
          </button>
          <button className={viewButtonClass(view === 'history')} onClick={() => patchSearch({ view: 'history' })} type="button">
            {t('zones.search.historyTab')}
          </button>
        </div>
      </div>

      {view === 'quick' ? (
        <div className="surface-panel space-y-3 rounded p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <FieldLabel
              label={t('zones.search.quickLabel')}
              helper={t('zones.search.quickHelper')}
              example={t('zones.search.quickPlaceholder')}
              helpKey="search.quick"
            >
              <input
                className={inputClass()}
                value={query}
                onChange={(e) => patchSearch({ q: e.target.value })}
                placeholder={t('zones.search.quickPlaceholder')}
              />
            </FieldLabel>
            <button
              className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black md:self-end"
              onClick={() => void runQuickSearch()}
              type="button"
            >
              {t('zones.search.searchButton')}
            </button>
          </div>
          <div className="space-y-2">
            {searchItems.map((item) => (
              <div key={item.product_id} className="surface-item rounded px-3 py-2 text-sm">
                <div className="font-medium">
                  {item.sku} - {item.name_th || item.name_en}
                </div>
                <div className="text-[color:var(--color-muted)]">
                  {t('zones.search.groupName')}: {item.canonical_group_name || '-'}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Link
                    className="rounded border border-[color:var(--color-border)] px-2 py-1 text-[color:var(--color-fg)]"
                    to={`/products?productId=${item.product_id}&sku=${encodeURIComponent(item.sku)}`}
                  >
                    {t('zones.search.openProduct')}
                  </Link>
                  <button
                    className="rounded border border-[color:var(--color-border)] px-2 py-1 text-[color:var(--color-fg)]"
                    onClick={() =>
                      patchSearch({
                        view: 'compare',
                        product_id: item.product_id,
                        canonical_group_id: item.canonical_group_id || '',
                        quantity: '1',
                        mode: 'active',
                      })
                    }
                    type="button"
                  >
                    {t('zones.search.openCompare')}
                  </button>
                </div>
              </div>
            ))}
            {!busy && searchItems.length === 0 ? (
              <div className="text-sm text-[color:var(--color-muted)]">{t('zones.search.noQuickResults')}</div>
            ) : null}
          </div>
        </div>
      ) : null}

      {view === 'compare' ? (
        <div className="surface-panel space-y-3 rounded p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <FieldLabel label={t('zones.search.productId')} helpKey="search.compare">
              <input
                className={inputClass()}
                value={productId}
                onChange={(e) => patchSearch({ product_id: e.target.value, productId: '' })}
                placeholder={t('zones.search.productId')}
              />
            </FieldLabel>
            <FieldLabel label={t('zones.search.groupId')} helper={t('zones.search.groupLabel')}>
              <input
                className={inputClass()}
                value={canonicalGroupId}
                onChange={(e) => patchSearch({ canonical_group_id: e.target.value, groupId: '' })}
                placeholder={t('zones.search.groupId')}
              />
            </FieldLabel>
            <FieldLabel label={t('zones.search.quantity')} example={t('zones.search.quantityPlaceholder')}>
              <input
                className={inputClass()}
                value={quantity}
                onChange={(e) => patchSearch({ quantity: e.target.value })}
                placeholder={t('zones.search.quantityPlaceholder')}
              />
            </FieldLabel>
            <FieldLabel label={t('zones.search.selectionMode')}>
              <select className={inputClass()} value={mode} onChange={(e) => patchSearch({ mode: e.target.value })}>
                <option value="active">{t('zones.search.selectionModeActive')}</option>
                <option value="latest">{t('zones.search.selectionModeLatest')}</option>
              </select>
            </FieldLabel>
          </div>
          <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black" onClick={() => void runCompare()} type="button">
            {t('zones.search.compareButton')}
          </button>
          <div className="space-y-2">
            {(compareResult?.rows ?? []).map((row) => (
              <div key={row.price_record_id} className="surface-item rounded px-3 py-2 text-sm">
                <div className="font-medium">
                  {row.supplier_name} - {t('zones.search.resultCost', { amount: row.final_total_cost_thb.toFixed(2) })}
                </div>
                <div className="text-[color:var(--color-muted)]">
                  {row.sku} - {row.delivery_mode} - {row.area_scope} - {row.selection_mode}
                </div>
              </div>
            ))}
            {!busy && (compareResult?.rows.length ?? 0) === 0 ? (
              <div className="text-sm text-[color:var(--color-muted)]">{t('zones.search.noCompareRows')}</div>
            ) : null}
          </div>
        </div>
      ) : null}

      {view === 'history' ? (
        <div className="surface-panel space-y-3 rounded p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <FieldLabel label={t('zones.search.productId')} helpKey="search.history">
              <input
                className={inputClass()}
                value={productId}
                onChange={(e) => patchSearch({ product_id: e.target.value, productId: '' })}
                placeholder={t('zones.search.productId')}
              />
            </FieldLabel>
            <FieldLabel label={t('zones.search.groupId')}>
              <input
                className={inputClass()}
                value={canonicalGroupId}
                onChange={(e) => patchSearch({ canonical_group_id: e.target.value, groupId: '' })}
                placeholder={t('zones.search.groupId')}
              />
            </FieldLabel>
            <FieldLabel label={t('zones.search.historyFrom')}>
              <input className={inputClass()} type="datetime-local" value={fromAt} onChange={(e) => patchSearch({ fromAt: e.target.value })} />
            </FieldLabel>
            <FieldLabel label={t('zones.search.historyTo')}>
              <input className={inputClass()} type="datetime-local" value={toAt} onChange={(e) => patchSearch({ toAt: e.target.value })} />
            </FieldLabel>
          </div>
          <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black" onClick={() => void runHistory()} type="button">
            {t('zones.search.historyButton')}
          </button>
          <div className="space-y-2">
            {historyItems.map((row) => (
              <div key={row.price_record_id} className="surface-item rounded px-3 py-2 text-sm">
                <div className="font-medium">{t('zones.search.resultCost', { amount: row.final_total_cost_thb.toFixed(2) })}</div>
                <div className="text-[color:var(--color-muted)]">
                  {t('zones.search.historyWindow', { from: row.effective_at || '-', to: row.expire_at || 'open' })}
                </div>
              </div>
            ))}
            {!busy && historyItems.length === 0 ? (
              <div className="text-sm text-[color:var(--color-muted)]">{t('zones.search.noHistoryRows')}</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
