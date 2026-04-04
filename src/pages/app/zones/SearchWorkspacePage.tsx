import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'

import { FieldLabel } from '../../../components/ui/FieldLabel'
import {
  fetchZoneCompare,
  fetchZoneHistory,
  fetchZoneQuickSearch,
  type CompareResult,
  type CompareResultRow,
  type HistoricalPriceItem,
  type QuickSearchItem,
} from '../../../services/zones'

const MAX_COMPARE_ITEMS = 20
const MIN_COMPARE_ITEMS = 2

type CompareSelection = {
  compareKey: string
  productId: string
  canonicalGroupId: string | null
  canonicalGroupName: string
  sku: string
  name: string
}

type QuickCompareSummaryRow = {
  compareKey: string
  productId: string
  sku: string
  name: string
  canonicalGroupName: string
  bestRow: CompareResultRow | null
  matchedRowCount: number
}

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

function compareKeyFor(item: Pick<QuickSearchItem, 'product_id' | 'canonical_group_id'>) {
  return item.canonical_group_id ? `group:${item.canonical_group_id}` : `product:${item.product_id}`
}

function toSelection(item: QuickSearchItem): CompareSelection {
  return {
    compareKey: compareKeyFor(item),
    productId: item.product_id,
    canonicalGroupId: item.canonical_group_id,
    canonicalGroupName: item.canonical_group_name || '',
    sku: item.sku,
    name: item.name_th || item.name_en || item.sku,
  }
}

export function SearchWorkspacePage() {
  const { t, i18n } = useTranslation()
  const [params, setParams] = useSearchParams()
  const [searchItems, setSearchItems] = useState<QuickSearchItem[]>([])
  const [quickBusy, setQuickBusy] = useState(false)
  const [compareBusy, setCompareBusy] = useState(false)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [compareSuggestions, setCompareSuggestions] = useState<QuickSearchItem[]>([])
  const [selectedCompareItems, setSelectedCompareItems] = useState<CompareSelection[]>([])
  const [quickCompareRows, setQuickCompareRows] = useState<QuickCompareSummaryRow[]>([])
  const [legacyCompareResult, setLegacyCompareResult] = useState<CompareResult | null>(null)
  const [historyItems, setHistoryItems] = useState<HistoricalPriceItem[]>([])
  const [compareInput, setCompareInput] = useState('')
  const [compareNotice, setCompareNotice] = useState('')

  const isEn = i18n.language === 'en'
  const view = params.get('view') || 'quick'
  const query = params.get('q') || ''
  const productId = params.get('product_id') || params.get('productId') || ''
  const canonicalGroupId = params.get('canonical_group_id') || params.get('groupId') || ''
  const quantity = params.get('quantity') || '1'
  const mode = params.get('mode') || 'active'
  const fromAt = params.get('fromAt') || ''
  const toAt = params.get('toAt') || ''

  const quickCompareSummary = useMemo(() => {
    const pricedRows = quickCompareRows.filter((row) => row.bestRow)
    const cheapest = pricedRows
      .slice()
      .sort((left, right) => (left.bestRow?.final_total_cost_thb || Number.MAX_SAFE_INTEGER) - (right.bestRow?.final_total_cost_thb || Number.MAX_SAFE_INTEGER))[0]
    return {
      selectedCount: selectedCompareItems.length,
      comparableCount: pricedRows.length,
      cheapestName: cheapest?.name || '',
      cheapestCost: cheapest?.bestRow?.final_total_cost_thb ?? null,
    }
  }, [quickCompareRows, selectedCompareItems.length])

  function patchSearch(next: Record<string, string>) {
    const draft = new URLSearchParams(params)
    Object.entries(next).forEach(([key, value]) => {
      if (!value) draft.delete(key)
      else draft.set(key, value)
    })
    setParams(draft)
  }

  async function runQuickSearch(searchTerm: string) {
    setQuickBusy(true)
    try {
      setSearchItems(await fetchZoneQuickSearch({ q: searchTerm || undefined, limit: 12 }))
    } finally {
      setQuickBusy(false)
    }
  }

  async function runHistory() {
    setHistoryBusy(true)
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
      setHistoryBusy(false)
    }
  }

  function addCompareItem(item: QuickSearchItem) {
    const nextItem = toSelection(item)
    if (selectedCompareItems.some((entry) => entry.compareKey === nextItem.compareKey)) {
      setCompareNotice(isEn ? 'This item is already selected.' : 'สินค้านี้ถูกเลือกไว้แล้ว')
      return
    }
    if (selectedCompareItems.length >= MAX_COMPARE_ITEMS) {
      setCompareNotice(isEn ? 'You can compare up to 20 items at once.' : 'เทียบได้พร้อมกันสูงสุด 20 รายการ')
      return
    }
    setSelectedCompareItems((current) => [...current, nextItem])
    setCompareSuggestions([])
    setCompareInput('')
    setCompareNotice('')
    patchSearch({ view: 'compare', product_id: '', canonical_group_id: '', productId: '', groupId: '' })
  }

  function removeCompareItem(compareKey: string) {
    setSelectedCompareItems((current) => current.filter((item) => item.compareKey !== compareKey))
    setCompareNotice('')
  }

  async function runLegacyCompare() {
    if (!productId && !canonicalGroupId) {
      setLegacyCompareResult(null)
      return
    }
    setCompareBusy(true)
    setCompareNotice('')
    try {
      setLegacyCompareResult(
        await fetchZoneCompare({
          product_id: productId || undefined,
          canonical_group_id: canonicalGroupId || undefined,
          quantity: Number(quantity || 1),
          mode,
        })
      )
    } finally {
      setCompareBusy(false)
    }
  }

  async function runQuickCompare(items: CompareSelection[]) {
    if (items.length < MIN_COMPARE_ITEMS) {
      setQuickCompareRows([])
      setCompareNotice(
        isEn
          ? `Select at least ${MIN_COMPARE_ITEMS - items.length} more item before comparing.`
          : `เลือกสินค้าเพิ่มอีก ${MIN_COMPARE_ITEMS - items.length} รายการก่อนเริ่มเทียบ`
      )
      return
    }
    setCompareBusy(true)
    setCompareNotice('')
    try {
      const settled = await Promise.allSettled(
        items.map(async (item) => {
          const result = await fetchZoneCompare({
            product_id: item.productId,
            canonical_group_id: item.canonicalGroupId || undefined,
            quantity: Number(quantity || 1),
            mode,
          })
          return {
            item,
            rows: result.rows,
          }
        })
      )

      const nextRows: QuickCompareSummaryRow[] = settled.map((entry, index) => {
        if (entry.status !== 'fulfilled') {
          return {
            compareKey: items[index].compareKey,
            productId: items[index].productId,
            sku: items[index].sku,
            name: items[index].name,
            canonicalGroupName: items[index].canonicalGroupName,
            bestRow: null,
            matchedRowCount: 0,
          }
        }
        return {
          compareKey: entry.value.item.compareKey,
          productId: entry.value.item.productId,
          sku: entry.value.item.sku,
          name: entry.value.item.name,
          canonicalGroupName: entry.value.item.canonicalGroupName,
          bestRow: entry.value.rows[0] || null,
          matchedRowCount: entry.value.rows.length,
        }
      })

      nextRows.sort((left, right) => {
        const leftValue = left.bestRow?.final_total_cost_thb ?? Number.MAX_SAFE_INTEGER
        const rightValue = right.bestRow?.final_total_cost_thb ?? Number.MAX_SAFE_INTEGER
        if (leftValue !== rightValue) return leftValue - rightValue
        return left.sku.localeCompare(right.sku)
      })
      setQuickCompareRows(nextRows)
      setLegacyCompareResult(null)
    } finally {
      setCompareBusy(false)
    }
  }

  useEffect(() => {
    if (view !== 'quick') return
    const timer = window.setTimeout(() => {
      void runQuickSearch(query)
    }, 220)
    return () => window.clearTimeout(timer)
  }, [query, view])

  useEffect(() => {
    if (view !== 'compare') return
    const timer = window.setTimeout(async () => {
      try {
        const items = await fetchZoneQuickSearch({ q: compareInput || undefined, limit: 8 })
        setCompareSuggestions(items)
      } catch {
        setCompareSuggestions([])
      }
    }, 220)
    return () => window.clearTimeout(timer)
  }, [compareInput, view])

  useEffect(() => {
    if (view !== 'compare') return
    if (selectedCompareItems.length >= MIN_COMPARE_ITEMS) {
      const timer = window.setTimeout(() => {
        void runQuickCompare(selectedCompareItems)
      }, 260)
      return () => window.clearTimeout(timer)
    }
    if (productId || canonicalGroupId) {
      const timer = window.setTimeout(() => {
        void runLegacyCompare()
      }, 260)
      return () => window.clearTimeout(timer)
    }
    setLegacyCompareResult(null)
    setQuickCompareRows([])
  }, [canonicalGroupId, mode, productId, quantity, selectedCompareItems, view])

  useEffect(() => {
    if (view !== 'history') return
    if (!fromAt || !toAt) {
      setHistoryItems([])
      return
    }
    const timer = window.setTimeout(() => {
      void runHistory()
    }, 260)
    return () => window.clearTimeout(timer)
  }, [canonicalGroupId, fromAt, productId, toAt, view])

  const quickCompareTitle = isEn ? 'Quick product compare' : 'เทียบสินค้าแบบไว'
  const quickCompareHint = isEn
    ? 'Type part of the product name, SKU, alias, or supplier. Suggestions appear automatically.'
    : 'พิมพ์ชื่อสินค้า รหัสสินค้า alias หรือชื่อร้านค้าได้เลย ระบบจะเด้งรายการให้เลือกอัตโนมัติ'
  const compareAddTitle = isEn ? '1. Find and add products' : '1. ค้นหาและเพิ่มสินค้าเข้าเทียบ'
  const compareAddHelper = isEn
    ? 'This box is for searching products to add into the compare list.'
    : 'กล่องนี้ใช้สำหรับค้นหาสินค้าที่จะเอาเข้าเทียบ พิมพ์ชื่อสินค้า รหัสสินค้า alias หรือชื่อร้านค้า แล้วกดจากรายการที่เด้งขึ้นมาได้เลย'
  const selectedTitle = isEn ? '2. Selected products' : '2. สินค้าที่เลือกไว้แล้ว'
  const selectedHelper = isEn
    ? 'These are the products already selected for comparison.'
    : 'กล่องนี้คือรายการสินค้าที่เลือกไว้แล้ว กดดูรายละเอียดหรือเอาออกได้'
  const summaryTitle = isEn ? '3. Compare summary' : '3. สรุปผลเทียบ'
  const summaryHelper = isEn
    ? 'This section tells you which product is cheaper and why.'
    : 'กล่องนี้ใช้สรุปว่าตัวไหนถูกกว่า และถ้ายังเทียบไม่ได้จะบอกเหตุผลที่พบบ่อย'
  const noPriceChecklist = isEn
    ? [
        'This item still has no active price record in the system.',
        'The quantity you entered may not match the configured price tier.',
        'The selected compare mode may not match the stored pricing data.',
      ]
    : [
        'สินค้านี้ยังไม่มีราคาที่ใช้งานอยู่ในระบบ',
        'จำนวนที่กรอกอาจไม่ตรงกับช่วงราคาที่ตั้งไว้',
        'โหมดที่เลือกอาจไม่ตรงกับข้อมูลราคาที่บันทึกไว้',
      ]

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{t('zones.search.title')}</h1>
          <p className="text-sm text-[color:var(--color-muted)]">{t('zones.search.subtitle')}</p>
        </div>
        <div className="flex gap-2 text-sm">
          <button className={viewButtonClass(view === 'quick')} onClick={() => patchSearch({ view: 'quick' })} type="button">
            {isEn ? 'Quick search' : 'ค้นหาอัตโนมัติ'}
          </button>
          <button className={viewButtonClass(view === 'compare')} onClick={() => patchSearch({ view: 'compare' })} type="button">
            {quickCompareTitle}
          </button>
          <button className={viewButtonClass(view === 'history')} onClick={() => patchSearch({ view: 'history' })} type="button">
            {isEn ? 'History' : 'ประวัติราคา'}
          </button>
        </div>
      </div>

      {view === 'quick' ? (
        <div className="surface-panel space-y-3 rounded p-4">
          <div className="grid gap-3">
            <FieldLabel
              label={isEn ? 'Keyword' : 'คำค้นหา'}
              helper={isEn ? 'Results appear automatically while you type.' : 'พิมพ์แล้วระบบจะค้นหาให้ทันที ไม่ต้องกดค้นหาทุกครั้ง'}
              example={t('zones.search.quickPlaceholder')}
              helpKey="search.quick"
            >
              <input
                className={inputClass()}
                value={query}
                onChange={(e) => patchSearch({ q: e.target.value })}
                placeholder={isEn ? 'Example: SKU-001, steel pipe, supplier A' : 'ตัวอย่าง: รหัสสินค้า 001, ท่อเหล็ก, ร้าน A'}
              />
            </FieldLabel>
          </div>
          <div className="text-xs text-[color:var(--color-muted)]">
            {quickBusy
              ? isEn
                ? 'Searching...'
                : 'กำลังค้นหา...'
              : isEn
                ? `Found ${searchItems.length} quick result(s)`
                : `พบผลลัพธ์แบบเร็ว ${searchItems.length} รายการ`}
          </div>
          <div className="space-y-2">
            {searchItems.map((item) => (
              <div key={item.product_id} className="surface-item rounded px-3 py-3 text-sm">
                <div className="font-medium">
                  {item.sku} - {item.name_th || item.name_en}
                </div>
                <div className="mt-1 text-[color:var(--color-muted)]">
                  {isEn ? 'Compare group' : 'กลุ่มเทียบ'}: {item.canonical_group_name || '-'}
                </div>
                <div className="mt-1 text-xs text-[color:var(--color-muted)]">
                  {isEn ? 'Suppliers' : 'ร้านค้าที่ผูกไว้'}: {item.supplier_text || '-'} |{' '}
                  {isEn ? 'Lowest current price' : 'ราคาต่ำสุดตอนนี้'}:{' '}
                  {item.cheapest_active_final_total_cost_thb != null ? `${item.cheapest_active_final_total_cost_thb.toFixed(2)} THB` : '-'}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    className="rounded border border-[color:var(--color-border)] px-2 py-1 text-[color:var(--color-fg)]"
                    to={`/products?productId=${item.product_id}&sku=${encodeURIComponent(item.sku)}`}
                  >
                    {isEn ? 'Product details' : 'ดูรายละเอียดสินค้า'}
                  </Link>
                  <button
                    className="rounded border border-[color:var(--color-border)] px-2 py-1 text-[color:var(--color-fg)]"
                    onClick={() => addCompareItem(item)}
                    type="button"
                  >
                    {isEn ? 'Add to quick compare' : 'เพิ่มไปเทียบสินค้า'}
                  </button>
                </div>
              </div>
            ))}
            {!quickBusy && searchItems.length === 0 ? (
              <div className="text-sm text-[color:var(--color-muted)]">
                {query
                  ? isEn
                    ? 'No result found. Try another keyword.'
                    : 'ยังไม่พบผลลัพธ์ ลองเปลี่ยนคำค้นหาได้เลย'
                  : isEn
                    ? 'Start typing and the system will suggest products automatically.'
                    : 'เริ่มพิมพ์คำค้นหาแล้วระบบจะแนะนำสินค้าให้ทันที'}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {view === 'compare' ? (
        <div className="space-y-6">
          {/* ── Section 1: ค้นหาและเพิ่มสินค้าเข้าเทียบ ── */}
          <div className="surface-panel rounded p-4 space-y-3">
            <div className="border-b border-[color:var(--color-border)] pb-3">
              <div className="text-base font-semibold">{compareAddTitle}</div>
              <div className="mt-1 text-sm text-[color:var(--color-muted)]">{compareAddHelper}</div>
            </div>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1.7fr)_minmax(180px,220px)_minmax(180px,220px)]">
              <FieldLabel label={quickCompareTitle} helper={quickCompareHint} helpKey="search.compare">
                <input
                  className={inputClass()}
                  value={compareInput}
                  onChange={(e) => setCompareInput(e.target.value)}
                  placeholder={isEn ? 'Example: steel pipe, SKU-001, supplier A' : 'ตัวอย่าง: ท่อเหล็ก, รหัสสินค้า 001, ร้าน A'}
                />
              </FieldLabel>
              <FieldLabel label={isEn ? 'Quantity to compare' : 'จำนวนที่ใช้เทียบ'} example={t('zones.search.quantityPlaceholder')}>
                <input
                  className={inputClass()}
                  value={quantity}
                  onChange={(e) => patchSearch({ quantity: e.target.value })}
                  placeholder={t('zones.search.quantityPlaceholder')}
                />
              </FieldLabel>
              <FieldLabel label={isEn ? 'Compare mode' : 'โหมดที่ใช้เทียบ'}>
                <select className={inputClass()} value={mode} onChange={(e) => patchSearch({ mode: e.target.value })}>
                  <option value="active">{isEn ? 'Active price now' : 'ราคาใช้งานอยู่ตอนนี้'}</option>
                  <option value="latest">{isEn ? 'Latest recorded price' : 'ราคาล่าสุดที่บันทึกไว้'}</option>
                </select>
              </FieldLabel>
            </div>

            <div className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-2 text-sm text-[color:var(--color-muted)]">
              {isEn
                ? `Selected ${selectedCompareItems.length}/${MAX_COMPARE_ITEMS} items. Pick at least ${MIN_COMPARE_ITEMS} items to compare automatically.`
                : `เลือกแล้ว ${selectedCompareItems.length}/${MAX_COMPARE_ITEMS} รายการ เลือกอย่างน้อย ${MIN_COMPARE_ITEMS} รายการเพื่อให้ระบบเทียบให้อัตโนมัติ`}
            </div>

            {compareSuggestions.length > 0 ? (
              <div className="space-y-1 rounded border border-[color:var(--color-primary)]/40 bg-[color:var(--color-primary)]/5 p-3">
                <div className="text-xs font-medium text-[color:var(--color-muted)] mb-2">
                  {isEn ? `Found ${compareSuggestions.length} product(s) — click to add` : `พบ ${compareSuggestions.length} สินค้า — กดเพื่อเพิ่มเข้ารายการเทียบ`}
                </div>
                {compareSuggestions.map((item) => (
                  <button
                    key={`${item.product_id}-${item.canonical_group_id || 'single'}`}
                    className="surface-item block w-full rounded px-3 py-2 text-left text-sm hover:ring-1 hover:ring-[color:var(--color-primary)]/50"
                    type="button"
                    onClick={() => addCompareItem(item)}
                  >
                    <div className="font-medium">
                      {item.sku} - {item.name_th || item.name_en}
                    </div>
                    <div className="mt-1 text-xs text-[color:var(--color-muted)]">
                      {item.canonical_group_name || (isEn ? 'No compare group' : 'ยังไม่มีกลุ่มเทียบ')} |{' '}
                      {item.cheapest_active_final_total_cost_thb != null
                        ? `${item.cheapest_active_final_total_cost_thb.toFixed(2)} THB`
                        : isEn
                          ? 'No active price'
                          : 'ยังไม่มีราคาที่ใช้อยู่'}
                    </div>
                  </button>
                ))}
              </div>
            ) : compareInput.trim() ? (
              <div className="text-sm text-[color:var(--color-muted)]">
                {isEn ? 'No products found. Try another keyword.' : 'ไม่พบสินค้า ลองเปลี่ยนคำค้นหาดู'}
              </div>
            ) : null}
          </div>

          {/* ── Section 2: สินค้าที่เลือกไว้แล้ว ── */}
          <div className="surface-panel rounded p-4 space-y-3">
            <div className="border-b border-[color:var(--color-border)] pb-3">
              <div className="text-base font-semibold">{selectedTitle}</div>
              <div className="mt-1 text-sm text-[color:var(--color-muted)]">{selectedHelper}</div>
            </div>

            {selectedCompareItems.length > 0 ? (
              <>
                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                  {selectedCompareItems.map((item) => (
                    <div key={item.compareKey} className="surface-item rounded px-3 py-3 text-sm">
                      <div className="font-medium">
                        {item.sku} - {item.name}
                      </div>
                      <div className="mt-1 text-xs text-[color:var(--color-muted)]">
                        {item.canonicalGroupName || (isEn ? 'Compare this product only' : 'เทียบเฉพาะสินค้านี้')}
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Link
                          className="rounded border border-[color:var(--color-border)] px-2 py-1 text-[color:var(--color-fg)]"
                          to={`/products?productId=${item.productId}&sku=${encodeURIComponent(item.sku)}`}
                        >
                          {isEn ? 'Details' : 'รายละเอียด'}
                        </Link>
                        <button
                          className="rounded border border-red-400/30 px-2 py-1 text-red-200 hover:bg-red-500/10"
                          onClick={() => removeCompareItem(item.compareKey)}
                          type="button"
                        >
                          {isEn ? 'Remove' : 'เอาออก'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-[color:var(--color-fg)] hover:bg-white/10"
                    onClick={() => {
                      setSelectedCompareItems([])
                      setQuickCompareRows([])
                      setCompareNotice('')
                    }}
                    type="button"
                  >
                    {isEn ? 'Clear selected items' : 'ล้างสินค้าที่เลือก'}
                  </button>
                </div>
              </>
            ) : (
              <div className="rounded border border-dashed border-[color:var(--color-border)] px-4 py-6 text-center text-sm text-[color:var(--color-muted)]">
                {isEn
                  ? 'No products selected yet. Search and click a product above to add it here.'
                  : 'ยังไม่ได้เลือกสินค้า ค้นหาสินค้าจากช่องด้านบนแล้วกดเพิ่มเข้ามาได้เลย'}
              </div>
            )}
          </div>

          {compareNotice ? (
            <div className="rounded border border-yellow-400/30 bg-yellow-500/5 px-4 py-3 text-sm text-[color:var(--color-muted)]">{compareNotice}</div>
          ) : null}

          {/* ── Section 3: สรุปผลเทียบ ── */}
          <div className="surface-panel rounded p-4 space-y-3">
            <div className="border-b border-[color:var(--color-border)] pb-3">
              <div className="text-base font-semibold">{summaryTitle}</div>
              <div className="mt-1 text-sm text-[color:var(--color-muted)]">{summaryHelper}</div>
            </div>

          {selectedCompareItems.length >= MIN_COMPARE_ITEMS ? (
            <div className="space-y-3">
              <div className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-3 text-sm">
                <div className="font-medium">{isEn ? 'Quick compare summary' : 'สรุปการเทียบสินค้าแบบไว'}</div>
                <div className="mt-1 text-[color:var(--color-muted)]">
                  {compareBusy
                    ? isEn
                      ? 'Comparing prices...'
                      : 'กำลังเทียบราคา...'
                    : quickCompareSummary.comparableCount > 0
                    ? isEn
                      ? `Cheapest item now: ${quickCompareSummary.cheapestName} (${quickCompareSummary.cheapestCost?.toFixed(2)} THB)`
                      : `ตอนนี้สินค้าที่ราคาดีสุดคือ ${quickCompareSummary.cheapestName} (${quickCompareSummary.cheapestCost?.toFixed(2)} บาท)`
                    : isEn
                      ? 'No active price record found for any selected product. Try switching the compare mode to "Latest recorded price" or adjusting the quantity.'
                      : 'ยังไม่พบราคาที่ใช้งานอยู่สำหรับสินค้าที่เลือก ลองเปลี่ยนโหมดเป็น "ราคาล่าสุดที่บันทึกไว้" หรือปรับจำนวนที่ใช้เทียบดู'}
                </div>
              </div>

              <div className="space-y-2">
                {quickCompareRows.map((row, index) => (
                  <div key={row.compareKey} className="surface-item rounded px-3 py-3 text-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">
                          {index + 1}. {row.sku} - {row.name}
                        </div>
                        <div className="mt-1 text-xs text-[color:var(--color-muted)]">
                          {row.canonicalGroupName || (isEn ? 'No compare group' : 'เทียบเฉพาะสินค้านี้')} |{' '}
                          {isEn ? 'Offer count' : 'จำนวนราคาที่พบ'}: {row.matchedRowCount}
                        </div>
                      </div>
                      <Link
                        className="rounded border border-[color:var(--color-border)] px-2 py-1 text-[color:var(--color-fg)]"
                        to={`/products?productId=${row.productId}&sku=${encodeURIComponent(row.sku)}`}
                      >
                        {isEn ? 'Details' : 'รายละเอียด'}
                      </Link>
                    </div>
                    {row.bestRow ? (
                      <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                        <div className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-2">
                          <div className="text-xs text-[color:var(--color-muted)]">{isEn ? 'Best supplier' : 'ร้านที่ดีที่สุดตอนนี้'}</div>
                          <div className="mt-1 font-medium">{row.bestRow.supplier_name}</div>
                        </div>
                        <div className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-2">
                          <div className="text-xs text-[color:var(--color-muted)]">{isEn ? 'Final total cost' : 'ต้นทุนรวมที่ใช้เทียบ'}</div>
                          <div className="mt-1 font-medium">{row.bestRow.final_total_cost_thb.toFixed(2)} THB</div>
                        </div>
                        <div className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-2">
                          <div className="text-xs text-[color:var(--color-muted)]">{isEn ? 'Base normalized price' : 'ราคาก่อนบวกต้นทุนอื่น'}</div>
                          <div className="mt-1 font-medium">{row.bestRow.normalized_amount_thb.toFixed(2)} THB</div>
                        </div>
                        <div className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-2">
                          <div className="text-xs text-[color:var(--color-muted)]">{isEn ? 'Delivery / area' : 'วิธีรับของ / พื้นที่'}</div>
                          <div className="mt-1 font-medium">
                            {row.bestRow.delivery_mode} / {row.bestRow.area_scope}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-3 rounded border border-dashed border-[color:var(--color-border)] px-3 py-3 text-sm text-[color:var(--color-muted)]">
                        <div className="font-medium text-[color:var(--color-fg)]">
                          {isEn ? 'No comparable price is available yet.' : 'ยังไม่พบราคาที่พร้อมเทียบสำหรับสินค้านี้'}
                        </div>
                        <div className="mt-2">
                          {isEn ? 'Please check these common reasons:' : 'ให้ลองเช็กสาเหตุที่พบบ่อยต่อไปนี้:'}
                        </div>
                        <ul className="mt-2 list-disc space-y-1 pl-5">
                          {noPriceChecklist.map((item) => (
                            <li key={`${row.compareKey}-${item}`}>{item}</li>
                          ))}
                        </ul>
                        <div className="mt-2 text-xs">
                          {isEn
                            ? 'Tip: try quantity 1, 10, or 50, or switch the compare mode.'
                            : 'คำแนะนำ: ลองเปลี่ยนจำนวนเป็น 1, 10 หรือ 50 และลองสลับโหมดที่ใช้เทียบ'}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : productId || canonicalGroupId ? (
            <div className="space-y-2">
              <div className="text-sm text-[color:var(--color-muted)]">
                {isEn
                  ? 'This compare view was opened from a link. The system still shows the current comparison below.'
                  : 'หน้านี้ถูกเปิดมาจากลิงก์เดิม ระบบจะแสดงผลเทียบปัจจุบันให้ก่อน แม้ยังไม่ได้เลือกหลายสินค้า'}
              </div>
              {(legacyCompareResult?.rows ?? []).map((row) => (
                <div key={row.price_record_id} className="surface-item rounded px-3 py-2 text-sm">
                  <div className="font-medium">
                    {row.supplier_name} - {t('zones.search.resultCost', { amount: row.final_total_cost_thb.toFixed(2) })}
                  </div>
                  <div className="text-[color:var(--color-muted)]">
                    {row.sku} - {row.delivery_mode} - {row.area_scope} - {row.selection_mode}
                  </div>
                </div>
              ))}
              {!compareBusy && (legacyCompareResult?.rows.length ?? 0) === 0 ? (
                <div className="text-sm text-[color:var(--color-muted)]">{t('zones.search.noCompareRows')}</div>
              ) : null}
            </div>
          ) : selectedCompareItems.length === 0 ? (
            <div className="rounded border border-dashed border-[color:var(--color-border)] px-4 py-6 text-center text-sm text-[color:var(--color-muted)]">
              {isEn
                ? 'Select at least 2 products above to begin comparing prices.'
                : 'เลือกสินค้าอย่างน้อย 2 รายการจากด้านบนเพื่อเริ่มเทียบราคา'}
            </div>
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
          <div className="text-xs text-[color:var(--color-muted)]">
            {historyBusy
              ? isEn
                ? 'Loading history...'
                : 'กำลังโหลดประวัติ...'
              : isEn
                ? 'Once both dates are filled in, history will load automatically.'
                : 'เมื่อกรอกวันเริ่มและวันสิ้นสุดครบ ระบบจะโหลดประวัติให้อัตโนมัติ'}
          </div>
          <div className="space-y-2">
            {historyItems.map((row) => (
              <div key={row.price_record_id} className="surface-item rounded px-3 py-2 text-sm">
                <div className="font-medium">{t('zones.search.resultCost', { amount: row.final_total_cost_thb.toFixed(2) })}</div>
                <div className="text-[color:var(--color-muted)]">
                  {t('zones.search.historyWindow', { from: row.effective_at || '-', to: row.expire_at || 'open' })}
                </div>
              </div>
            ))}
            {!historyBusy && historyItems.length === 0 ? (
              <div className="text-sm text-[color:var(--color-muted)]">{t('zones.search.noHistoryRows')}</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
