import { useEffect, useMemo, useState } from 'react'
import { Pie, PieChart, ResponsiveContainer, Cell, Tooltip, Legend } from 'recharts'

import { listProducts } from '../../services/products'
import type { Product } from '../../types/models'
import { formatTHB } from '../../utils/money'

const COLORS: Record<string, string> = {
  FULL: '#22c55e',
  NORMAL: '#60a5fa',
  LOW: '#f59e0b',
  CRITICAL: '#ef4444',
  OUT: '#64748b',
  TEST: '#0ea5e9'
}

export function OwnerCheckPage() {
  const [busy, setBusy] = useState(true)
  const [items, setItems] = useState<Product[]>([])

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const res = await listProducts({ limit: 500, offset: 0 })
        if (!cancelled) setItems(res.items)
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

  const stockValue = useMemo(
    () => items.reduce((sum, p) => sum + Number(p.stock_qty || 0) * Number(p.cost_price || 0), 0),
    [items]
  )
  const salesValue = useMemo(
    () => items.reduce((sum, p) => sum + Number(p.stock_qty || 0) * Number(p.selling_price || 0), 0),
    [items]
  )

  const statusChart = useMemo(() => {
    const map = new Map<string, number>()
    for (const x of items) map.set(x.status, (map.get(x.status) || 0) + 1)
    return Array.from(map.entries()).map(([name, value]) => ({ name, value }))
  }, [items])

  const categoryChart = useMemo(() => {
    const map = new Map<string, number>()
    for (const x of items) {
      const k = x.category || 'ไม่ระบุ'
      map.set(k, (map.get(k) || 0) + 1)
    }
    return Array.from(map.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10)
  }, [items])

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">สำหรับเจ้าของ</div>
        <div className="mt-1 text-xs text-white/60">ภาพรวมสินค้าแบบกราฟสำหรับผู้บริหาร</div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">สถานะสินค้า</div>
          <div className="mt-3 h-[320px]">
            {busy ? (
              <div className="text-sm text-white/60">กำลังโหลด...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusChart} dataKey="value" nameKey="name" outerRadius={110} label>
                    {statusChart.map((entry) => (
                      <Cell key={entry.name} fill={COLORS[entry.name] || '#94a3b8'} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">หมวดหมู่สินค้า (Top 10)</div>
          <div className="mt-3 h-[320px]">
            {busy ? (
              <div className="text-sm text-white/60">กำลังโหลด...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={categoryChart} dataKey="value" nameKey="name" outerRadius={110} label />
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">รายละเอียด</div>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">สินค้าทั้งหมด</div>
            <div className="mt-1 text-xl font-semibold">{items.length}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">มูลค่าสต็อก (ต้นทุน)</div>
            <div className="mt-1 text-xl font-semibold">{formatTHB(stockValue)}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">มูลค่าสต็อก (ราคาขาย)</div>
            <div className="mt-1 text-xl font-semibold">{formatTHB(salesValue)}</div>
          </div>
          {statusChart.map((x) => (
            <div key={x.name} className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
              <div className="text-xs text-white/60">{x.name}</div>
              <div className="mt-1 text-xl font-semibold">{x.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

