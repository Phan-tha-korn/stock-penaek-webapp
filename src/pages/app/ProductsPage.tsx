import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  bulkDeleteProducts,
  bulkImportProductsZip,
  createProductWithImage,
  adjustStock,
  deleteProduct,
  downloadBulkImportTemplateZip,
  listProducts,
  restoreProduct,
  updateProductWithImage
} from '../../services/products'
import { formatTHB } from '../../utils/money'
import type { Product } from '../../types/models'
import { useAuthStore } from '../../store/authStore'
import { getSocket } from '../../services/socketManager'
import { ProductDetailModal } from '../../components/products/ProductDetailModal'

function StatusBadge(props: { status: string; isTest: boolean }) {
  const { t } = useTranslation()
  const color =
    props.status === 'OUT'
      ? 'bg-red-600 text-white'
      : props.status === 'CRITICAL'
        ? 'bg-orange-600 text-white'
        : props.status === 'LOW'
          ? 'bg-yellow-400 text-black'
          : props.status === 'FULL'
            ? 'bg-green-600 text-white'
            : props.status === 'NORMAL'
              ? 'bg-sky-600 text-white'
              : 'bg-purple-600 text-white'

  return (
    <span className={`inline-flex items-center gap-2 rounded px-2 py-0.5 text-xs font-semibold ${color}`}>
      {props.isTest ? <span className="rounded bg-[color:var(--color-primary)] px-1 text-black">{t('stockStatus.TEST')}</span> : null}
      <span>{t(`stockStatus.${props.status}`)}</span>
    </span>
  )
}

function downloadBlobFile(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function ProductsPage() {
  const role = useAuthStore((s) => s.role)
  const user = useAuthStore((s) => s.user)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(true)
  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [showDeleted, setShowDeleted] = useState(false)
  const [creating, setCreating] = useState(false)
  const [bulkCreating, setBulkCreating] = useState(false)
  const [newSku, setNewSku] = useState('')
  const [newNameTh, setNewNameTh] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [newUnit, setNewUnit] = useState('')
  const [newCostPrice, setNewCostPrice] = useState<number | ''>('')
  const [newSellingPrice, setNewSellingPrice] = useState<number | ''>('')
  const [newStockQty, setNewStockQty] = useState<number | ''>('')
  const [newMin, setNewMin] = useState<number | ''>('')
  const [newMax, setNewMax] = useState<number | ''>('')
  const [newImageFile, setNewImageFile] = useState<File | null>(null)
  const [bulkZipFile, setBulkZipFile] = useState<File | null>(null)
  const [bulkZipMsg, setBulkZipMsg] = useState('')
  const [bulkTemplateRows, setBulkTemplateRows] = useState('5')
  const [editing, setEditing] = useState<Product | null>(null)
  const [editNameTh, setEditNameTh] = useState('')
  const [editCategory, setEditCategory] = useState('')
  const [editUnit, setEditUnit] = useState('')
  const [editCost, setEditCost] = useState<number | ''>('')
  const [editSell, setEditSell] = useState<number | ''>('')
  const [editMin, setEditMin] = useState<number | ''>('')
  const [editMax, setEditMax] = useState<number | ''>('')
  const [editImageFile, setEditImageFile] = useState<File | null>(null)
  const [selectedSkus, setSelectedSkus] = useState<string[]>([])

  const canManage = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const canAdjust = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const params = useMemo(
    () => ({ q: q.trim() || undefined, limit: 50, offset: 0, include_deleted: canManage ? showDeleted : undefined }),
    [q, showDeleted, canManage]
  )

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const res = await listProducts(params)
        if (cancelled) return
        setItems(res.items)
        setTotal(res.total)
        setSelectedSkus([])
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
    const s = getSocket(user?.id)
    if (!s) return
    const onStockUpdated = (evt: any) => {
      const sku = String(evt?.sku || '')
      if (!sku) return
      setItems((prev) =>
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
    }
    s.on('stock_updated', onStockUpdated)
    return () => {
      s.off('stock_updated', onStockUpdated)
    }
  }, [user?.id])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="text-sm font-semibold">สินค้า</div>
          {canManage ? (
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
              onClick={() => setShowDeleted((v) => !v)}
              type="button"
            >
              {showDeleted ? 'ซ่อนที่ลบ' : 'แสดงที่ลบ'}
            </button>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canManage ? (
            <>
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                onClick={() => setBulkCreating(true)}
                type="button"
              >
                + เพิ่มหลายรายการ
              </button>
              <button
                className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90"
                onClick={() => setCreating(true)}
                type="button"
              >
                + เพิ่มสินค้า
              </button>
            </>
          ) : null}
        </div>
        <input
          className="w-full max-w-sm rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="ค้นหาด้วย SKU / ชื่อ / บาร์โค้ด"
        />
      </div>

      {canManage && selectedSkus.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/70 px-3 py-2 text-sm backdrop-blur">
          <div className="text-white/80">เลือกแล้ว {selectedSkus.length} รายการ</div>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-1.5 text-sm text-white/80 hover:bg-white/10"
              type="button"
              onClick={() => setSelectedSkus([])}
            >
              ล้างที่เลือก
            </button>
            <button
              className="rounded border border-red-500/30 px-3 py-1.5 text-sm text-red-200 hover:bg-red-500/10"
              type="button"
              onClick={async () => {
                const ok = window.confirm(`ยืนยันลบ ${selectedSkus.length} รายการ?`)
                if (!ok) return
                const reason = window.prompt('เหตุผลในการลบ (ไม่บังคับ)') || ''
                try {
                  await bulkDeleteProducts(selectedSkus, reason)
                  const res = await listProducts(params)
                  setItems(res.items)
                  setTotal(res.total)
                } catch {
                  alert('ลบหลายรายการไม่สำเร็จ')
                }
              }}
            >
              ลบที่เลือก
            </button>
          </div>
        </div>
      ) : null}

      {creating ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="card w-full max-w-lg rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
              <div className="text-sm font-semibold">เพิ่มสินค้าใหม่</div>
              <button onClick={() => setCreating(false)} className="text-white/60 hover:text-white" type="button">
                ✕
              </button>
            </div>
            <div className="space-y-3 overflow-y-auto p-6">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="SKU (เช่น TH-FOOD-0005)"
                value={newSku}
                onChange={(e) => setNewSku(e.target.value)}
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="ชื่อสินค้า (ไทย)"
                value={newNameTh}
                onChange={(e) => setNewNameTh(e.target.value)}
              />
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  placeholder="ประเภท"
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                />
                <input
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  placeholder="หน่วย (เช่น ชิ้น, กล่อง)"
                  value={newUnit}
                  onChange={(e) => setNewUnit(e.target.value)}
                />
              </div>
              <input
                type="number"
                min={0}
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="จำนวนที่ควรมี (max stock)"
                value={newMax}
                onChange={(e) => setNewMax(e.target.value ? Number(e.target.value) : '')}
              />
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  placeholder="ต้นทุน/หน่วย"
                  value={newCostPrice}
                  onChange={(e) => setNewCostPrice(e.target.value ? Number(e.target.value) : '')}
                />
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  placeholder="ราคาขาย/หน่วย"
                  value={newSellingPrice}
                  onChange={(e) => setNewSellingPrice(e.target.value ? Number(e.target.value) : '')}
                />
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  placeholder="จำนวนตั้งต้น"
                  value={newStockQty}
                  onChange={(e) => setNewStockQty(e.target.value ? Number(e.target.value) : '')}
                />
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  placeholder="จำนวนขั้นต่ำ"
                  value={newMin}
                  onChange={(e) => setNewMin(e.target.value ? Number(e.target.value) : '')}
                />
              </div>
              <input
                type="file"
                accept="image/*"
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm text-white/80 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-black/40 file:px-3 file:py-1.5"
                onChange={(e) => setNewImageFile(e.target.files?.[0] || null)}
              />
              <div className="flex flex-wrap justify-end gap-2 pt-2">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  onClick={() => setCreating(false)}
                  type="button"
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                  type="button"
                  onClick={async () => {
                    const sku = newSku.trim()
                    const name_th = newNameTh.trim()
                    if (!sku || !name_th) return
                    try {
                      await createProductWithImage(
                        {
                        sku,
                        name_th,
                        category: newCategory.trim(),
                        unit: newUnit.trim(),
                        cost_price: typeof newCostPrice === 'number' ? newCostPrice : 0,
                        selling_price: typeof newSellingPrice === 'number' ? newSellingPrice : null,
                        stock_qty: typeof newStockQty === 'number' ? newStockQty : 0,
                        min_stock: typeof newMin === 'number' ? newMin : 0,
                        max_stock: typeof newMax === 'number' ? newMax : 0
                        },
                        newImageFile || undefined
                      )
                      setCreating(false)
                      setNewSku('')
                      setNewNameTh('')
                      setNewCategory('')
                      setNewUnit('')
                      setNewCostPrice('')
                      setNewSellingPrice('')
                      setNewStockQty('')
                      setNewMin('')
                      setNewMax('')
                      setNewImageFile(null)
                      const res = await listProducts(params)
                      setItems(res.items)
                      setTotal(res.total)
                    } catch {
                      alert('เพิ่มสินค้าไม่สำเร็จ (SKU ซ้ำหรือข้อมูลไม่ถูกต้อง)')
                    }
                  }}
                >
                  บันทึก
                </button>
              </div>
            </div>
          </div>
        </div>
        </div>
      ) : null}

      {bulkCreating ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="card w-full max-w-2xl rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl flex max-h-[calc(100vh-2rem)] flex-col">
              <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
                <div className="text-sm font-semibold">เพิ่มสินค้าใหม่หลายรายการ</div>
                <button onClick={() => setBulkCreating(false)} className="text-white/60 hover:text-white" type="button">
                  ✕
                </button>
              </div>
              <div className="space-y-3 overflow-y-auto p-6">
                <div className="text-xs text-white/60">
                  อัปโหลดไฟล์ ZIP ที่มี <span className="font-mono">products.csv</span> และรูปภาพสินค้าในไฟล์เดียวกัน
                </div>
                <div className="text-xs text-white/50">
                  คอลัมน์ที่รองรับ: sku,name_th,category,unit,stock_qty,min_stock,max_stock,cost_price,selling_price,image_key
                </div>
                <div className="rounded border border-[color:var(--color-border)] bg-white/5 p-3">
                  <div className="text-xs text-white/60">โหลดไฟล์ตัวอย่าง ZIP</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      className="w-28 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                      value={bulkTemplateRows}
                      onChange={(e) => setBulkTemplateRows(e.target.value)}
                      inputMode="numeric"
                      placeholder="จำนวนรายการ"
                    />
                    <button
                      className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                      type="button"
                      onClick={async () => {
                        const rows = Math.max(1, Math.min(200, Number(bulkTemplateRows) || 5))
                        const blob = await downloadBulkImportTemplateZip(rows)
                        downloadBlobFile(blob, `products-template-${rows}-rows.zip`)
                      }}
                    >
                      โหลดตัวอย่าง ZIP
                    </button>
                  </div>
                  <div className="mt-2 text-xs text-white/45">ภายใน ZIP จะมี products.csv, README และโฟลเดอร์ images/ ให้เอาไปจัดไฟล์ต่อได้ทันที</div>
                </div>
                <input
                  type="file"
                  accept=".zip,application/zip"
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm text-white/80 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-black/40 file:px-3 file:py-1.5"
                  onChange={(e) => setBulkZipFile(e.target.files?.[0] || null)}
                />
                {bulkZipMsg ? <div className="rounded border border-white/10 bg-black/30 px-3 py-2 text-xs text-white/80">{bulkZipMsg}</div> : null}
                <div className="flex flex-wrap justify-end gap-2 pt-2">
                  <button
                    className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                    onClick={() => setBulkCreating(false)}
                    type="button"
                  >
                    ยกเลิก
                  </button>
                  <button
                    className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                    type="button"
                    onClick={async () => {
                      if (!bulkZipFile) return
                      setBulkZipMsg('กำลังนำเข้า...')
                      try {
                        const res = await bulkImportProductsZip(bulkZipFile, true)
                        setBulkZipMsg(`สำเร็จ: สร้าง ${res.created}, อัปเดต ${res.updated}, ผิดพลาด ${res.failed}`)
                        const list = await listProducts(params)
                        setItems(list.items)
                        setTotal(list.total)
                      } catch (e: any) {
                        setBulkZipMsg(`นำเข้าไม่สำเร็จ: ${e?.response?.data?.detail || 'unknown_error'}`)
                      }
                    }}
                  >
                    นำเข้า ZIP
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {editing ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="card w-full max-w-xl rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
                <div className="text-sm font-semibold">แก้ไขสินค้า {editing.sku}</div>
                <button onClick={() => setEditing(null)} className="text-white/60 hover:text-white" type="button">
                  ✕
                </button>
              </div>
              <div className="space-y-3 p-6">
                <input
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={editNameTh}
                  onChange={(e) => setEditNameTh(e.target.value)}
                  placeholder="ชื่อสินค้า (ไทย)"
                />
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <input
                    className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    value={editCategory}
                    onChange={(e) => setEditCategory(e.target.value)}
                    placeholder="ประเภท"
                  />
                  <input
                    className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    value={editUnit}
                    onChange={(e) => setEditUnit(e.target.value)}
                    placeholder="หน่วย"
                  />
                  <input
                    type="number"
                    className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    value={editCost}
                    onChange={(e) => setEditCost(e.target.value ? Number(e.target.value) : '')}
                    placeholder="ต้นทุน/หน่วย"
                  />
                  <input
                    type="number"
                    className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    value={editSell}
                    onChange={(e) => setEditSell(e.target.value ? Number(e.target.value) : '')}
                    placeholder="ราคาขาย/หน่วย"
                  />
                  <input
                    type="number"
                    className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    value={editMin}
                    onChange={(e) => setEditMin(e.target.value ? Number(e.target.value) : '')}
                    placeholder="ขั้นต่ำ"
                  />
                  <input
                    type="number"
                    className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                    value={editMax}
                    onChange={(e) => setEditMax(e.target.value ? Number(e.target.value) : '')}
                    placeholder="ที่ควรมี"
                  />
                </div>
                <input
                  type="file"
                  accept="image/*"
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm text-white/80 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-black/40 file:px-3 file:py-1.5"
                  onChange={(e) => setEditImageFile(e.target.files?.[0] || null)}
                />
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                    onClick={() => setEditing(null)}
                    type="button"
                  >
                    ยกเลิก
                  </button>
                  <button
                    className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                    type="button"
                    onClick={async () => {
                      try {
                        await updateProductWithImage(
                          editing.sku,
                          {
                            name_th: editNameTh.trim(),
                            category: editCategory.trim(),
                            unit: editUnit.trim(),
                            cost_price: typeof editCost === 'number' ? editCost : 0,
                            selling_price: typeof editSell === 'number' ? editSell : null,
                            min_stock: typeof editMin === 'number' ? editMin : 0,
                            max_stock: typeof editMax === 'number' ? editMax : 0
                          },
                          editImageFile || undefined
                        )
                        setEditing(null)
                        const res = await listProducts(params)
                        setItems(res.items)
                        setTotal(res.total)
                      } catch {
                        alert('แก้ไขสินค้าไม่สำเร็จ')
                      }
                    }}
                  >
                    บันทึกการแก้ไข
                  </button>
                </div>
              </div>
            </div>
          </div>
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
                {canManage ? <th className="px-4 py-2">เลือก</th> : null}
                <th className="px-4 py-2">SKU</th>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2">Stock</th>
                <th className="px-4 py-2">Price</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {busy && items.length === 0
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={`s_${i}`}>
                      <td className="px-4 py-3" colSpan={canManage ? 7 : 6}>
                        <div className="h-4 w-full max-w-2xl rounded skeleton" />
                      </td>
                    </tr>
                  ))
                : null}
              {items.map((p) => (
                <tr
                  key={p.id}
                  className="hover:bg-white/5"
                  onClick={(e) => {
                    if (!canManage) return
                    const target = e.target as HTMLElement
                    if (target.closest('button,input,a,textarea,select,label')) return
                    setSelectedSkus((prev) => (prev.includes(p.sku) ? prev.filter((x) => x !== p.sku) : [...prev, p.sku]))
                  }}
                >
                  {canManage ? (
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        checked={selectedSkus.includes(p.sku)}
                        onChange={(e) => {
                          const checked = e.target.checked
                          setSelectedSkus((prev) => {
                            if (checked) return prev.includes(p.sku) ? prev : [...prev, p.sku]
                            return prev.filter((x) => x !== p.sku)
                          })
                        }}
                      />
                    </td>
                  ) : null}
                  <td className="px-4 py-2 font-mono text-xs text-white/80">{p.sku}</td>
                  <td className="px-4 py-2">
                    <div className="text-white/90">{p.name.th}</div>
                    <div className="text-xs text-white/50">{p.name.en}</div>
                  </td>
                  <td className="px-4 py-2 text-white/70">{p.category}</td>
                  <td className="px-4 py-2">
                    <div className="font-semibold text-white/90">{p.stock_qty}</div>
                    <div className="mt-0.5 text-xs text-white/60">
                      <span className="text-white/50">ควรมี</span>{' '}
                      <span className="text-white/80">{Number(p.max_stock) > 0 ? p.max_stock : '—'}</span>
                      <span className="text-white/40"> • </span>
                      <span className="text-white/50">ขั้นต่ำ</span>{' '}
                      <span className="text-white/80">{p.min_stock}</span>
                    </div>
                    {Number(p.max_stock) > 0 ? (
                      <div className="mt-2 h-1.5 w-32 overflow-hidden rounded bg-white/10">
                        <div
                          className="h-full bg-[color:var(--color-secondary)]"
                          style={{
                            width: `${Math.max(0, Math.min(100, (Number(p.stock_qty) / Number(p.max_stock)) * 100))}%`
                          }}
                        />
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-white/70">
                    <div className="text-xs">
                      ต้นทุน: <span className="text-white/90">{formatTHB(p.cost_price)}</span>
                    </div>
                    <div className="text-xs">
                      ขาย:{' '}
                      <span className="text-white/90">{p.selling_price == null ? '-' : formatTHB(p.selling_price)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex flex-col items-start gap-2">
                      <StatusBadge status={p.status} isTest={p.is_test} />
                      <button
                        className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                        type="button"
                        onClick={() => setSelectedProduct(p)}
                      >
                        รายละเอียด
                      </button>
                      <div className="flex flex-wrap items-center gap-2">
                        {canManage && (p.notes || '').startsWith('__DELETED__:') ? (
                          <button
                            className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                            type="button"
                            onClick={async () => {
                              await restoreProduct(p.sku)
                              const res = await listProducts(params)
                              setItems(res.items)
                              setTotal(res.total)
                            }}
                          >
                            กู้คืน
                          </button>
                        ) : null}
                        {canManage && !(p.notes || '').startsWith('__DELETED__:') ? (
                          <button
                            className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                            type="button"
                            onClick={() => {
                              setEditing(p)
                              setEditNameTh(p.name.th)
                              setEditCategory(p.category || '')
                              setEditUnit(p.unit || '')
                              setEditCost(Number(p.cost_price || 0))
                              setEditSell(p.selling_price ? Number(p.selling_price) : '')
                              setEditMin(Number(p.min_stock || 0))
                              setEditMax(Number(p.max_stock || 0))
                              setEditImageFile(null)
                            }}
                          >
                            แก้ไข
                          </button>
                        ) : null}
                        {canAdjust && !(p.notes || '').startsWith('__DELETED__:') ? (
                          <button
                            className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                            type="button"
                            onClick={async () => {
                              const nextQtyRaw = window.prompt(`ตั้งยอดสต็อก (จำนวนคงเหลือ) สำหรับ ${p.sku}`, String(p.stock_qty || '0'))
                              if (nextQtyRaw == null) return
                              const nextQty = Number(nextQtyRaw)
                              if (!Number.isFinite(nextQty) || nextQty < 0) {
                                alert('จำนวนไม่ถูกต้อง')
                                return
                              }
                              const reason = window.prompt('หมายเหตุ (ไม่บังคับ)') || ''
                              try {
                                const updated = await adjustStock(p.sku, { qty: nextQty, type: 'ADJUST', reason })
                                setItems((prev) => prev.map((x) => (x.sku === p.sku ? updated : x)))
                              } catch {
                                alert('ตั้งยอดไม่สำเร็จ')
                              }
                            }}
                          >
                            ตั้งยอด
                          </button>
                        ) : null}
                        {canManage && !(p.notes || '').startsWith('__DELETED__:') ? (
                          <button
                            className="rounded border border-red-500/30 px-2 py-1 text-xs text-red-200 hover:bg-red-500/10"
                            type="button"
                            onClick={async () => {
                              const ok = window.confirm(`ยืนยันลบสินค้า ${p.sku}?`)
                              if (!ok) return
                              try {
                                const reason = window.prompt('เหตุผลในการลบ (ไม่บังคับ)') || ''
                                await deleteProduct(p.sku, reason)
                                const res = await listProducts(params)
                                setItems(res.items)
                                setTotal(res.total)
                              } catch {
                                alert('ลบสินค้าไม่สำเร็จ')
                              }
                            }}
                          >
                            ลบ
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
              {!busy && items.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-sm text-white/60" colSpan={canManage ? 7 : 6}>
                    ไม่พบสินค้า
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {selectedProduct ? (
        <ProductDetailModal
          product={selectedProduct}
          onClose={() => setSelectedProduct(null)}
          onUpdate={(updated) => {
            setSelectedProduct(updated)
            setItems((prev) => prev.map((x) => (x.sku === updated.sku ? updated : x)))
          }}
        />
      ) : null}
    </div>
  )
}

