import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { adjustStock } from '../../services/products'
import { useConfigStore } from '../../store/configStore'
import { useAuthStore } from '../../store/authStore'
import type { Product } from '../../types/models'
import { formatTHB } from '../../utils/money'

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'OUT':
      return 'bg-red-600 text-white'
    case 'CRITICAL':
      return 'bg-orange-600 text-white'
    case 'LOW':
      return 'bg-yellow-400 text-black'
    case 'FULL':
      return 'bg-green-600 text-white'
    case 'NORMAL':
      return 'bg-sky-600 text-white'
    case 'TEST':
      return 'bg-purple-600 text-white'
    default:
      return 'bg-zinc-600 text-white'
  }
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

export function ProductDetailModal(props: {
  product: Product
  onClose: () => void
  onUpdate?: (p: Product) => void
  onToast?: (msg: string, type?: 'success' | 'error' | 'info') => void
}) {
  const { t } = useTranslation()
  const config = useConfigStore((s) => s.config)
  const role = useAuthStore((s) => s.role)
  const canAdjust = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'

  const product = props.product
  const onToast = props.onToast || (() => {})
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const lastActiveRef = useRef<HTMLElement | null>(null)
  const barcodeRef = useRef<SVGSVGElement>(null)
  const [QRCodeComp, setQRCodeComp] = useState<any>(null)

  const [adjustQty, setAdjustQty] = useState<number | ''>('')
  const [adjustReason, setAdjustReason] = useState('')
  const [adjustBusy, setAdjustBusy] = useState(false)
  const [adjustError, setAdjustError] = useState<string | null>(null)

  const stockQty = Number(product.stock_qty || 0)
  const maxStock = Number(product.max_stock || 0)
  const minStock = Number(product.min_stock || 0)
  const pct = maxStock > 0 ? Math.max(0, Math.min(100, (stockQty / maxStock) * 100)) : 0
  const restockQty = Math.max(0, maxStock - stockQty)
  const totalValue = stockQty * Number(product.cost_price || 0)
  const barcodeValue = String(product.barcode || '').trim() || product.sku

  const handleAdjust = async (type: 'STOCK_IN' | 'STOCK_OUT' | 'ADJUST') => {
    if (adjustQty === '') return
    if (type !== 'ADJUST' && (!adjustQty || adjustQty <= 0)) return
    if (type === 'ADJUST' && Number(adjustQty) < 0) return
    setAdjustBusy(true)
    setAdjustError(null)
    try {
      const updated = await adjustStock(product.sku, {
        qty: Number(adjustQty),
        type,
        reason: adjustReason
      })
      props.onUpdate?.(updated)
      setAdjustQty('')
      setAdjustReason('')
      onToast(t('product.adjustSuccess'), 'success')
    } catch (e: any) {
      if (e?.response?.status === 400) {
        setAdjustError(t('product.insufficientStock'))
      } else {
        setAdjustError(t('errors.generic'))
      }
    } finally {
      setAdjustBusy(false)
    }
  }

  useEffect(() => {
    ;(async () => {
      if (!barcodeRef.current) return
      try {
        const mod: any = await import('jsbarcode')
        const fn = mod?.default || mod
        if (!fn) return
        fn(barcodeRef.current, barcodeValue, {
          format: 'CODE128',
          width: 1.5,
          height: 40,
          displayValue: true,
          background: 'transparent',
          lineColor: '#fff',
          margin: 0
        })
      } catch {
      }
    })()
  }, [barcodeValue])

  useEffect(() => {
    if (QRCodeComp) return
    import('react-qr-code')
      .then((m: any) => setQRCodeComp(() => m.default))
      .catch(() => {})
  }, [QRCodeComp])

  useEffect(() => {
    lastActiveRef.current = document.activeElement as HTMLElement | null
    // Focus close button for keyboard users
    window.setTimeout(() => closeBtnRef.current?.focus(), 0)
    return () => {
      lastActiveRef.current?.focus?.()
    }
  }, [])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') props.onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [props])

  const baseUrl = (config?.web_url || window.location.origin).replace(/\/+$/, '')
  const publicUrl = `${baseUrl}/public/product/${encodeURIComponent(product.sku)}`

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm md:items-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) props.onClose()
      }}
    >
      <div
        className="card w-full max-w-3xl rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl flex flex-col max-h-[calc(100vh-2rem)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-detail-title"
      >
        <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
          <h3 id="product-detail-title" className="text-lg font-semibold">{t('product.detailTitle')}</h3>
          <button
            ref={closeBtnRef}
            onClick={props.onClose}
            className="text-white/60 hover:text-white"
            type="button"
            aria-label={t('app.close')}
          >
            ✕
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6 overflow-y-auto">
          <div className="space-y-4">
            <div className="aspect-square w-full rounded-lg bg-black/30 flex items-center justify-center border border-[color:var(--color-border)] overflow-hidden">
              {product.image_url ? (
                <img src={product.image_url} alt={product.name?.th || product.sku} className="h-full w-full object-cover" />
              ) : (
                <div className="text-white/30 text-4xl">📦</div>
              )}
            </div>

            <div>
              <div className="text-xl font-bold">{product.name?.th || product.sku}</div>
              <div className="text-sm text-white/50">{product.name?.en || ''}</div>
              <div className="mt-2 text-xs text-white/50">อัปเดตล่าสุด: {formatUpdatedAt(product.updated_at)}</div>
            </div>

            <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-white/60 text-sm">{t('product.status')}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-semibold ${statusBadgeClass(product.status)}`}>{t(`stockStatus.${product.status}`)}</span>
              </div>
              <div className="flex justify-between items-baseline">
                <span className="text-white/60 text-sm">{t('product.currentStock')}</span>
                <span className="text-2xl font-bold text-[color:var(--color-primary)]">
                  {product.stock_qty} <span className="text-sm font-normal text-white/60">{product.unit}</span>
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[color:var(--color-border)] text-sm">
                <div className="text-white/60">ควรมี</div>
                <div className="text-white/90">{maxStock > 0 ? `${product.max_stock} ${product.unit}` : '—'}</div>
                <div className="text-white/60">ขั้นต่ำ</div>
                <div className="text-white/90">{`${product.min_stock} ${product.unit}`}</div>
                <div className="text-white/60">ต้องเติม</div>
                <div className="font-semibold text-white">{`${restockQty.toLocaleString('th-TH', { maximumFractionDigits: 2 })} ${product.unit}`}</div>
                <div className="text-white/60">% คงเหลือ</div>
                <div className="text-white/90">{maxStock > 0 ? `${pct.toFixed(1)}%` : '—'}</div>
              </div>
              {maxStock > 0 ? (
                <div className="mt-2 h-2 w-full overflow-hidden rounded bg-white/10">
                  <div className="h-full bg-[color:var(--color-secondary)]" style={{ width: `${pct}%` }} />
                </div>
              ) : null}
            </div>

            <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
              <div className="text-sm font-semibold">รายละเอียดสินค้า</div>
              <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <div className="text-white/60">SKU</div>
                <div className="font-mono text-white/90">{product.sku}</div>
                <div className="text-white/60">หมวดหมู่</div>
                <div className="text-white/90">{product.category || '-'}</div>
                <div className="text-white/60">ประเภท</div>
                <div className="text-white/90">{product.type || '-'}</div>
                <div className="text-white/60">หน่วยนับ</div>
                <div className="text-white/90">{product.unit || '-'}</div>
                <div className="text-white/60">โหมดทดสอบ</div>
                <div className="text-white/90">{product.is_test ? t('stockStatus.TEST') : '-'}</div>
                <div className="text-white/60">ต้นทุน/หน่วย</div>
                <div className="text-white/90">{formatTHB(product.cost_price)}</div>
                <div className="text-white/60">ราคาขาย/หน่วย</div>
                <div className="text-white/90">{product.selling_price == null ? '-' : formatTHB(product.selling_price)}</div>
                <div className="text-white/60">มูลค่าสต็อก</div>
                <div className="text-white/90">{formatTHB(totalValue)}</div>
                <div className="text-white/60">บาร์โค้ด</div>
                <div className="text-white/90">{barcodeValue || '-'}</div>
                <div className="text-white/60">ซัพพลายเออร์</div>
                <div className="text-white/90">{product.supplier || '-'}</div>
                <div className="text-white/60">หมายเหตุ</div>
                <div className="text-white/90">{product.notes || '-'}</div>
                <div className="text-white/60">ผู้สร้าง</div>
                <div className="text-white/90">{product.created_by || '-'}</div>
                <div className="text-white/60">สร้างเมื่อ</div>
                <div className="text-white/90">{formatUpdatedAt(product.created_at)}</div>
              </div>
            </div>

            {canAdjust ? (
              <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-4 space-y-3">
                {adjustError && <div className="text-red-400 text-xs mb-2">{adjustError}</div>}
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder={t('product.adjustQty')}
                    value={adjustQty}
                    onChange={(e) => setAdjustQty(e.target.value ? Number(e.target.value) : '')}
                    className="w-1/3 rounded border border-[color:var(--color-border)] bg-black/40 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    min="0"
                  />
                  <input
                    type="text"
                    placeholder={t('product.reason')}
                    value={adjustReason}
                    onChange={(e) => setAdjustReason(e.target.value)}
                    className="w-2/3 rounded border border-[color:var(--color-border)] bg-black/40 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    disabled={adjustBusy || adjustQty === '' || Number(adjustQty) <= 0}
                    onClick={() => handleAdjust('STOCK_IN')}
                    className="flex-1 rounded bg-green-500/20 text-green-400 border border-green-500/30 px-3 py-2 text-sm font-semibold hover:bg-green-500/30 disabled:opacity-50"
                    type="button"
                  >
                    + {t('product.stockIn')}
                  </button>
                  <button
                    disabled={adjustBusy || adjustQty === '' || Number(adjustQty) <= 0}
                    onClick={() => handleAdjust('STOCK_OUT')}
                    className="flex-1 rounded bg-red-500/20 text-red-400 border border-red-500/30 px-3 py-2 text-sm font-semibold hover:bg-red-500/30 disabled:opacity-50"
                    type="button"
                  >
                    - {t('product.stockOut')}
                  </button>
                  <button
                    disabled={adjustBusy || adjustQty === '' || Number(adjustQty) < 0}
                    onClick={() => handleAdjust('ADJUST')}
                    className="flex-1 rounded border border-[color:var(--color-border)] bg-white/5 px-3 py-2 text-sm font-semibold text-white/80 hover:bg-white/10 disabled:opacity-50"
                    type="button"
                  >
                    ตั้งยอด
                  </button>
                </div>
                <div className="text-xs text-white/50">ตั้งยอด: ใส่จำนวนคงเหลือปัจจุบันที่ถูกต้อง (รองรับ 0)</div>
              </div>
            ) : null}
          </div>

          <div className="flex flex-col items-center justify-start space-y-6 rounded-lg border border-[color:var(--color-border)] bg-white/5 p-6">
            <div className="text-center">
              <div className="mb-2 text-sm text-white/60">{t('product.publicScan')}</div>
              <div className="rounded-xl bg-white p-3 inline-block">
                {QRCodeComp ? <QRCodeComp value={publicUrl} size={220} level="Q" /> : <div className="h-[220px] w-[220px]" />}
              </div>
            </div>

            <div className="text-center w-full overflow-hidden">
              <div className="mb-2 text-sm text-white/60">{t('product.barcode')}</div>
              <svg ref={barcodeRef} className="max-w-full" />
            </div>

            <div className="w-full space-y-2 pt-4 border-t border-[color:var(--color-border)]">
              <button
                className="w-full rounded bg-[color:var(--color-primary)] px-4 py-2 font-semibold text-black hover:opacity-90 flex items-center justify-center gap-2"
                type="button"
                onClick={() => window.open(publicUrl, '_blank', 'noopener,noreferrer')}
              >
                {t('app.printQR')}
              </button>
              <button
                className="w-full rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(publicUrl)
                    onToast(t('app.copied'), 'success')
                  } catch {
                    onToast(t('errors.generic'), 'error')
                  }
                }}
              >
                {t('app.copyLink')}
              </button>
              <button
                className="w-full rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(product.sku)
                    onToast(t('app.copiedSku'), 'success')
                  } catch {
                    onToast(t('errors.generic'), 'error')
                  }
                }}
              >
                คัดลอก SKU
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
