import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { fetchTransactions, type TransactionItem } from '../../services/dashboard'
import { adjustStock, listProducts } from '../../services/products'
import type { Product } from '../../types/models'
import { useAuthStore } from '../../store/authStore'
import { getSocket } from '../../services/socketManager'
import { productDisplayName } from '../../utils/product'

function typeLabel(t: (k: string) => string, v: TransactionItem['type']) {
  if (v === 'STOCK_IN') return t('product.stockIn')
  if (v === 'STOCK_OUT') return t('product.stockOut')
  return 'ตั้งยอด'
}

export function TransactionsPage() {
  const { t } = useTranslation()
  const role = useAuthStore((s) => s.role)
  const user = useAuthStore((s) => s.user)
  const [sku, setSku] = useState('')
  const [type, setType] = useState<string>('')
  const [busy, setBusy] = useState(true)
  const [items, setItems] = useState<TransactionItem[]>([])
  const [total, setTotal] = useState(0)
  const [period, setPeriod] = useState<string>('all')
  const [formSku, setFormSku] = useState('')
  const [formQty, setFormQty] = useState<number | ''>('')
  const [formType, setFormType] = useState<'STOCK_IN' | 'STOCK_OUT' | 'ADJUST'>('STOCK_OUT')
  const [formNote, setFormNote] = useState('')
  const [skuSuggestions, setSkuSuggestions] = useState<Product[]>([])
  const [realtimeBusy, setRealtimeBusy] = useState(false)

  const canAccountingAction = role === 'ADMIN' || role === 'DEV' || role === 'OWNER'
  const canAdjustAbsolute = role === 'ADMIN' || role === 'DEV' || role === 'OWNER'

  const now = Date.now()
  const dateFrom = useMemo(() => {
    if (period === 'day') return new Date(now - 24 * 60 * 60 * 1000).toISOString()
    if (period === 'week') return new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString()
    if (period === 'month') return new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString()
    return undefined
  }, [period, now])

  const params = useMemo(
    () => ({
      sku: sku.trim() || undefined,
      type: type || undefined,
      date_from: dateFrom,
      limit: 200,
      offset: 0
    }),
    [sku, type, dateFrom]
  )

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const res = await fetchTransactions(params)
        if (cancelled) return
        setItems(res.items)
        setTotal(res.total)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [params])

  useEffect(() => {
    let cancelled = false
    const s = getSocket(user?.id)
    if (!s) return
    let timer: number | null = null
    const onStockUpdated = () => {
      if (timer) window.clearTimeout(timer)
      timer = window.setTimeout(async () => {
        setRealtimeBusy(true)
        try {
          const res = await fetchTransactions(params)
          if (cancelled) return
          setItems(res.items)
          setTotal(res.total)
        } catch {
        } finally {
          if (!cancelled) setRealtimeBusy(false)
        }
      }, 400)
    }
    s.on('stock_updated', onStockUpdated)
    return () => {
      cancelled = true
      s.off('stock_updated', onStockUpdated)
      if (timer) window.clearTimeout(timer)
    }
  }, [user?.id, params])

  useEffect(() => {
    const q = formSku.trim()
    if (!q) {
      setSkuSuggestions([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      try {
        const res = await listProducts({ q, limit: 8 })
        if (!cancelled) setSkuSuggestions(res.items)
      } catch {
        if (!cancelled) setSkuSuggestions([])
      }
    }, 200)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [formSku])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">ธุรกรรมสต็อก</div>
          <div className="text-xs text-white/50">{realtimeBusy ? 'กำลังอัปเดตแบบเรียลไทม์...' : 'อัปเดตแบบเรียลไทม์'}</div>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          <input
            className="w-full max-w-sm flex-1 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="ค้นหาด้วยรหัสสินค้า"
          />
          <select
            className="w-full max-w-xs rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] sm:w-auto"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="">ทั้งหมด</option>
            <option value="STOCK_IN">{t('product.stockIn')}</option>
            <option value="STOCK_OUT">{t('product.stockOut')}</option>
            <option value="ADJUST">ตั้งยอด</option>
          </select>
          <select
            className="w-full max-w-xs rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] sm:w-auto"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="all">ทุกช่วงเวลา</option>
            <option value="day">ย้อนหลัง 1 วัน</option>
            <option value="week">ย้อนหลัง 7 วัน</option>
            <option value="month">ย้อนหลัง 30 วัน</option>
          </select>
        </div>
      </div>

      {canAccountingAction ? (
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="mb-2 text-sm font-semibold">บันทึก เบิก/ขาย/ซื้อเพิ่ม</div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-12">
            <div className="relative md:col-span-3">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={formSku}
                onChange={(e) => setFormSku(e.target.value)}
                placeholder="รหัสสินค้า / ชื่อสินค้า / บาร์โค้ด (พิมพ์บางส่วนได้)"
              />
              {skuSuggestions.length > 0 ? (
                <div className="absolute z-20 mt-1 w-full overflow-hidden rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-xl">
                  {skuSuggestions.map((p) => (
                    <div
                      key={p.id}
                      className="cursor-pointer border-b border-white/5 px-3 py-2 hover:bg-white/10"
                      onClick={() => {
                        setFormSku(p.sku)
                        setFormNote((prev) => prev || `สินค้า: ${productDisplayName(p)}`)
                        setSkuSuggestions([])
                      }}
                    >
                      <div className="text-sm text-white/90">{productDisplayName(p)}</div>
                      <div className="text-xs text-white/60">{p.sku}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
            <input
              type="number"
              min={0}
              className="rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] md:col-span-2"
              value={formQty}
              onChange={(e) => setFormQty(e.target.value ? Number(e.target.value) : '')}
              placeholder="จำนวน"
            />
            <select
              className="rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] md:col-span-2"
              value={formType}
              onChange={(e) => setFormType(e.target.value as 'STOCK_IN' | 'STOCK_OUT' | 'ADJUST')}
            >
              <option value="STOCK_IN">ซื้อเพิ่ม (+)</option>
              <option value="STOCK_OUT">เบิก/ขาย (-)</option>
              {canAdjustAbsolute ? <option value="ADJUST">ตั้งยอด (แก้สต็อก)</option> : null}
            </select>
            <input
              className="rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] md:col-span-3"
              value={formNote}
              onChange={(e) => setFormNote(e.target.value)}
              placeholder={formType === 'ADJUST' ? 'หมายเหตุ (เช่น ตรวจนับจริง)' : 'หมายเหตุ'}
            />
            <button
              className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90 md:col-span-2"
              type="button"
              onClick={async () => {
                const s = formSku.trim()
                const q = Number(formQty)
                if (!s) return
                if (Number.isNaN(q)) return
                if (formType !== 'ADJUST' && (!q || q <= 0)) return
                if (formType === 'ADJUST' && !canAdjustAbsolute) return
                if (formType === 'ADJUST' && q < 0) return
                try {
                  await adjustStock(s, { qty: q, type: formType, reason: formNote })
                  setFormQty('')
                  setFormNote('')
                  const res = await fetchTransactions(params)
                  setItems(res.items)
                  setTotal(res.total)
                } catch {
                  alert('บันทึกรายการไม่สำเร็จ (ตรวจสอบรหัสสินค้าและจำนวน)')
                }
              }}
            >
              บันทึกรายการ
            </button>
          </div>
          {formType === 'ADJUST' ? (
            <div className="mt-2 text-xs text-white/60">โหมดตั้งยอด: ใส่ “จำนวนคงเหลือปัจจุบันที่ถูกต้อง” (รองรับ 0)</div>
          ) : null}
        </div>
      ) : null}

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 backdrop-blur">
        <div className="border-b border-[color:var(--color-border)] px-4 py-2 text-xs text-white/60">
          {busy ? 'กำลังโหลด...' : `${total} รายการ`}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-white/60">
              <tr className="border-b border-[color:var(--color-border)]">
                <th className="px-4 py-2">เวลา</th>
                <th className="px-4 py-2">ประเภท</th>
                <th className="px-4 py-2">รหัสสินค้า</th>
                <th className="px-4 py-2">สินค้า</th>
                <th className="px-4 py-2">จำนวน</th>
                <th className="px-4 py-2">หมายเหตุ</th>
                <th className="px-4 py-2">ผู้ทำรายการ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {items.map((x) => (
                <tr key={x.id} className="hover:bg-white/5">
                  <td className="px-4 py-2 text-xs text-white/70">{new Date(x.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2">{typeLabel(t, x.type)}</td>
                  <td className="px-4 py-2 font-mono text-xs text-white/80">{x.sku}</td>
                  <td className="px-4 py-2 text-white/80">{x.product_name}</td>
                  <td className="px-4 py-2">
                    <span className="font-semibold text-white/90">{x.qty}</span>{' '}
                    <span className="text-xs text-white/50">{x.unit}</span>
                  </td>
                  <td className="px-4 py-2 text-white/70">{x.note}</td>
                  <td className="px-4 py-2 text-white/60">{x.actor_username ?? '-'}</td>
                </tr>
              ))}
              {!busy && items.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-sm text-white/60" colSpan={7}>
                    ยังไม่มีรายการ
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

