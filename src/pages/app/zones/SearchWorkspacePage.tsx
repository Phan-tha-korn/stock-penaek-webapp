import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { fetchZoneCompare, fetchZoneHistory, fetchZoneQuickSearch, type CompareResult, type HistoricalPriceItem, type QuickSearchItem } from '../../../services/zones'

function inputClass() {
  return 'w-full rounded border border-[color:var(--color-border)] bg-black/20 px-3 py-2 text-sm'
}

export function SearchWorkspacePage() {
  const [params, setParams] = useSearchParams()
  const [searchItems, setSearchItems] = useState<QuickSearchItem[]>([])
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null)
  const [historyItems, setHistoryItems] = useState<HistoricalPriceItem[]>([])
  const [busy, setBusy] = useState(false)

  const view = params.get('view') || 'quick'
  const query = params.get('q') || ''
  const productId = params.get('productId') || ''
  const canonicalGroupId = params.get('groupId') || ''
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
          <h1 className="text-2xl font-semibold">Search & Compare</h1>
          <p className="text-sm text-white/60">Deep-link params: verification `requestId`, product `productId|sku`, compare `productId|groupId|quantity|mode`.</p>
        </div>
        <div className="flex gap-2 text-sm">
          <button className="rounded border border-[color:var(--color-border)] px-3 py-2" onClick={() => patchSearch({ view: 'quick' })} type="button">Quick</button>
          <button className="rounded border border-[color:var(--color-border)] px-3 py-2" onClick={() => patchSearch({ view: 'compare' })} type="button">Compare</button>
          <button className="rounded border border-[color:var(--color-border)] px-3 py-2" onClick={() => patchSearch({ view: 'history' })} type="button">History</button>
        </div>
      </div>

      {view === 'quick' ? (
        <div className="space-y-3 rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_auto]">
            <input className={inputClass()} value={query} onChange={(e) => patchSearch({ q: e.target.value })} placeholder="SKU / alias / name" />
            <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black" onClick={() => void runQuickSearch()} type="button">Search</button>
          </div>
          <div className="space-y-2">
            {searchItems.map((item) => (
              <div key={item.product_id} className="rounded border border-white/10 px-3 py-2 text-sm">
                <div className="font-medium">{item.sku} - {item.name_th || item.name_en}</div>
                <div className="text-white/70">Group: {item.canonical_group_name || '-'}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Link className="rounded border border-white/15 px-2 py-1" to={`/products?productId=${item.product_id}&sku=${encodeURIComponent(item.sku)}`}>Open Product</Link>
                  <button className="rounded border border-white/15 px-2 py-1" onClick={() => patchSearch({ view: 'compare', productId: item.product_id, groupId: item.canonical_group_id || '', quantity: '1', mode: 'active' })} type="button">Compare</button>
                </div>
              </div>
            ))}
            {!busy && searchItems.length === 0 ? <div className="text-sm text-white/50">No search results loaded.</div> : null}
          </div>
        </div>
      ) : null}

      {view === 'compare' ? (
        <div className="space-y-3 rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <input className={inputClass()} value={productId} onChange={(e) => patchSearch({ productId: e.target.value })} placeholder="productId" />
            <input className={inputClass()} value={canonicalGroupId} onChange={(e) => patchSearch({ groupId: e.target.value })} placeholder="groupId" />
            <input className={inputClass()} value={quantity} onChange={(e) => patchSearch({ quantity: e.target.value })} placeholder="quantity" />
            <select className={inputClass()} value={mode} onChange={(e) => patchSearch({ mode: e.target.value })}>
              <option value="active">active</option>
              <option value="latest">latest</option>
            </select>
          </div>
          <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black" onClick={() => void runCompare()} type="button">Run Compare</button>
          <div className="space-y-2">
            {(compareResult?.rows ?? []).map((row) => (
              <div key={row.price_record_id} className="rounded border border-white/10 px-3 py-2 text-sm">
                <div className="font-medium">{row.supplier_name} · {row.final_total_cost_thb.toFixed(2)} THB</div>
                <div className="text-white/70">{row.sku} · {row.delivery_mode} · {row.area_scope} · {row.selection_mode}</div>
              </div>
            ))}
            {!busy && (compareResult?.rows.length ?? 0) === 0 ? <div className="text-sm text-white/50">No comparison rows loaded.</div> : null}
          </div>
        </div>
      ) : null}

      {view === 'history' ? (
        <div className="space-y-3 rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4">
          <div className="grid gap-3 md:grid-cols-4">
            <input className={inputClass()} value={productId} onChange={(e) => patchSearch({ productId: e.target.value })} placeholder="productId" />
            <input className={inputClass()} value={canonicalGroupId} onChange={(e) => patchSearch({ groupId: e.target.value })} placeholder="groupId" />
            <input className={inputClass()} type="datetime-local" value={fromAt} onChange={(e) => patchSearch({ fromAt: e.target.value })} />
            <input className={inputClass()} type="datetime-local" value={toAt} onChange={(e) => patchSearch({ toAt: e.target.value })} />
          </div>
          <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black" onClick={() => void runHistory()} type="button">Load History</button>
          <div className="space-y-2">
            {historyItems.map((row) => (
              <div key={row.price_record_id} className="rounded border border-white/10 px-3 py-2 text-sm">
                <div className="font-medium">{row.final_total_cost_thb.toFixed(2)} THB</div>
                <div className="text-white/70">{row.effective_at || '-'} to {row.expire_at || 'open'}</div>
              </div>
            ))}
            {!busy && historyItems.length === 0 ? <div className="text-sm text-white/50">No history loaded.</div> : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
