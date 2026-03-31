import { useState } from 'react'
import Papa from 'papaparse'

import { listProducts } from '../../services/products'
import { fetchTransactions } from '../../services/dashboard'

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

export function ReportsPage() {
  const [busy, setBusy] = useState(false)

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">รายงาน (CSV)</div>
        <div className="mt-1 text-xs text-white/60">ดาวน์โหลดข้อมูลจริงจากระบบเพื่อทำรายงานต่อใน Excel/Google Sheets</div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-wrap gap-3">
          <button
            disabled={busy}
            className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
            onClick={async () => {
              setBusy(true)
              try {
                const res = await listProducts({ limit: 200, offset: 0 })
                const rows = res.items.map((p) => ({
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
                setBusy(false)
              }
            }}
          >
            ดาวน์โหลดสินค้า (CSV)
          </button>

          <button
            disabled={busy}
            className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-60"
            onClick={async () => {
              setBusy(true)
              try {
                const res = await fetchTransactions({ limit: 500, offset: 0 })
                const rows = res.items.map((x) => ({
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
                setBusy(false)
              }
            }}
          >
            ดาวน์โหลดธุรกรรมสต็อก (CSV)
          </button>
        </div>
      </div>
    </div>
  )
}

