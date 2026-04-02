import { useEffect, useState, useRef } from 'react'
import { useAuthStore } from '../../store/authStore'
import { useConfigStore } from '../../store/configStore'
import { fetchActivity, fetchKpis, fetchStockSummary, type ActivityItem, type Kpis } from '../../services/dashboard'
import { listProducts, adjustStock, type StockAdjustData } from '../../services/products'
import type { Product } from '../../types/models'
import { getSocket } from '../../services/socketManager'

import { useTranslation } from 'react-i18next'
import { formatTHB } from '../../utils/money'
import { ProductDetailModal } from '../../components/products/ProductDetailModal'
import { productDisplayName } from '../../utils/product'

type CardColor = 'blue' | 'green' | 'yellow' | 'amber' | 'red' | 'orange' | 'sky' | 'default'
const CARD_COLOR_MAP: Record<CardColor, { border: string; bg: string; text: string }> = {
  blue:    { border: 'border-l-blue-500',   bg: 'bg-blue-500/10',   text: 'text-blue-300' },
  green:   { border: 'border-l-green-500',  bg: 'bg-green-500/10',  text: 'text-green-300' },
  yellow:  { border: 'border-l-yellow-400', bg: 'bg-yellow-400/10', text: 'text-yellow-300' },
  amber:   { border: 'border-l-amber-500',  bg: 'bg-amber-500/10',  text: 'text-amber-300' },
  red:     { border: 'border-l-red-500',    bg: 'bg-red-500/10',    text: 'text-red-300' },
  orange:  { border: 'border-l-orange-500', bg: 'bg-orange-500/10', text: 'text-orange-300' },
  sky:     { border: 'border-l-sky-500',    bg: 'bg-sky-500/10',    text: 'text-sky-300' },
  default: { border: 'border-l-transparent',bg: '',                 text: '' },
}

function Card(props: { title: string; value: string; loading: boolean; color?: CardColor }) {
  const c = CARD_COLOR_MAP[props.color ?? 'default']
  return (
    <div className={`card rounded border border-[color:var(--color-border)] border-l-4 ${c.border} ${c.bg} p-4 backdrop-blur`}>
      <div className="text-xs text-white/60">{props.title}</div>
      {props.loading ? (
        <div className="mt-2 h-7 w-28 rounded skeleton" />
      ) : (
        <div className={`mt-1 text-2xl font-bold ${c.text}`}>{props.value}</div>
      )}
    </div>
  )
}

// ─── Toast system ────────────────────────────────────────────────────────────
type ToastItem = { id: number; message: string; type: 'success' | 'error' | 'info' }

function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  function addToast(message: string, type: ToastItem['type'] = 'info') {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }
  return { toasts, addToast }
}

function ToastContainer({ toasts }: { toasts: ToastItem[] }) {
  if (toasts.length === 0) return null
  return (
    <div className="fixed bottom-6 inset-x-0 z-[9999] flex justify-center pointer-events-none px-4">
      <div className="flex flex-col items-center gap-2">
        {toasts.map(t => (
          <div key={t.id} className={`flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold shadow-2xl backdrop-blur ${
            t.type === 'success' ? 'bg-green-600/95 text-white' :
            t.type === 'error'   ? 'bg-red-600/95 text-white' :
                                   'bg-zinc-800/95 text-white border border-white/10'
          }`}>
            <span>{t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : 'ℹ'}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Status badge helper (vivid solid colours) ───────────────────────────────
function statusBadgeClass(status: string): string {
  switch (status) {
    case 'OUT':      return 'bg-red-600 text-white'
    case 'CRITICAL': return 'bg-orange-600 text-white'
    case 'LOW':      return 'bg-yellow-400 text-black'
    case 'FULL':     return 'bg-green-600 text-white'
    case 'NORMAL':   return 'bg-sky-600 text-white'
    case 'TEST':     return 'bg-purple-600 text-white'
    default:         return 'bg-zinc-600 text-white'
  }
}

type StockAlertSectionKey = 'LOW' | 'CRITICAL' | 'OUT'

const STOCK_ALERT_META: Array<{
  key: StockAlertSectionKey
  title: string
  description: string
  color: CardColor
  badgeClass: string
}> = [
  {
    key: 'LOW',
    title: 'สินค้าใกล้หมด',
    description: 'ยังพอขายได้ แต่ควรเฝ้าระวัง',
    color: 'yellow',
    badgeClass: 'bg-yellow-400/15 text-yellow-300 border border-yellow-400/30'
  },
  {
    key: 'CRITICAL',
    title: 'สินค้าควรเติม',
    description: 'ต่ำกว่าจุดปลอดภัย ควรเติมด่วน',
    color: 'amber',
    badgeClass: 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
  },
  {
    key: 'OUT',
    title: 'สินค้าหมด',
    description: 'ไม่มีของพร้อมขายในคลัง',
    color: 'red',
    badgeClass: 'bg-red-500/15 text-red-300 border border-red-500/30'
  }
]

function formatQty(value: string | number) {
  const num = Number(value || 0)
  return num.toLocaleString('th-TH', { maximumFractionDigits: 2 })
}

function formatUpdatedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('th-TH', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function getRestockQty(product: Product) {
  return Math.max(0, Number(product.max_stock) - Number(product.stock_qty))
}

function matchesWatchlistSearch(product: Product, query: string) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return [
    product.sku,
    productDisplayName(product),
    product?.name?.en || '',
    product.category,
    product.type,
    product.barcode,
    product.supplier,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(normalized))
}

function StockDashboard() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [q, setQ] = useState('')
  const [scanning, setScanning] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [searchResults, setSearchResults] = useState<Product[]>([])
  const [busy, setBusy] = useState(false)
  const [summaryBusy, setSummaryBusy] = useState(true)
  const [summaryReady, setSummaryReady] = useState(false)
  const [alertsBusy, setAlertsBusy] = useState(true)
  const [scannedToday, setScannedToday] = useState(0)
  const [summary, setSummary] = useState({
    totalProducts: 0,
    fullStock: 0,
    normalStock: 0,
    lowStock: 0,
    criticalStock: 0,
    outOfStock: 0
  })
  const [alertSections, setAlertSections] = useState<Record<StockAlertSectionKey, Product[]>>({
    LOW: [],
    CRITICAL: [],
    OUT: [],
  })
  const [watchlistQuery, setWatchlistQuery] = useState('')
  const [watchlistPage, setWatchlistPage] = useState<Record<StockAlertSectionKey, number>>({
    LOW: 1,
    CRITICAL: 1,
    OUT: 1,
  })
  const { toasts, addToast } = useToast()
  const videoRef = useRef<HTMLVideoElement>(null)
  const codeReader = useRef<any>(null)
  const realtimeTimerRef = useRef<number | null>(null)

  async function reloadSummary() {
    setSummaryBusy(true)
    try {
      const s = await fetchStockSummary()
      setSummary({
        totalProducts: Number(s.total_products ?? 0),
        fullStock: Number(s.full ?? 0),
        normalStock: Number((s as any).normal ?? 0),
        lowStock: Number(s.low ?? 0),
        criticalStock: Number(s.critical ?? 0),
        outOfStock: Number(s.out ?? 0),
      })
      setSummaryReady(true)
    } finally {
      setSummaryBusy(false)
    }
  }

  async function reloadAlerts() {
    setAlertsBusy(true)
    try {
      const [low, critical, out] = await Promise.all([
        listProducts({ status: 'LOW', limit: 100 }),
        listProducts({ status: 'CRITICAL', limit: 100 }),
        listProducts({ status: 'OUT', limit: 100 }),
      ])
      setAlertSections({
        LOW: low.items,
        CRITICAL: critical.items,
        OUT: out.items,
      })
    } finally {
      setAlertsBusy(false)
    }
  }

  async function reloadStockOverview() {
    await Promise.all([reloadSummary(), reloadAlerts()])
  }

  useEffect(() => {
    const delay = setTimeout(async () => {
      if (q.length > 0) {
        setBusy(true)
        try {
          const res = await listProducts({ q, limit: 5 })
          setSearchResults(res.items)
          // If exact match barcode/sku, auto open
          if (res.items.length === 1 && (res.items[0].sku === q || res.items[0].barcode === q)) {
            setSelectedProduct(res.items[0])
            setScannedToday(c => c + 1)
            setQ('')
          }
        } finally {
          setBusy(false)
        }
      } else {
        setSearchResults([])
      }
    }, 300)
    return () => clearTimeout(delay)
  }, [q])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!scanning || !videoRef.current) return
      if (!codeReader.current) {
        try {
          const mod: any = await import('@zxing/browser')
          if (cancelled) return
          codeReader.current = new mod.BrowserMultiFormatReader()
        } catch {
          setScanning(false)
          return
        }
      }
      codeReader.current.decodeFromVideoDevice(undefined, videoRef.current, (result: any) => {
        if (result) {
          setQ(result.getText())
          setScanning(false)
        }
      })
    })()
    return () => {
      cancelled = true
      // @zxing/browser doesn't have reset on BrowserMultiFormatReader, it manages its own lifecycle or we can stop the stream if we kept the stream reference. 
      // For this simple implementation, unmounting the component handles it.
    }
  }, [scanning])

  useEffect(() => {
    reloadStockOverview()
    const timer = window.setInterval(reloadStockOverview, 30_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const s = getSocket(user?.id)
    if (!s) return
    const onStockUpdated = (evt: any) => {
      const sku = String(evt?.sku || '')
      if (!sku) return
      setSelectedProduct((prev) => {
        if (!prev || prev.sku !== sku) return prev
        return {
          ...prev,
          stock_qty: String(evt?.stock_qty ?? prev.stock_qty),
          status: (evt?.status as any) ?? prev.status,
          updated_at: String(evt?.updated_at ?? prev.updated_at)
        }
      })
      setSearchResults((prev) =>
        prev.map((p) =>
          p.sku === sku
            ? {
                ...p,
                stock_qty: String(evt?.stock_qty ?? p.stock_qty),
                status: (evt?.status as any) ?? p.status,
                updated_at: String(evt?.updated_at ?? p.updated_at)
              }
            : p
        )
      )
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = window.setTimeout(() => {
        reloadStockOverview()
      }, 300)
    }
    s.on('stock_updated', onStockUpdated)
    return () => {
      s.off('stock_updated', onStockUpdated)
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = null
    }
  }, [user?.id])

  return (
    <div className="space-y-4">
      <ToastContainer toasts={toasts} />
      {selectedProduct && (
        <ProductDetailModal 
          product={selectedProduct} 
          onClose={() => setSelectedProduct(null)} 
          onUpdate={(p) => {
            setSelectedProduct(p)
            reloadStockOverview()
          }}
          onToast={addToast}
        />
      )}

      {/* ── Search card ── */}
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-6 backdrop-blur">
        <h2 className="text-lg font-semibold mb-4">{t('dashboard.stock.title')}</h2>
        
        {scanning ? (
          <div className="mb-4 aspect-video w-full max-w-md overflow-hidden rounded border border-[color:var(--color-primary)] bg-black mx-auto relative">
            <video ref={videoRef} className="h-full w-full object-cover" />
            <button 
              className="absolute top-2 right-2 rounded bg-black/50 px-3 py-1 text-sm text-white hover:bg-black/80"
              onClick={() => setScanning(false)}
            >
              {t('app.closeCamera')}
            </button>
            <div className="absolute inset-0 border-2 border-[color:var(--color-primary)] m-8 opacity-50 rounded"></div>
          </div>
        ) : null}

        <div className="flex gap-2">
          <input 
            type="text" 
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('app.searchPlaceholder')}
            className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-4 py-3 text-sm outline-none focus:border-[color:var(--color-primary)] text-lg"
            autoFocus
          />
          <button 
            className="rounded bg-[color:var(--color-primary)] px-4 py-2 font-semibold text-black hover:opacity-90 flex items-center gap-2"
            onClick={() => setScanning(true)}
          >
            {t('app.openCamera')}
          </button>
        </div>
        {busy && q.length > 0 && (
          <div className="mt-2 text-xs text-white/40">กำลังค้นหา...</div>
        )}
      </div>

      {/* ── Search results panel (separate card, scrollable, no overlap) ── */}
      {q.length > 0 && searchResults.length > 0 && (
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/95 backdrop-blur overflow-hidden">
          <div className="px-4 py-2 border-b border-[color:var(--color-border)] flex items-center justify-between">
            <span className="text-xs font-medium text-white/50">ผลการค้นหา {searchResults.length} รายการ</span>
            <button onClick={() => { setQ(''); setSearchResults([]) }} className="text-xs text-white/40 hover:text-white/70">✕ ปิด</button>
          </div>
          <div className="max-h-72 overflow-y-auto divide-y divide-[color:var(--color-border)]">
            {searchResults.map(p => (
              <button
                key={p.id}
                type="button"
                className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-white/10 active:bg-white/15"
                onClick={() => {
                  setSelectedProduct(p)
                  setScannedToday(c => c + 1)
                  setQ('')
                  setSearchResults([])
                }}
              >
                <div className="h-12 w-12 shrink-0 rounded bg-black/30 flex items-center justify-center text-xl overflow-hidden border border-[color:var(--color-border)]">
                  {p.image_url ? <img src={p.image_url} alt="" className="h-full w-full object-cover" /> : '📦'}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold truncate">{productDisplayName(p)}</div>
                  <div className="text-xs text-white/50 font-mono">{p.sku}</div>
                </div>
                <div className="text-right shrink-0 flex flex-col items-end gap-1">
                  <div className="text-xl font-bold text-[color:var(--color-primary)]">{p.stock_qty} <span className="text-xs font-normal text-white/50">{p.unit}</span></div>
                  <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${statusBadgeClass(p.status)}`}>{t(`stockStatus.${p.status}`)}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Summary cards ── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between px-1">
          <div className="text-xs font-medium text-white/40 uppercase tracking-wider">ภาพรวมสต็อก</div>
          {summaryReady && (
            <div className="flex items-center gap-1.5 text-xs text-green-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
              </span>
              อัพเดตอัตโนมัติ
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <Card title={t('dashboard.stock.totalProducts')} value={String(summary.totalProducts)} loading={summaryBusy && !summaryReady} color="blue" />
          <Card title="เต็ม" value={String(summary.fullStock)} loading={!summaryReady} color="green" />
          <Card title="ปกติ" value={String(summary.normalStock)} loading={!summaryReady} color="sky" />
          <Card title={t('dashboard.stock.lowStock')} value={String(summary.lowStock)} loading={!summaryReady} color="yellow" />
          <Card title="ควรเติม" value={String(summary.criticalStock)} loading={!summaryReady} color="amber" />
          <Card title={t('dashboard.stock.outOfStock')} value={String(summary.outOfStock)} loading={!summaryReady} color="red" />
          <Card title={t('dashboard.stock.scannedToday')} value={String(scannedToday)} loading={false} color="orange" />
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-5 backdrop-blur">
        <div className="mb-4 flex flex-col gap-1 md:flex-row md:items-end md:justify-between">
          <div>
            <h3 className="text-base font-semibold">โซนเฝ้าระวังสต็อก</h3>
            <p className="text-sm text-white/50">กดที่สินค้าเพื่อเปิดดูรายละเอียดและเช็กจำนวนที่ต้องเติม</p>
          </div>
          <div className="text-xs text-white/40">อัปเดตตามสถานะล่าสุดของคลังสินค้า</div>
        </div>

        <div className="mb-4">
          <input
            className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] md:max-w-md"
            value={watchlistQuery}
            onChange={(e) => {
              setWatchlistQuery(e.target.value)
              setWatchlistPage({ LOW: 1, CRITICAL: 1, OUT: 1 })
            }}
            placeholder="ค้นหาในโซนเฝ้าระวัง"
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          {STOCK_ALERT_META.map((section) => {
            const items = alertSections[section.key]
            const filteredItems = items.filter((product) => matchesWatchlistSearch(product, watchlistQuery))
            const totalPages = Math.max(1, Math.ceil(filteredItems.length / 5))
            const currentPage = Math.min(watchlistPage[section.key], totalPages)
            const pageItems = filteredItems.slice((currentPage - 1) * 5, currentPage * 5)
            return (
              <div key={section.key} className="rounded-xl border border-[color:var(--color-border)] bg-black/20">
                <div className="flex items-start justify-between gap-3 border-b border-[color:var(--color-border)] px-4 py-4">
                  <div>
                    <div className="font-semibold">{section.title}</div>
                    <div className="text-xs text-white/50">{section.description}</div>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${section.badgeClass}`}>
                    {filteredItems.length} ??????
                  </span>
                </div>

                <div className="space-y-3 p-4">
                  {alertsBusy ? (
                    Array.from({ length: 3 }).map((_, index) => (
                      <div key={index} className="rounded-lg border border-[color:var(--color-border)] bg-white/5 p-4">
                        <div className="h-4 w-32 rounded skeleton" />
                        <div className="mt-3 h-3 w-24 rounded skeleton" />
                        <div className="mt-4 h-16 rounded skeleton" />
                      </div>
                    ))
                  ) : filteredItems.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-[color:var(--color-border)] bg-white/5 px-4 py-8 text-center text-sm text-white/45">
                      ?????????????????????????
                    </div>
                  ) : (
                    pageItems.map((product) => {
                      const restockQty = getRestockQty(product)
                      return (
                        <button
                          key={product.id}
                          type="button"
                          onClick={() => setSelectedProduct(product)}
                          className="block w-full rounded-lg border border-[color:var(--color-border)] bg-white/5 p-4 text-left transition hover:border-white/20 hover:bg-white/10"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate font-semibold">{productDisplayName(product)}</div>
                              <div className="mt-1 text-xs font-mono text-white/45">{product.sku}</div>
                            </div>
                            <span className={`shrink-0 rounded px-2 py-1 text-[11px] font-semibold ${statusBadgeClass(product.status)}`}>
                              {t(`stockStatus.${product.status}`)}
                            </span>
                          </div>

                          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                            <div className="rounded border border-white/5 bg-black/20 p-3">
                              <div className="text-xs text-white/50">คงเหลือ</div>
                              <div className="mt-1 text-lg font-bold text-[color:var(--color-primary)]">
                                {formatQty(product.stock_qty)} <span className="text-xs font-normal text-white/50">{product.unit}</span>
                              </div>
                            </div>
                            <div className="rounded border border-white/5 bg-black/20 p-3">
                              <div className="text-xs text-white/50">ต้องเติมเพิ่ม</div>
                              <div className="mt-1 text-lg font-bold text-red-300">
                                {formatQty(restockQty)} <span className="text-xs font-normal text-white/50">{product.unit}</span>
                              </div>
                            </div>
                          </div>

                          <div className="mt-3 grid gap-2 text-xs text-white/60 md:grid-cols-3">
                            <div>ขั้นต่ำ: <span className="text-white">{formatQty(product.min_stock)} {product.unit}</span></div>
                            <div>ควรมี: <span className="text-white">{formatQty(product.max_stock)} {product.unit}</span></div>
                            <div>อัปเดตล่าสุด: <span className="text-white">{formatUpdatedAt(product.updated_at)}</span></div>
                          </div>
                        </button>
                      )
                    })
                  )}
                  {!alertsBusy && filteredItems.length > 5 ? (
                    <div className="flex items-center justify-between border-t border-[color:var(--color-border)] pt-3 text-xs text-white/60">
                      <div>Page {currentPage} / {totalPages}</div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="rounded border border-[color:var(--color-border)] px-2 py-1 hover:bg-white/10 disabled:opacity-40"
                          disabled={currentPage <= 1}
                          onClick={() => setWatchlistPage((prev) => ({ ...prev, [section.key]: Math.max(1, prev[section.key] - 1) }))}
                        >
                          Previous
                        </button>
                        <button
                          type="button"
                          className="rounded border border-[color:var(--color-border)] px-2 py-1 hover:bg-white/10 disabled:opacity-40"
                          disabled={currentPage >= totalPages}
                          onClick={() => setWatchlistPage((prev) => ({ ...prev, [section.key]: Math.min(totalPages, prev[section.key] + 1) }))}
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function AdminDashboard() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [busy, setBusy] = useState(true)
  const realtimeTimerRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const k = await fetchKpis()
        if (!cancelled) setKpis(k)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    run()
    const timer = window.setInterval(run, 10_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const s = getSocket(user?.id)
    if (!s) return
    const onStockUpdated = () => {
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = window.setTimeout(async () => {
        try {
          const k = await fetchKpis()
          if (!cancelled) setKpis(k)
        } catch {}
      }, 300)
    }
    s.on('stock_updated', onStockUpdated)
    return () => {
      cancelled = true
      s.off('stock_updated', onStockUpdated)
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = null
    }
  }, [user?.id])

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card title={t('dashboard.admin.pendingApproval')} value={String(kpis?.total_products ?? 0)} loading={busy && !kpis} />
        <Card title={t('dashboard.admin.todayMovement')} value={formatTHB(kpis?.stock_value ?? 0)} loading={busy && !kpis} />
        <Card title={t('dashboard.admin.needRestock')} value={formatTHB(kpis?.daily_revenue ?? 0)} loading={busy && !kpis} />
      </div>
    </div>
  )
}

function AccountantDashboard() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [busy, setBusy] = useState(true)
  const realtimeTimerRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const k = await fetchKpis()
        if (!cancelled) setKpis(k)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    run()
    const timer = window.setInterval(run, 10_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const s = getSocket(user?.id)
    if (!s) return
    const onStockUpdated = () => {
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = window.setTimeout(async () => {
        try {
          const k = await fetchKpis()
          if (!cancelled) setKpis(k)
        } catch {}
      }, 300)
    }
    s.on('stock_updated', onStockUpdated)
    return () => {
      cancelled = true
      s.off('stock_updated', onStockUpdated)
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = null
    }
  }, [user?.id])

  const revenue = Number(kpis?.daily_revenue ?? 0)
  const expense = Number(kpis?.daily_expense ?? 0)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <Card title={t('dashboard.accountant.todayRevenue')} value={formatTHB(revenue)} loading={busy && !kpis} color="green" />
        <Card title={t('dashboard.accountant.todayExpense')} value={formatTHB(expense)} loading={busy && !kpis} color="red" />
        <Card title={t('dashboard.accountant.stockValue')} value={formatTHB(kpis?.stock_value ?? 0)} loading={busy && !kpis} color="amber" />
        <Card title={t('dashboard.owner.usersOnline')} value={String(kpis?.active_users_online ?? 0)} loading={busy && !kpis} color="blue" />
      </div>
    </div>
  )
}

export function DashboardPage() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const role = user?.role

  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [busy, setBusy] = useState(true)
  const realtimeTimerRef = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const [k, a] = await Promise.all([fetchKpis(), fetchActivity()])
        if (cancelled) return
        setKpis(k)
        setActivity(a.items)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    run()
    const t = window.setInterval(run, 10_000)
    return () => {
      cancelled = true
      window.clearInterval(t)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const s = getSocket(user?.id)
    if (!s) return
    const onStockUpdated = () => {
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = window.setTimeout(async () => {
        try {
          const [k, a] = await Promise.all([fetchKpis(), fetchActivity()])
          if (cancelled) return
          setKpis(k)
          setActivity(a.items)
        } catch {}
      }, 300)
    }
    s.on('stock_updated', onStockUpdated)
    return () => {
      cancelled = true
      s.off('stock_updated', onStockUpdated)
      if (realtimeTimerRef.current) window.clearTimeout(realtimeTimerRef.current)
      realtimeTimerRef.current = null
    }
  }, [user?.id])

  if (role === 'STOCK') return <StockDashboard />
  if (role === 'ADMIN') return <AdminDashboard />
  if (role === 'ACCOUNTANT') return <AccountantDashboard />

  // OWNER and DEV see the full executive dashboard
  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">สำหรับเจ้าของ</div>
        <div className="mt-1 text-xs text-white/60">ข้อมูลภาพรวมที่ Sync จากสินค้าและธุรกรรมล่าสุด</div>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        <Card title={t('dashboard.owner.totalProducts')} value={String(kpis?.total_products ?? 0)} loading={busy && !kpis} />
        <Card title={t('dashboard.owner.stockValue')} value={formatTHB(kpis?.stock_value ?? 0)} loading={busy && !kpis} />
        <Card title={t('dashboard.owner.dailyRevenue')} value={formatTHB(kpis?.daily_revenue ?? 0)} loading={busy && !kpis} />
        <Card title={t('dashboard.owner.usersOnline')} value={String(kpis?.active_users_online ?? 0)} loading={busy && !kpis} />
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 backdrop-blur">
        <div className="border-b border-[color:var(--color-border)] px-4 py-3 text-sm font-semibold">
          {t('dashboard.owner.liveActivity')}
        </div>
        <div className="divide-y divide-[color:var(--color-border)]">
          {busy && activity.length === 0 ? (
            <div className="px-4 py-5">
              <div className="h-4 w-full max-w-3xl rounded skeleton" />
              <div className="mt-3 h-4 w-full max-w-2xl rounded skeleton" />
              <div className="mt-3 h-4 w-full max-w-xl rounded skeleton" />
            </div>
          ) : activity.length === 0 ? (
            <div className="px-4 py-8 text-sm text-white/60">{t('app.noActivity')}</div>
          ) : (
            activity.map((x) => (
              <div key={x.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm">
                    <span className="text-white/80">{x.actor_username ?? 'SYSTEM'}</span>
                    <span className="text-white/40"> • </span>
                    <span className="text-white/70">{x.action}</span>
                    <span className="text-white/40"> • </span>
                    <span className="text-white/70">{x.message}</span>
                  </div>
                  <div className="text-xs text-white/50">{new Date(x.created_at).toLocaleString()}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

