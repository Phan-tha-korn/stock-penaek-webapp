import { useEffect, useMemo, useState, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { useTranslation } from 'react-i18next'

import {
  adjustStock,
  bulkCreateProducts,
  bulkDeleteProducts,
  bulkImportProductsZip,
  createProductWithImage,
  deleteProduct,
  downloadBulkImportTemplateZip,
  getProductFilterOptions,
  listProducts,
  restoreProduct,
  updateProductWithImage,
} from '../../services/products'
import {
  getInventoryRuleSettings,
  listProductCategories,
} from '../../services/productCategories'
import { formatTHB } from '../../utils/money'
import type { InventoryRuleSettings, Product, ProductCategory } from '../../types/models'
import { useAuthStore } from '../../store/authStore'
import { getSocket } from '../../services/socketManager'
import { ProductDetailModal } from '../../components/products/ProductDetailModal'
import { productDisplayName } from '../../utils/product'
import { useAlert, useConfirm, usePrompt } from '../../components/ui/ConfirmDialog'

const UNCATEGORIZED_VALUE = '__uncategorized__'

type ProductDraft = {
  sku: string
  name_th: string
  name_en: string
  category_id: string
  type: string
  unit: string
  cost_price: number | ''
  selling_price: number | ''
  stock_qty: number | ''
  min_stock: number | ''
  max_stock: number | ''
  supplier: string
  barcode: string
  notes: string
  imageFile: File | null
}

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
      <span>{t(`stockStatus.${props.status}`, { defaultValue: props.status })}</span>
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

function isDeletedProduct(product: Product) {
  return (product.notes || '').startsWith('__DELETED__:')
}

function integerOnlyUnit(unit: string) {
  const normalized = (unit || '').trim().toLowerCase()
  return normalized === 'ชิ้น' || normalized === 'piece' || normalized === 'pcs' || normalized === 'pc'
}

function roundByRule(value: number) {
  if (!Number.isFinite(value)) return 0
  const base = Math.floor(value)
  const decimal = Math.abs(value - base)
  return decimal <= 0.5 ? base : Math.ceil(value)
}

function computeAutoValues(stockQty: number, rules: InventoryRuleSettings, unit: string) {
  const maxValue = roundByRule(stockQty * Number(rules.max_multiplier || 2))
  const minValue = roundByRule(stockQty / Number(rules.min_divisor || 3))
  if (integerOnlyUnit(unit)) {
    return { min: Math.trunc(minValue), max: Math.trunc(maxValue) }
  }
  return { min: minValue, max: maxValue }
}

function normalizeQty(value: number | '', unit: string) {
  if (value === '') return ''
  if (!Number.isFinite(Number(value))) return ''
  const numeric = Number(value)
  return integerOnlyUnit(unit) ? Math.trunc(numeric) : numeric
}

function emptyDraft(defaultCategoryId = ''): ProductDraft {
  return {
    sku: '',
    name_th: '',
    name_en: '',
    category_id: defaultCategoryId,
    type: '',
    unit: '',
    cost_price: '',
    selling_price: '',
    stock_qty: '',
    min_stock: '',
    max_stock: '',
    supplier: '',
    barcode: '',
    notes: '',
    imageFile: null,
  }
}

function categoryLabel(product: Product) {
  return product.category?.trim() || 'ไม่ระบุหมวด'
}

function FilterSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`input-surface rounded border border-[color:var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] ${props.className || ''}`}
    />
  )
}

function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`input-surface w-full rounded border border-[color:var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] ${props.className || ''}`}
    />
  )
}

function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`input-surface w-full rounded border border-[color:var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)] ${props.className || ''}`}
    />
  )
}

function ProductFormFields(props: {
  draft: ProductDraft
  categories: ProductCategory[]
  onChange: (next: ProductDraft) => void
  rules: InventoryRuleSettings
  showSku?: boolean
}) {
  const { draft, categories, onChange, rules, showSku = true } = props

  function patch(next: Partial<ProductDraft>) {
    onChange({ ...draft, ...next })
  }

  function handleQtyChange(raw: string) {
    const nextQty = raw === '' ? '' : normalizeQty(Number(raw), draft.unit)
    const numericQty = nextQty === '' ? 0 : Number(nextQty)
    const auto = computeAutoValues(numericQty, rules, draft.unit)
    patch({
      stock_qty: nextQty,
      min_stock: nextQty === '' ? '' : auto.min,
      max_stock: nextQty === '' ? '' : auto.max,
    })
  }

  function handleUnitChange(unit: string) {
    const nextStock = normalizeQty(draft.stock_qty, unit)
    const nextMin = normalizeQty(draft.min_stock, unit)
    const nextMax = normalizeQty(draft.max_stock, unit)
    const numericQty = nextStock === '' ? 0 : Number(nextStock)
    const auto = computeAutoValues(numericQty, rules, unit)
    patch({
      unit,
      stock_qty: nextStock,
      min_stock: nextStock === '' ? nextMin : auto.min,
      max_stock: nextStock === '' ? nextMax : auto.max,
    })
  }

  return (
    <div className="space-y-3">
      {showSku ? (
        <TextInput
          placeholder="รหัสสินค้า"
          value={draft.sku}
          onChange={(e) => patch({ sku: e.target.value })}
        />
      ) : null}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <TextInput
          placeholder="ชื่อสินค้า"
          value={draft.name_th}
          onChange={(e) => patch({ name_th: e.target.value })}
        />
        <TextInput
          placeholder="ชื่อสินค้าเพิ่มเติม (ถ้ามี)"
          value={draft.name_en}
          onChange={(e) => patch({ name_en: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <FilterSelect value={draft.category_id} onChange={(e) => patch({ category_id: e.target.value })}>
          <option value="">ไม่ระบุหมวด</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </FilterSelect>
        <TextInput
          placeholder="ประเภทย่อย"
          value={draft.type}
          onChange={(e) => patch({ type: e.target.value })}
        />
        <TextInput
          placeholder="หน่วย เช่น ชิ้น / กก."
          value={draft.unit}
          onChange={(e) => handleUnitChange(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <TextInput
          type="number"
          min={0}
          step={0.001}
          placeholder="ต้นทุน/หน่วย"
          value={draft.cost_price}
          onChange={(e) => patch({ cost_price: e.target.value === '' ? '' : Number(e.target.value) })}
        />
        <TextInput
          type="number"
          min={0}
          step={0.001}
          placeholder="ราคาขาย/หน่วย"
          value={draft.selling_price}
          onChange={(e) => patch({ selling_price: e.target.value === '' ? '' : Number(e.target.value) })}
        />
        <TextInput
          type="number"
          min={0}
          step={integerOnlyUnit(draft.unit) ? 1 : 0.001}
          placeholder="จำนวนตั้งต้น"
          value={draft.stock_qty}
          onChange={(e) => handleQtyChange(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <TextInput
          type="number"
          min={0}
          step={integerOnlyUnit(draft.unit) ? 1 : 0.001}
          placeholder="จำนวนขั้นต่ำ"
          value={draft.min_stock}
          onChange={(e) => patch({ min_stock: e.target.value === '' ? '' : normalizeQty(Number(e.target.value), draft.unit) })}
        />
        <TextInput
          type="number"
          min={0}
          step={integerOnlyUnit(draft.unit) ? 1 : 0.001}
          placeholder="จำนวนที่ควรมี"
          value={draft.max_stock}
          onChange={(e) => patch({ max_stock: e.target.value === '' ? '' : normalizeQty(Number(e.target.value), draft.unit) })}
        />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <TextInput
          placeholder="ชื่อร้านค้าหรือซัพพลายเออร์"
          value={draft.supplier}
          onChange={(e) => patch({ supplier: e.target.value })}
        />
        <TextInput
          placeholder="บาร์โค้ด"
          value={draft.barcode}
          onChange={(e) => patch({ barcode: e.target.value })}
        />
      </div>
      <TextArea
        rows={2}
        placeholder="หมายเหตุ"
        value={draft.notes}
        onChange={(e) => patch({ notes: e.target.value })}
      />
      <input
        type="file"
        accept="image/*"
        className="input-surface w-full rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-[color:var(--color-input-bg)] file:px-3 file:py-1.5"
        onChange={(e) => patch({ imageFile: e.target.files?.[0] || null })}
      />
    </div>
  )
}

export function ProductsPage() {
  const role = useAuthStore((s) => s.role)
  const user = useAuthStore((s) => s.user)
  const showAlert = useAlert()
  const showConfirm = useConfirm()
  const showPrompt = usePrompt()
  const canManage = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const canAdjust = canManage

  const [busy, setBusy] = useState(true)
  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [selectedSkus, setSelectedSkus] = useState<string[]>([])
  const [showDeleted, setShowDeleted] = useState(false)
  const [categories, setCategories] = useState<ProductCategory[]>([])
  const [ruleSettings, setRuleSettings] = useState<InventoryRuleSettings>({ max_multiplier: 2, min_divisor: 3 })
  const [typeOptions, setTypeOptions] = useState<string[]>([])
  const [patchingCatalog, setPatchingCatalog] = useState(false)

  const [q, setQ] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [selectedType, setSelectedType] = useState('')

  const [creating, setCreating] = useState(false)
  const [savingCreate, setSavingCreate] = useState(false)
  const [createDraft, setCreateDraft] = useState<ProductDraft>(emptyDraft())

  const [bulkCreating, setBulkCreating] = useState(false)
  const [bulkCount, setBulkCount] = useState('2')
  const [bulkRows, setBulkRows] = useState<ProductDraft[]>([emptyDraft(), emptyDraft()])
  const [bulkSaving, setBulkSaving] = useState(false)
  const [bulkZipFile, setBulkZipFile] = useState<File | null>(null)
  const [bulkZipMsg, setBulkZipMsg] = useState('')
  const [bulkTemplateRows, setBulkTemplateRows] = useState('5')

  const [editing, setEditing] = useState<Product | null>(null)
  const [editingDraft, setEditingDraft] = useState<ProductDraft>(emptyDraft())

  const params = useMemo(() => {
    const base: Record<string, unknown> = {
      q: q.trim() || undefined,
      limit: 100,
      offset: 0,
      include_deleted: canManage ? showDeleted : undefined,
      product_type: selectedType.trim() || undefined,
    }
    if (selectedCategory === UNCATEGORIZED_VALUE) {
      base.uncategorized_only = true
    } else if (selectedCategory !== 'all') {
      base.category_id = selectedCategory
    }
    return base
  }, [q, canManage, showDeleted, selectedType, selectedCategory])

  async function loadCatalog() {
    const [productRes, categoryRes, filterRes, rulesRes] = await Promise.all([
      listProducts(params),
      listProductCategories(false),
      getProductFilterOptions({ include_deleted: canManage ? showDeleted : undefined }),
      getInventoryRuleSettings(),
    ])
    setItems(Array.isArray(productRes?.items) ? productRes.items : [])
    setTotal(Number(productRes?.total || 0))
    setCategories(Array.isArray(categoryRes?.items) ? categoryRes.items : [])
    setTypeOptions(Array.isArray(filterRes?.types) ? filterRes.types : [])
    setRuleSettings(rulesRes)
    setSelectedSkus([])
  }

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    loadCatalog()
      .catch(() => {
        if (!cancelled) {
          setItems([])
          setTotal(0)
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(false)
      })
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
                updated_at: String(evt?.updated_at ?? p.updated_at),
              }
            : p
        )
      )
    }

    const onCatalogPatch = (evt: any) => {
      const stage = String(evt?.stage || '')
      if (stage === 'started') {
        setPatchingCatalog(true)
        return
      }
      setPatchingCatalog(false)
      void loadCatalog().catch(() => {})
    }

    s.on('stock_updated', onStockUpdated)
    s.on('catalog_patch', onCatalogPatch)
    return () => {
      s.off('stock_updated', onStockUpdated)
      s.off('catalog_patch', onCatalogPatch)
    }
  }, [user?.id, params])

  useEffect(() => {
    setCreateDraft(emptyDraft(selectedCategory !== 'all' && selectedCategory !== UNCATEGORIZED_VALUE ? selectedCategory : ''))
  }, [selectedCategory])

  function refreshList() {
    return loadCatalog()
  }

  function bulkCountApply() {
    const count = Math.max(2, Number(bulkCount) || 2)
    setBulkRows((prev) => Array.from({ length: count }, (_, index) => prev[index] || emptyDraft()))
  }

  function openEdit(product: Product) {
    setEditing(product)
    setEditingDraft({
      sku: product.sku,
      name_th: productDisplayName(product),
      name_en: product?.name?.en || '',
      category_id: product.category_id || '',
      type: product.type || '',
      unit: product.unit || '',
      cost_price: Number(product.cost_price || 0),
      selling_price: product.selling_price == null ? '' : Number(product.selling_price),
      stock_qty: Number(product.stock_qty || 0),
      min_stock: Number(product.min_stock || 0),
      max_stock: Number(product.max_stock || 0),
      supplier: product.supplier || '',
      barcode: product.barcode || '',
      notes: product.notes || '',
      imageFile: null,
    })
  }

  async function handleCreate() {
    const sku = createDraft.sku.trim()
    const name_th = createDraft.name_th.trim()
    if (!sku || !name_th) {
      await showAlert('กรุณากรอกรหัสสินค้าและชื่อสินค้า')
      return
    }
    setSavingCreate(true)
    try {
      await createProductWithImage(
        {
          sku,
          name_th,
          name_en: createDraft.name_en.trim(),
          category_id: createDraft.category_id || null,
          type: createDraft.type.trim(),
          unit: createDraft.unit.trim(),
          cost_price: Number(createDraft.cost_price || 0),
          selling_price: createDraft.selling_price === '' ? null : Number(createDraft.selling_price),
          stock_qty: Number(createDraft.stock_qty || 0),
          min_stock: Number(createDraft.min_stock || 0),
          max_stock: Number(createDraft.max_stock || 0),
          supplier: createDraft.supplier.trim(),
          barcode: createDraft.barcode.trim(),
          notes: createDraft.notes.trim(),
        },
        createDraft.imageFile || undefined
      )
      setCreating(false)
      setCreateDraft(emptyDraft())
      await refreshList()
    } catch (e: any) {
      await showAlert(e?.response?.data?.detail || 'เพิ่มสินค้าไม่สำเร็จ')
    } finally {
      setSavingCreate(false)
    }
  }

  async function handleBulkCreate() {
    if (bulkRows.length < 2) {
      await showAlert('ต้องมีอย่างน้อย 2 รายการ')
      return
    }
    const invalid = bulkRows.find((row) => !row.sku.trim() || !row.name_th.trim())
    if (invalid) {
      await showAlert('กรอกรหัสสินค้าและชื่อสินค้าให้ครบทุกแถว')
      return
    }
    setBulkSaving(true)
    try {
      await bulkCreateProducts(
        bulkRows.map((row) => ({
          sku: row.sku.trim(),
          name_th: row.name_th.trim(),
          name_en: row.name_en.trim(),
          category_id: row.category_id || null,
          type: row.type.trim(),
          unit: row.unit.trim(),
          cost_price: Number(row.cost_price || 0),
          selling_price: row.selling_price === '' ? null : Number(row.selling_price),
          stock_qty: Number(row.stock_qty || 0),
          min_stock: Number(row.min_stock || 0),
          max_stock: Number(row.max_stock || 0),
          supplier: row.supplier.trim(),
          barcode: row.barcode.trim(),
          notes: row.notes.trim(),
        }))
      )
      setBulkCreating(false)
      setBulkRows([emptyDraft(), emptyDraft()])
      await refreshList()
    } catch (e: any) {
      await showAlert(e?.response?.data?.detail || 'เพิ่มหลายรายการไม่สำเร็จ')
    } finally {
      setBulkSaving(false)
    }
  }

  async function handleUpdate() {
    if (!editing) return
    try {
      await updateProductWithImage(
        editing.sku,
        {
          name_th: editingDraft.name_th.trim(),
          name_en: editingDraft.name_en.trim(),
          category_id: editingDraft.category_id || null,
          type: editingDraft.type.trim(),
          unit: editingDraft.unit.trim(),
          cost_price: Number(editingDraft.cost_price || 0),
          selling_price: editingDraft.selling_price === '' ? null : Number(editingDraft.selling_price),
          min_stock: Number(editingDraft.min_stock || 0),
          max_stock: Number(editingDraft.max_stock || 0),
          supplier: editingDraft.supplier.trim(),
          barcode: editingDraft.barcode.trim(),
          notes: editingDraft.notes.trim(),
        },
        editingDraft.imageFile || undefined
      )
      setEditing(null)
      await refreshList()
    } catch (e: any) {
      await showAlert(e?.response?.data?.detail || 'แก้ไขสินค้าไม่สำเร็จ')
    }
  }

  const categoryFilterLabel =
    selectedCategory === 'all'
      ? 'สินค้าทั้งหมด'
      : selectedCategory === UNCATEGORIZED_VALUE
        ? 'ไม่ระบุหมวด'
        : categories.find((c) => c.id === selectedCategory)?.name || 'หมวดหมู่'

  return (
    <div className="space-y-3">
      {patchingCatalog ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/55 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-sky-400/20 bg-[color:var(--color-card)]/95 p-6 text-center shadow-2xl">
            <div className="text-lg font-semibold text-sky-100">กำลังอัปเดตแพตช์สินค้า</div>
            <div className="mt-2 text-sm text-white/70">
              ระบบกำลังอัปเดตหมวดหมู่สินค้าและรีโหลดข้อมูลให้ตรงกัน กรุณารอสักครู่
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-sky-400" />
            </div>
          </div>
        </div>
      ) : null}

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
          <FilterSelect value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)} className="min-w-[220px]">
            <option value="all">สินค้าทั้งหมด</option>
            <option value={UNCATEGORIZED_VALUE}>ไม่ระบุหมวด</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </FilterSelect>
          {canManage ? (
            <>
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                onClick={() => {
                  setBulkCreating(true)
                  bulkCountApply()
                }}
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
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_220px_220px]">
        <TextInput
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="ค้นหารหัสสินค้า / ชื่อ / บาร์โค้ด / ร้านค้า / ประเภท"
        />
        <TextInput
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value)}
          placeholder="ค้นหาประเภทย่อย"
          list="product-type-options"
        />
        <datalist id="product-type-options">
          {typeOptions.map((type) => (
            <option key={type} value={type} />
          ))}
        </datalist>
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/70 px-3 py-2 text-sm text-white/70">
          กำลังดู: <span className="font-semibold text-white">{categoryFilterLabel}</span>
        </div>
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
                const ok = await showConfirm(`ยืนยันลบ ${selectedSkus.length} รายการ?`)
                if (!ok) return
                const reason = (await showPrompt('เหตุผลในการลบ (ไม่บังคับ)')) || ''
                try {
                  await bulkDeleteProducts(selectedSkus, reason)
                  await refreshList()
                } catch {
                  await showAlert('ลบหลายรายการไม่สำเร็จ')
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
            <div className="card flex max-h-[calc(100vh-2rem)] w-full max-w-3xl flex-col rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
                <div>
                  <div className="text-sm font-semibold">เพิ่มสินค้าใหม่</div>
                  <div className="text-xs text-white/50">ระบบจะคำนวณขั้นต่ำและจำนวนที่ควรมีให้อัตโนมัติจากสูตรปัจจุบัน</div>
                </div>
                <button onClick={() => setCreating(false)} className="text-white/60 hover:text-white" type="button">
                  ✕
                </button>
              </div>
              <div className="space-y-4 overflow-y-auto p-6">
                <ProductFormFields
                  draft={createDraft}
                  categories={categories}
                  onChange={setCreateDraft}
                  rules={ruleSettings}
                />
              </div>
              <div className="flex flex-wrap justify-end gap-2 border-t border-[color:var(--color-border)] px-6 py-4">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  onClick={() => setCreating(false)}
                  type="button"
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
                  onClick={handleCreate}
                  type="button"
                  disabled={savingCreate}
                >
                  {savingCreate ? 'กำลังบันทึก...' : 'บันทึก'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {bulkCreating ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="card flex max-h-[calc(100vh-2rem)] w-full max-w-6xl flex-col rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
                <div>
                  <div className="text-sm font-semibold">เพิ่มสินค้าใหม่หลายรายการ</div>
                  <div className="text-xs text-white/50">กำหนดจำนวนฟอร์มขั้นต่ำ 2 รายการ และเลือกหมวดได้แยกแต่ละแถว</div>
                </div>
                <button onClick={() => setBulkCreating(false)} className="text-white/60 hover:text-white" type="button">
                  ✕
                </button>
              </div>
              <div className="space-y-4 overflow-y-auto p-6">
                <div className="rounded border border-[color:var(--color-border)] bg-white/5 p-4">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-[180px_auto]">
                    <div>
                      <div className="mb-1 text-xs text-white/50">จำนวนรายการ</div>
                      <TextInput value={bulkCount} onChange={(e) => setBulkCount(e.target.value)} inputMode="numeric" />
                    </div>
                    <div className="flex items-end gap-2">
                      <button
                        type="button"
                        className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                        onClick={bulkCountApply}
                      >
                        สร้างฟอร์ม
                      </button>
                      <div className="text-xs text-white/50">ตั้งแต่ 2 รายการขึ้นไป</div>
                    </div>
                  </div>
                </div>

                <div className="rounded border border-[color:var(--color-border)] bg-white/5 p-4">
                  <div className="text-sm font-semibold">นำเข้า ZIP แบบเดิม</div>
                  <div className="mt-1 text-xs text-white/50">โหมดนี้ยังใช้งานได้เหมือนเดิม เผื่อกรณีเพิ่มจำนวนมากจากไฟล์</div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <TextInput
                      className="w-28"
                      value={bulkTemplateRows}
                      onChange={(e) => setBulkTemplateRows(e.target.value)}
                      inputMode="numeric"
                      placeholder="จำนวน"
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
                    <input
                      type="file"
                      accept=".zip,application/zip"
                      className="w-full max-w-sm rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm text-white/80 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-black/40 file:px-3 file:py-1.5"
                      onChange={(e) => setBulkZipFile(e.target.files?.[0] || null)}
                    />
                    <button
                      className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                      type="button"
                      onClick={async () => {
                        if (!bulkZipFile) return
                        setBulkZipMsg('กำลังนำเข้า...')
                        try {
                          const res = await bulkImportProductsZip(bulkZipFile, true)
                          setBulkZipMsg(`สำเร็จ: สร้าง ${res.created}, อัปเดต ${res.updated}, ผิดพลาด ${res.failed}`)
                          await refreshList()
                        } catch (e: any) {
                          setBulkZipMsg(`นำเข้าไม่สำเร็จ: ${e?.response?.data?.detail || 'unknown_error'}`)
                        }
                      }}
                    >
                      นำเข้า ZIP
                    </button>
                  </div>
                  {bulkZipMsg ? <div className="mt-2 text-xs text-white/70">{bulkZipMsg}</div> : null}
                </div>

                <div className="space-y-4">
                  {bulkRows.map((row, index) => (
                    <div key={index} className="rounded-xl border border-[color:var(--color-border)] bg-black/20 p-4">
                      <div className="mb-3 flex items-center justify-between gap-2">
                        <div className="text-sm font-semibold">รายการที่ {index + 1}</div>
                        <button
                          type="button"
                          className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/70 hover:bg-white/10"
                          onClick={() => {
                            setBulkRows((prev) => prev.map((item, i) => (i === index ? emptyDraft() : item)))
                          }}
                        >
                          ล้างแถวนี้
                        </button>
                      </div>
                      <ProductFormFields
                        draft={row}
                        categories={categories}
                        onChange={(next) => setBulkRows((prev) => prev.map((item, i) => (i === index ? next : item)))}
                        rules={ruleSettings}
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap justify-end gap-2 border-t border-[color:var(--color-border)] px-6 py-4">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  onClick={() => setBulkCreating(false)}
                  type="button"
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
                  onClick={handleBulkCreate}
                  type="button"
                  disabled={bulkSaving}
                >
                  {bulkSaving ? 'กำลังบันทึก...' : 'บันทึกทั้งหมด'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {editing ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="card flex max-h-[calc(100vh-2rem)] w-full max-w-3xl flex-col rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
                <div className="text-sm font-semibold">แก้ไขสินค้า {editing.sku}</div>
                <button onClick={() => setEditing(null)} className="text-white/60 hover:text-white" type="button">
                  ✕
                </button>
              </div>
              <div className="space-y-4 overflow-y-auto p-6">
                <ProductFormFields
                  draft={editingDraft}
                  categories={categories}
                  onChange={setEditingDraft}
                  rules={ruleSettings}
                  showSku={false}
                />
              </div>
              <div className="flex justify-end gap-2 border-t border-[color:var(--color-border)] px-6 py-4">
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
                  onClick={handleUpdate}
                >
                  บันทึกการแก้ไข
                </button>
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
                <th className="px-4 py-2">รหัสสินค้า</th>
                <th className="px-4 py-2">ชื่อสินค้า</th>
                <th className="px-4 py-2">หมวดหมู่</th>
                <th className="px-4 py-2">ประเภท</th>
                <th className="px-4 py-2">สต็อก</th>
                <th className="px-4 py-2">ราคา</th>
                <th className="px-4 py-2">สถานะ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {busy && items.length === 0
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={`s_${i}`}>
                      <td className="px-4 py-3" colSpan={canManage ? 8 : 7}>
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
                    <div className="text-white/90">{productDisplayName(p)}</div>
                  </td>
                  <td className="px-4 py-2 text-white/80">{categoryLabel(p)}</td>
                  <td className="px-4 py-2 text-white/60">{p.type || '-'}</td>
                  <td className="px-4 py-2">
                    <div className="font-semibold text-white/90">{p.stock_qty}</div>
                    <div className="mt-0.5 text-xs text-white/60">
                      <span className="text-white/50">ควรมี</span>{' '}
                      <span className="text-white/80">{Number(p.max_stock) > 0 ? p.max_stock : '—'}</span>
                      <span className="text-white/40"> • </span>
                      <span className="text-white/50">ขั้นต่ำ</span>{' '}
                      <span className="text-white/80">{p.min_stock}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2 text-white/70">
                    <div className="text-xs">ต้นทุน: <span className="text-white/90">{formatTHB(p.cost_price)}</span></div>
                    <div className="text-xs">ขาย: <span className="text-white/90">{p.selling_price == null ? '-' : formatTHB(p.selling_price)}</span></div>
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
                        {canManage && isDeletedProduct(p) ? (
                          <button
                            className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                            type="button"
                            onClick={async () => {
                              await restoreProduct(p.sku)
                              await refreshList()
                            }}
                          >
                            กู้คืน
                          </button>
                        ) : null}
                        {canManage && !isDeletedProduct(p) ? (
                          <button
                            className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                            type="button"
                            onClick={() => openEdit(p)}
                          >
                            แก้ไข
                          </button>
                        ) : null}
                        {canAdjust && !isDeletedProduct(p) ? (
                          <button
                            className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                            type="button"
                            onClick={async () => {
                              const nextQtyRaw = await showPrompt(`ตั้งยอดสต็อกสำหรับ ${p.sku}`, String(p.stock_qty || '0'))
                              if (nextQtyRaw == null) return
                              const nextQty = Number(nextQtyRaw)
                              if (!Number.isFinite(nextQty) || nextQty < 0) {
                                await showAlert('จำนวนไม่ถูกต้อง')
                                return
                              }
                              const reason = (await showPrompt('หมายเหตุ (ไม่บังคับ)')) || ''
                              try {
                                const updated = await adjustStock(p.sku, { qty: nextQty, type: 'ADJUST', reason })
                                setItems((prev) => prev.map((x) => (x.sku === p.sku ? updated : x)))
                              } catch (e: any) {
                                await showAlert(e?.response?.data?.detail || 'ตั้งยอดไม่สำเร็จ')
                              }
                            }}
                          >
                            ตั้งยอด
                          </button>
                        ) : null}
                        {canManage && !isDeletedProduct(p) ? (
                          <button
                            className="rounded border border-red-500/30 px-2 py-1 text-xs text-red-200 hover:bg-red-500/10"
                            type="button"
                            onClick={async () => {
                              const ok = await showConfirm(`ยืนยันลบสินค้า ${p.sku}?`)
                              if (!ok) return
                              try {
                                const reason = (await showPrompt('เหตุผลในการลบ (ไม่บังคับ)')) || ''
                                await deleteProduct(p.sku, reason)
                                await refreshList()
                              } catch {
                                await showAlert('ลบสินค้าไม่สำเร็จ')
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
                  <td className="px-4 py-8 text-sm text-white/60" colSpan={canManage ? 8 : 7}>
                    ไม่พบสินค้าในตัวกรองนี้
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
