import { useEffect, useState } from 'react'
import Papa from 'papaparse'

import { api } from '../../services/api'
import { getDevSheetsConfig, type DevSheetsConfig } from '../../services/devSheets'
import { listProducts } from '../../services/products'
import { fetchKpis, fetchStockSummary, fetchTransactions, type Kpis, type StockSummary, type TransactionItem } from '../../services/dashboard'

type ReportPeriod = 'day' | 'week' | 'month' | 'year'

type HealthInfo = {
  status: string
  started_at: string
  uptime_seconds: number
}

const GOOGLE_OAUTH_PENDING_KEY = 'google_oauth_pending_until'

function hasPendingGoogleOauth() {
  const raw = window.localStorage.getItem(GOOGLE_OAUTH_PENDING_KEY)
  const until = Number(raw || '0')
  if (!until || Number.isNaN(until)) return false
  if (until <= Date.now()) {
    window.localStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY)
    return false
  }
  return true
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function formatDurationFromSeconds(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds || 0))
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days} วัน ${hours} ชม.`
  if (hours > 0) return `${hours} ชม. ${minutes} นาที`
  return `${minutes} นาที`
}

function formatDateTime(value?: string) {
  if (!value) return '-'
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

function getPeriodRange(period: ReportPeriod) {
  const now = new Date()
  const end = new Date(now)
  const start = new Date(now)
  if (period === 'day') {
    start.setHours(0, 0, 0, 0)
  } else if (period === 'week') {
    const day = start.getDay()
    const diff = day === 0 ? 6 : day - 1
    start.setDate(start.getDate() - diff)
    start.setHours(0, 0, 0, 0)
  } else if (period === 'month') {
    start.setDate(1)
    start.setHours(0, 0, 0, 0)
  } else {
    start.setMonth(0, 1)
    start.setHours(0, 0, 0, 0)
  }
  return {
    start,
    end,
    label:
      period === 'day'
        ? 'รายวัน'
        : period === 'week'
          ? 'รายสัปดาห์'
          : period === 'month'
            ? 'รายเดือน'
            : 'รายปี'
  }
}

async function fetchAllTransactions(params: { date_from?: string; date_to?: string } = {}) {
  const items: TransactionItem[] = []
  let offset = 0
  let total = 0
  do {
    const res = await fetchTransactions({ ...params, limit: 500, offset })
    items.push(...res.items)
    total = res.total
    offset += res.items.length
    if (res.items.length === 0) break
  } while (items.length < total)
  return items
}

async function fetchAllProducts() {
  const items: Awaited<ReturnType<typeof listProducts>>['items'] = []
  let offset = 0
  let total = 0
  do {
    const res = await listProducts({ limit: 200, offset })
    items.push(...res.items)
    total = res.total
    offset += res.items.length
    if (res.items.length === 0) break
  } while (items.length < total)
  return items
}

function toIsoLocal(date: Date) {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19)
}

function StatCard(props: { title: string; value: string; tone?: string }) {
  return (
    <div className={`rounded border border-[color:var(--color-border)] p-4 ${props.tone || 'bg-white/5'}`}>
      <div className="text-xs text-white/55">{props.title}</div>
      <div className="mt-1 text-2xl font-bold">{props.value}</div>
    </div>
  )
}

export function ReportsPage() {
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [kpis, setKpis] = useState<Kpis | null>(null)
  const [stockSummary, setStockSummary] = useState<StockSummary | null>(null)
  const [sheetsCfg, setSheetsCfg] = useState<DevSheetsConfig | null>(null)
  const [sheetsLoading, setSheetsLoading] = useState(true)
  const [googleSheetsPending, setGoogleSheetsPending] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [healthRes, kpisRes, stockRes] = await Promise.all([
          api.get<HealthInfo>('/health').then((res) => res.data),
          fetchKpis(),
          fetchStockSummary()
        ])
        if (cancelled) return
        setHealth(healthRes)
        setKpis(kpisRes)
        setStockSummary(stockRes)
        const pending = hasPendingGoogleOauth()
        setGoogleSheetsPending(pending)
        setSheetsLoading(true)
        try {
          let cfg = await getDevSheetsConfig()
          if (cancelled) return
          setSheetsCfg(cfg)
          if (pending && !cfg.usable) {
            const startedAt = Date.now()
            while (!cancelled && Date.now() - startedAt < 15_000 && !cfg.usable) {
              await new Promise((resolve) => window.setTimeout(resolve, 1200))
              cfg = await getDevSheetsConfig()
              if (cancelled) return
              setSheetsCfg(cfg)
              if (cfg.usable || cfg.enabled) break
            }
          }
        } catch {
        } finally {
          if (pending) window.localStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY)
          if (!cancelled) {
            setGoogleSheetsPending(false)
            setSheetsLoading(false)
          }
        }
      } catch {}
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const uptimeText = health ? formatDurationFromSeconds(health.uptime_seconds) : 'กำลังโหลด...'

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-xs text-white/50">ระบบ Stock ทำงานมาแล้ว {uptimeText}</div>
        <div className="mt-1 text-sm font-semibold">สรุป</div>
        <div className="mt-1 text-xs text-white/60">โหลดสรุปรายวัน รายสัปดาห์ รายเดือน หรือรายปี และดึงข้อมูลจริงไปใช้ต่อได้ทันที</div>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
        <StatCard title="สินค้าทั้งหมด" value={String(kpis?.total_products ?? 0)} tone="bg-blue-500/10" />
        <StatCard title="เต็ม" value={String(stockSummary?.full ?? 0)} tone="bg-green-500/10" />
        <StatCard title="ปกติ" value={String(stockSummary?.normal ?? 0)} tone="bg-sky-500/10" />
        <StatCard title="ใกล้หมด" value={String(stockSummary?.low ?? 0)} tone="bg-yellow-500/10" />
        <StatCard title="ควรเติม" value={String(stockSummary?.critical ?? 0)} tone="bg-amber-500/10" />
        <StatCard title="หมด" value={String(stockSummary?.out ?? 0)} tone="bg-red-500/10" />
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">โหลดสรุปตามช่วงเวลา</div>
        <div className="mt-1 text-xs text-white/60">ไฟล์จะมีทั้งสรุปภาพรวมและรายการธุรกรรมในช่วงเวลาที่เลือก</div>
        <div className="mt-4 flex flex-wrap gap-3">
          {([
            ['day', 'โหลดสรุปรายวัน'],
            ['week', 'โหลดสรุปรายสัปดาห์'],
            ['month', 'โหลดสรุปรายเดือน'],
            ['year', 'โหลดสรุปรายปี'],
          ] as Array<[ReportPeriod, string]>).map(([period, label]) => (
            <button
              key={period}
              disabled={busyKey !== null}
              className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
              onClick={async () => {
                setBusyKey(`summary-${period}`)
                try {
                  const { start, end, label: periodLabel } = getPeriodRange(period)
                  const [transactions, healthRes, kpisRes, stockRes] = await Promise.all([
                    fetchAllTransactions({
                      date_from: toIsoLocal(start),
                      date_to: toIsoLocal(end)
                    }),
                    api.get<HealthInfo>('/health').then((res) => res.data),
                    fetchKpis(),
                    fetchStockSummary()
                  ])

                  const stockIn = transactions.filter((x) => x.type === 'STOCK_IN')
                  const stockOut = transactions.filter((x) => x.type === 'STOCK_OUT')
                  const adjust = transactions.filter((x) => x.type === 'ADJUST')
                  const inQty = stockIn.reduce((sum, item) => sum + Number(item.qty || 0), 0)
                  const outQty = stockOut.reduce((sum, item) => sum + Number(item.qty || 0), 0)
                  const adjustQty = adjust.reduce((sum, item) => sum + Number(item.qty || 0), 0)

                  const rows = [
                    ['หัวข้อ', 'ค่า'],
                    ['ประเภทสรุป', periodLabel],
                    ['สร้างเมื่อ', formatDateTime(new Date().toISOString())],
                    ['ช่วงเวลาเริ่ม', formatDateTime(start.toISOString())],
                    ['ช่วงเวลาสิ้นสุด', formatDateTime(end.toISOString())],
                    ['ระบบ Stock ทำงานมาแล้ว', formatDurationFromSeconds(healthRes.uptime_seconds)],
                    ['สินค้าทั้งหมด', String(kpisRes.total_products)],
                    ['สถานะเต็ม', String(stockRes.full)],
                    ['สถานะปกติ', String(stockRes.normal)],
                    ['สถานะใกล้หมด', String(stockRes.low)],
                    ['สถานะควรเติม', String(stockRes.critical)],
                    ['สถานะหมด', String(stockRes.out)],
                    ['จำนวนธุรกรรมในช่วง', String(transactions.length)],
                    ['รายการรับเข้า', String(stockIn.length)],
                    ['รายการจ่ายออก', String(stockOut.length)],
                    ['รายการปรับยอด', String(adjust.length)],
                    ['รวมจำนวนรับเข้า', String(inQty)],
                    ['รวมจำนวนจ่ายออก', String(outQty)],
                    ['รวมจำนวนปรับยอด', String(adjustQty)],
                    [],
                    ['created_at', 'type', 'sku', 'product_name', 'qty', 'unit', 'note', 'actor_username'],
                    ...transactions.map((item) => [
                      formatDateTime(item.created_at),
                      item.type,
                      item.sku,
                      item.product_name,
                      item.qty,
                      item.unit,
                      item.note,
                      item.actor_username ?? ''
                    ])
                  ]
                  downloadText(`summary_${period}_${new Date().toISOString().slice(0, 10)}.csv`, Papa.unparse(rows))
                } finally {
                  setBusyKey(null)
                }
              }}
            >
              {busyKey === `summary-${period}` ? 'กำลังเตรียมไฟล์...' : label}
            </button>
          ))}
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">โหลดผ่าน Google Sheets</div>
        <div className="mt-1 text-xs text-white/60">เปิดดูแบบแยกหมวดได้ทั้ง Stock, บัญชี และ Log โดยข้อมูลจะจัดแท็บสีให้อ่านง่าย</div>
        {!sheetsCfg?.usable ? (
          <div className="mt-4 relative overflow-hidden rounded border border-[color:var(--color-border)] bg-black/20 p-5">
            <div className="absolute inset-0 bg-black/55 backdrop-blur-md" />
            <div className="relative text-center">
              {sheetsLoading || googleSheetsPending ? (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/85 px-4 text-center">
                  <div className="mb-4 h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-[color:var(--color-primary)]" />
                  <div className="text-base font-semibold text-sky-100">กำลังโหลดข้อมูล Google Sheets</div>
                  <div className="mt-2 text-sm text-sky-50/85">เชื่อม Google แล้ว ระบบกำลังดึงสถานะล่าสุดและเตรียมข้อมูลสำหรับหน้า Report กรุณารอสักครู่</div>
                </div>
              ) : null}
              <div className="text-base font-semibold">โซน Google Sheets ยังใช้งานไม่ได้</div>
              <div className="mt-2 text-sm text-white/65">ไปหน้า Config เพื่อเชื่อม Google และให้ระบบสร้าง/เชื่อม Sheets อัตโนมัติก่อนใช้งานโซนนี้</div>
              <div className="mt-1 text-xs text-white/45">สถานะ: {sheetsCfg?.error || 'not_configured'}</div>
              <button
                className="mt-4 rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                type="button"
                onClick={() => (window.location.href = '/settings#google-setup')}
              >
                ไปเชื่อม Google ใน Config
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded border border-green-500/30 bg-green-500/10 p-3">
            <div className="text-sm font-semibold text-green-100">Stock Sheets</div>
            <div className="mt-1 text-xs text-green-100/80">ข้อมูลสินค้า สถานะสต็อก และรายการใกล้หมด</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="rounded border border-green-400/30 px-3 py-2 text-xs text-green-50 hover:bg-green-500/10 disabled:opacity-50" type="button" disabled={!sheetsCfg?.stock_tab_url} onClick={() => window.open(sheetsCfg?.stock_tab_url, '_blank', 'noopener,noreferrer')}>
                เปิดแท็บ Stock
              </button>
              <button className="rounded border border-green-400/30 px-3 py-2 text-xs text-green-50 hover:bg-green-500/10 disabled:opacity-50" type="button" disabled={!sheetsCfg?.download_xlsx_url} onClick={() => window.open(sheetsCfg?.download_xlsx_url, '_blank', 'noopener,noreferrer')}>
                โหลดทั้งชีต .xlsx
              </button>
            </div>
          </div>
          <div className="rounded border border-violet-500/30 bg-violet-500/10 p-3">
            <div className="text-sm font-semibold text-violet-100">บัญชี Sheets</div>
            <div className="mt-1 text-xs text-violet-100/80">ภาพรวมสรุปและแท็บบัญชีที่แยกสำหรับรายรับรายจ่าย</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="rounded border border-violet-400/30 px-3 py-2 text-xs text-violet-50 hover:bg-violet-500/10 disabled:opacity-50" type="button" disabled={!sheetsCfg?.accounting_tab_url} onClick={() => window.open(sheetsCfg?.accounting_tab_url, '_blank', 'noopener,noreferrer')}>
                เปิดแท็บบัญชี
              </button>
              <button className="rounded border border-violet-400/30 px-3 py-2 text-xs text-violet-50 hover:bg-violet-500/10 disabled:opacity-50" type="button" disabled={!sheetsCfg?.sheet_url} onClick={() => window.open(sheetsCfg?.sheet_url, '_blank', 'noopener,noreferrer')}>
                เปิดสมุดทั้งหมด
              </button>
            </div>
          </div>
          <div className="rounded border border-red-500/30 bg-red-500/10 p-3">
            <div className="text-sm font-semibold text-red-100">Log Sheets</div>
            <div className="mt-1 text-xs text-red-100/80">แยก Audit, Add, Edit และ Sell ให้ดูย้อนหลังได้ง่าย</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button className="rounded border border-red-400/30 px-3 py-2 text-xs text-red-50 hover:bg-red-500/10 disabled:opacity-50" type="button" disabled={!sheetsCfg?.logs_tab_url} onClick={() => window.open(sheetsCfg?.logs_tab_url, '_blank', 'noopener,noreferrer')}>
                เปิดแท็บ Log
              </button>
              <button className="rounded border border-red-400/30 px-3 py-2 text-xs text-red-50 hover:bg-red-500/10 disabled:opacity-50" type="button" disabled={!sheetsCfg?.download_xlsx_url} onClick={() => window.open(sheetsCfg?.download_xlsx_url, '_blank', 'noopener,noreferrer')}>
                โหลดทั้งชีต .xlsx
              </button>
            </div>
          </div>
        </div>
        )}
      </div>

      {sheetsCfg?.usable ? (
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">ข้อมูลดิบเพิ่มเติม</div>
        <div className="mt-1 text-xs text-white/60">ใช้สำหรับตรวจละเอียดต่อใน Excel หรือ Google Sheets</div>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            disabled={busyKey !== null}
            className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
            onClick={async () => {
              setBusyKey('products')
              try {
                const items = await fetchAllProducts()
                const rows = items.map((p) => ({
                  sku: p.sku,
                  name_th: p.name.th,
                  name_en: p.name.en,
                  category: p.category,
                  type: p.type,
                  unit: p.unit,
                  cost_price: p.cost_price,
                  selling_price: p.selling_price ?? '',
                  stock_qty: p.stock_qty,
                  min_stock: p.min_stock,
                  max_stock: p.max_stock,
                  status: p.status
                }))
                downloadText(`products_${new Date().toISOString().slice(0, 10)}.csv`, Papa.unparse(rows))
              } finally {
                setBusyKey(null)
              }
            }}
          >
            {busyKey === 'products' ? 'กำลังเตรียมไฟล์...' : 'ดาวน์โหลดสินค้า (CSV)'}
          </button>

          <button
            disabled={busyKey !== null}
            className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-60"
            onClick={async () => {
              setBusyKey('transactions')
              try {
                const items = await fetchAllTransactions()
                const rows = items.map((x) => ({
                  created_at: x.created_at,
                  type: x.type,
                  sku: x.sku,
                  product_name: x.product_name,
                  qty: x.qty,
                  unit: x.unit,
                  note: x.note,
                  actor_username: x.actor_username ?? ''
                }))
                downloadText(`transactions_${new Date().toISOString().slice(0, 10)}.csv`, Papa.unparse(rows))
              } finally {
                setBusyKey(null)
              }
            }}
          >
            {busyKey === 'transactions' ? 'กำลังเตรียมไฟล์...' : 'ดาวน์โหลดธุรกรรมสต็อก (CSV)'}
          </button>
        </div>
      </div>
      ) : null}
    </div>
  )
}
