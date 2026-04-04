import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAuthStore } from '../../store/authStore'
import { useAlert, useConfirm } from '../../components/ui/ConfirmDialog'
import {
  archivePriceRecord,
  createPriceRecord,
  dropdownProducts,
  dropdownSuppliers,
  listPriceRecords,
  updatePriceRecord,
  type DropdownProduct,
  type DropdownSupplier,
  type PriceRecordItem,
  type PriceRecordPayload,
} from '../../services/priceRecords'

const SOURCE_TYPES = [
  { value: 'manual_entry', th: 'กรอกเอง', en: 'Manual entry' },
  { value: 'actual_purchase', th: 'ซื้อจริง', en: 'Actual purchase' },
  { value: 'supplier_quote', th: 'ใบเสนอราคา', en: 'Supplier quote' },
  { value: 'phone_inquiry', th: 'สอบถามทางโทรศัพท์', en: 'Phone inquiry' },
  { value: 'chat_confirmation', th: 'ยืนยันทางแชต', en: 'Chat confirmation' },
  { value: 'imported', th: 'นำเข้า', en: 'Imported' },
  { value: 'estimated', th: 'ประมาณการ', en: 'Estimated' },
]

const STATUS_OPTIONS = [
  { value: 'draft', th: 'แบบร่าง', en: 'Draft' },
  { value: 'pending_verify', th: 'รอตรวจสอบ', en: 'Pending verify' },
  { value: 'active', th: 'ใช้งาน', en: 'Active' },
  { value: 'inactive', th: 'ปิดใช้งาน', en: 'Inactive' },
]

function fieldClass() {
  return 'input-surface w-full rounded border border-[color:var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]'
}

function statusBadge(status: string) {
  const base = 'inline-block rounded-full px-2 py-0.5 text-xs font-medium'
  switch (status) {
    case 'active':
      return `${base} bg-green-500/20 text-green-400`
    case 'draft':
      return `${base} bg-yellow-500/20 text-yellow-400`
    case 'pending_verify':
      return `${base} bg-blue-500/20 text-blue-400`
    case 'inactive':
    case 'archived':
    case 'expired':
      return `${base} bg-gray-500/20 text-gray-400`
    default:
      return `${base} bg-gray-500/20 text-gray-400`
  }
}

function fmt(v: string | number | null | undefined): string {
  if (v == null || v === '' || v === '0' || v === '0.000000') return '-'
  const num = typeof v === 'string' ? parseFloat(v) : v
  if (isNaN(num) || num === 0) return '-'
  return num.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ---------------------------------------------------------------------------
// Searchable dropdown component
// ---------------------------------------------------------------------------

interface SearchDropdownProps<T> {
  label: string
  value: string
  onSelect: (item: T) => void
  search: (q: string) => Promise<T[]>
  renderItem: (item: T) => string
  getId: (item: T) => string
  displayValue: string
  placeholder?: string
  autoLoad?: boolean
  menuMode?: 'overlay' | 'push'
}

function SearchDropdown<T>({ label, value, onSelect, search, renderItem, getId, displayValue, placeholder, autoLoad, menuMode = 'overlay' }: SearchDropdownProps<T>) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<T[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Auto-load items when component mounts (e.g. when form opens)
  useEffect(() => {
    if (autoLoad && !loaded) {
      setLoading(true)
      search('')
        .then((result) => { setItems(Array.isArray(result) ? result : []); setLoaded(true) })
        .catch(() => setItems([]))
        .finally(() => setLoading(false))
    }
  }, [autoLoad]) // eslint-disable-line react-hooks/exhaustive-deps

  function doSearch(q: string) {
    setLoading(true)
    search(q)
      .then((result) => { setItems(Array.isArray(result) ? result : []); setLoaded(true) })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }

  function handleOpen() {
    setOpen(true)
    setQuery('')
    if (!loaded) doSearch('')
    // Focus input after open
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  function handleInputChange(q: string) {
    setQuery(q)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(q), 250)
  }

  const hasValue = Boolean(value)
  const dropdownClassName = menuMode === 'push'
    ? 'relative mt-2 max-h-56 w-full overflow-auto rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] text-[color:var(--color-fg)] shadow-xl'
    : 'absolute z-50 mt-1 max-h-56 w-full overflow-auto rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] text-[color:var(--color-fg)] shadow-xl'

  return (
    <div ref={ref} className="relative">
      <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{label}</label>

      {/* Trigger button — shows selected value or empty prompt */}
      {!open ? (
        <button
          type="button"
          className={`${fieldClass()} flex items-center justify-between gap-2 text-left text-[color:var(--color-fg)]`}
          onClick={handleOpen}
        >
          <span className={`truncate ${hasValue ? 'text-[color:var(--color-fg)]' : 'text-[color:var(--color-muted)]'}`}>
            {hasValue ? (displayValue || value) : (placeholder || 'เลือก...')}
          </span>
          <span className="shrink-0 text-[color:var(--color-muted)] text-xs">
            {loading ? '⏳' : '▼'}
          </span>
        </button>
      ) : (
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            className={`${fieldClass()} pr-8 text-[color:var(--color-fg)]`}
            placeholder="พิมพ์เพื่อค้นหา..."
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            autoFocus
          />
          {query && (
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-[color:var(--color-muted)] hover:text-[color:var(--color-fg)]"
              onClick={() => { setQuery(''); doSearch('') }}
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* Dropdown list */}
      {open && (
        <div className={dropdownClassName}>
          {/* Currently selected shown at top if exists */}
          {hasValue && !query && (
            <div className="border-b border-[color:var(--color-border)] px-3 py-2 text-xs text-[color:var(--color-primary)] truncate">
              ✓ {displayValue}
            </div>
          )}
          {loading && <div className="px-3 py-2 text-xs text-[color:var(--color-muted)]">กำลังโหลด...</div>}
          {!loading && items.length === 0 && (
            <div className="px-3 py-2 text-xs text-[color:var(--color-muted)]">
              {query ? `ไม่พบ "${query}"` : 'ไม่มีข้อมูล'}
            </div>
          )}
          {items.map((item) => (
            <button
              key={getId(item)}
              type="button"
              className={`block w-full px-3 py-2 text-left text-sm text-[color:var(--color-fg)] truncate transition-colors ${
                getId(item) === value
                  ? 'bg-[color:var(--color-primary)]/20 text-[color:var(--color-primary)]'
                  : 'hover:bg-[color:var(--color-primary)]/10'
              }`}
              onClick={() => { onSelect(item); setOpen(false); setQuery('') }}
            >
              {renderItem(item)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export function PriceRecordsPage() {
  const { t, i18n } = useTranslation()
  const isEn = i18n.language === 'en'
  const role = useAuthStore((s) => s.role)
  const canManage = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const canDelete = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const showAlert = useAlert()
  const showConfirm = useConfirm()

  const [busy, setBusy] = useState(true)
  const [saving, setSaving] = useState(false)
  const [items, setItems] = useState<PriceRecordItem[]>([])
  const [total, setTotal] = useState(0)
  const [filterProductId, setFilterProductId] = useState('')
  const [filterSupplierId, setFilterSupplierId] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  // Form state
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [selectedProduct, setSelectedProduct] = useState<DropdownProduct | null>(null)
  const [selectedSupplier, setSelectedSupplier] = useState<DropdownSupplier | null>(null)
  const [form, setForm] = useState({
    source_type: 'manual_entry',
    status: 'active',
    original_currency: 'THB',
    original_amount: '',
    vat_percent: '7',
    shipping_cost: '',
    fuel_cost: '',
    labor_cost: '',
    utility_cost: '',
    supplier_fee: '',
    discount: '',
    quantity_min: '1',
    quantity_max: '',
    delivery_mode: 'standard',
    area_scope: 'global',
    note: '',
  })

  function resetForm() {
    setSelectedProduct(null)
    setSelectedSupplier(null)
    setEditingId(null)
    setForm({
      source_type: 'manual_entry',
      status: 'active',
      original_currency: 'THB',
      original_amount: '',
      vat_percent: '7',
      shipping_cost: '',
      fuel_cost: '',
      labor_cost: '',
      utility_cost: '',
      supplier_fee: '',
      discount: '',
      quantity_min: '1',
      quantity_max: '',
      delivery_mode: 'standard',
      area_scope: 'global',
      note: '',
    })
  }

  async function loadRecords() {
    try {
      const res = await listPriceRecords({
        product_id: filterProductId || undefined,
        supplier_id: filterSupplierId || undefined,
        status: filterStatus || undefined,
        limit: 100,
      })
      setItems(Array.isArray(res?.items) ? res.items : [])
      setTotal(res?.total ?? 0)
    } catch (err: any) {
      await showAlert(err?.response?.data?.detail || err?.message || 'โหลดข้อมูลไม่สำเร็จ')
    }
  }

  useEffect(() => {
    setBusy(true)
    loadRecords().finally(() => setBusy(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterProductId, filterSupplierId, filterStatus])

  function openCreate() {
    resetForm()
    setShowForm(true)
  }

  function openEdit(record: PriceRecordItem) {
    setEditingId(record.id)
    setSelectedProduct({ id: record.product_id, sku: record.product_sku || '', name_th: record.product_name_th || '', name_en: '', unit: '' })
    setSelectedSupplier({ id: record.supplier_id, code: '', name: record.supplier_name || '' })
    setForm({
      source_type: record.source_type,
      status: record.status,
      original_currency: record.original_currency,
      original_amount: record.original_amount,
      vat_percent: record.vat_percent,
      shipping_cost: record.shipping_cost !== '0.000000' ? record.shipping_cost : '',
      fuel_cost: record.fuel_cost !== '0.000000' ? record.fuel_cost : '',
      labor_cost: record.labor_cost !== '0.000000' ? record.labor_cost : '',
      utility_cost: record.utility_cost !== '0.000000' ? record.utility_cost : '',
      supplier_fee: record.supplier_fee !== '0.000000' ? record.supplier_fee : '',
      discount: record.discount !== '0.000000' ? record.discount : '',
      quantity_min: String(record.quantity_min),
      quantity_max: record.quantity_max != null ? String(record.quantity_max) : '',
      delivery_mode: record.delivery_mode,
      area_scope: record.area_scope,
      note: record.note || '',
    })
    setShowForm(true)
  }

  async function handleSave() {
    if (!selectedProduct) {
      await showAlert(isEn ? 'Please select a product' : 'กรุณาเลือกสินค้า')
      return
    }
    if (!selectedSupplier) {
      await showAlert(isEn ? 'Please select a supplier' : 'กรุณาเลือกร้านค้า')
      return
    }
    const amount = parseFloat(form.original_amount)
    if (isNaN(amount) || amount <= 0) {
      await showAlert(isEn ? 'Please enter a valid price amount' : 'กรุณากรอกราคาให้ถูกต้อง')
      return
    }

    setSaving(true)
    try {
      const payload: PriceRecordPayload = {
        product_id: selectedProduct.id,
        supplier_id: selectedSupplier.id,
        source_type: form.source_type,
        status: form.status,
        original_currency: form.original_currency,
        original_amount: amount,
        exchange_rate: 1,
        vat_percent: parseFloat(form.vat_percent) || 0,
        shipping_cost: parseFloat(form.shipping_cost) || 0,
        fuel_cost: parseFloat(form.fuel_cost) || 0,
        labor_cost: parseFloat(form.labor_cost) || 0,
        utility_cost: parseFloat(form.utility_cost) || 0,
        supplier_fee: parseFloat(form.supplier_fee) || 0,
        discount: parseFloat(form.discount) || 0,
        quantity_min: parseInt(form.quantity_min, 10) || 1,
        quantity_max: form.quantity_max ? parseInt(form.quantity_max, 10) : null,
        delivery_mode: form.delivery_mode,
        area_scope: form.area_scope,
        note: form.note,
      }

      if (editingId) {
        await updatePriceRecord(editingId, payload)
      } else {
        await createPriceRecord(payload)
      }
      setShowForm(false)
      resetForm()
      await loadRecords()
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'บันทึกไม่สำเร็จ'
      await showAlert(detail === 'active_price_conflict'
        ? (isEn ? 'There is already an active price for this product + supplier combination in the same time range' : 'มีราคาที่ใช้งานอยู่แล้วสำหรับสินค้า+ร้านค้านี้ในช่วงเวลาเดียวกัน')
        : detail)
    } finally {
      setSaving(false)
    }
  }

  async function handleArchive(id: string) {
    const confirmed = await showConfirm(isEn ? 'Archive this price record?' : 'ต้องการเก็บรายการราคานี้หรือไม่?')
    if (!confirmed) return
    try {
      await archivePriceRecord(id)
      await loadRecords()
    } catch (err: any) {
      await showAlert(err?.response?.data?.detail || err?.message || 'ลบไม่สำเร็จ')
    }
  }

  // Compute a quick total preview for the form
  const previewBase = parseFloat(form.original_amount) || 0
  const previewVatPct = parseFloat(form.vat_percent) || 0
  const previewVat = previewBase * previewVatPct / 100
  const previewTotal = previewBase + previewVat
    + (parseFloat(form.shipping_cost) || 0)
    + (parseFloat(form.fuel_cost) || 0)
    + (parseFloat(form.labor_cost) || 0)
    + (parseFloat(form.utility_cost) || 0)
    + (parseFloat(form.supplier_fee) || 0)
    - (parseFloat(form.discount) || 0)

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold">{isEn ? 'Price Records' : 'บันทึกราคาสินค้า'}</h1>
          <p className="text-xs text-[color:var(--color-muted)]">
            {isEn
              ? 'Record purchase prices from different suppliers for comparison'
              : 'บันทึกราคาซื้อจากร้านค้าต่าง ๆ เพื่อใช้เปรียบเทียบ'}
          </p>
        </div>
        {canManage && (
          <button
            className="rounded-lg bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black shadow hover:opacity-90"
            onClick={openCreate}
          >
            {isEn ? '+ Add Price' : '+ เพิ่มราคา'}
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="card surface-panel rounded-xl border p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <SearchDropdown<DropdownProduct>
            label={isEn ? 'Filter by product' : 'กรองตามสินค้า'}
            value={filterProductId}
            displayValue={filterProductId ? `${items.find(i => i.product_id === filterProductId)?.product_sku || ''} ${items.find(i => i.product_id === filterProductId)?.product_name_th || ''}` : ''}
            onSelect={(p) => setFilterProductId(p.id)}
            search={dropdownProducts}
            renderItem={(p) => `${p.sku} — ${p.name_th || p.name_en}`}
            getId={(p) => p.id}
            placeholder={isEn ? 'Search product...' : 'ค้นหาสินค้า...'}
            menuMode="push"
          />
          <SearchDropdown<DropdownSupplier>
            label={isEn ? 'Filter by supplier' : 'กรองตามร้านค้า'}
            value={filterSupplierId}
            displayValue={filterSupplierId ? items.find(i => i.supplier_id === filterSupplierId)?.supplier_name || '' : ''}
            onSelect={(s) => setFilterSupplierId(s.id)}
            search={dropdownSuppliers}
            renderItem={(s) => s.code ? `${s.code} — ${s.name}` : s.name}
            getId={(s) => s.id}
            placeholder={isEn ? 'Search supplier...' : 'ค้นหาร้านค้า...'}
            menuMode="push"
          />
          <div>
            <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Filter by status' : 'กรองตามสถานะ'}</label>
            <select
              className={fieldClass()}
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
            >
              <option value="">{isEn ? 'All statuses' : 'ทุกสถานะ'}</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>{isEn ? s.en : s.th}</option>
              ))}
            </select>
          </div>
        </div>
        {(filterProductId || filterSupplierId || filterStatus) && (
          <button
            className="mt-2 text-xs text-[color:var(--color-primary)] hover:underline"
            onClick={() => { setFilterProductId(''); setFilterSupplierId(''); setFilterStatus('') }}
          >
            {isEn ? 'Clear filters' : 'ล้างตัวกรอง'}
          </button>
        )}
      </div>

      {/* Create/Edit Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/60 pt-10 pb-10">
          <div className="card surface-panel w-full max-w-2xl rounded-xl border p-6 shadow-xl">
            <h2 className="mb-4 text-base font-semibold">
              {editingId
                ? (isEn ? 'Edit Price Record' : 'แก้ไขรายการราคา')
                : (isEn ? 'Add Price Record' : 'เพิ่มรายการราคา')}
            </h2>

            <div className="space-y-4">
              {/* Product & Supplier selection */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <SearchDropdown<DropdownProduct>
                  label={isEn ? 'Product *' : 'สินค้า *'}
                  value={selectedProduct?.id || ''}
                  displayValue={selectedProduct ? `${selectedProduct.sku} — ${selectedProduct.name_th}` : ''}
                  onSelect={setSelectedProduct}
                  search={dropdownProducts}
                  renderItem={(p) => p.unit ? `${p.sku} — ${p.name_th || p.name_en} (${p.unit})` : `${p.sku} — ${p.name_th || p.name_en}`}
                  getId={(p) => p.id}
                  placeholder={isEn ? 'Click to browse or type to search...' : 'คลิกเลือก หรือพิมพ์เพื่อค้นหา...'}
                  autoLoad
                />
                <SearchDropdown<DropdownSupplier>
                  label={isEn ? 'Supplier *' : 'ร้านค้า *'}
                  value={selectedSupplier?.id || ''}
                  displayValue={selectedSupplier ? (selectedSupplier.code ? `${selectedSupplier.code} — ${selectedSupplier.name}` : selectedSupplier.name) : ''}
                  onSelect={setSelectedSupplier}
                  search={dropdownSuppliers}
                  renderItem={(s) => s.code ? `${s.code} — ${s.name}` : s.name}
                  getId={(s) => s.id}
                  placeholder={isEn ? 'Click to browse or type to search...' : 'คลิกเลือก หรือพิมพ์เพื่อค้นหา...'}
                  autoLoad
                />
              </div>

              {/* Main price fields */}
              <div className="rounded-lg border border-[color:var(--color-border)] p-4">
                <h3 className="mb-3 text-sm font-medium">{isEn ? 'Price Information' : 'ข้อมูลราคา'}</h3>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="col-span-2">
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Base price (THB) *' : 'ราคาฐาน (บาท) *'}</label>
                    <input
                      type="number"
                      className={fieldClass()}
                      value={form.original_amount}
                      onChange={(e) => setForm({ ...form, original_amount: e.target.value })}
                      placeholder="0.00"
                      min="0"
                      step="0.01"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'VAT %' : 'ภาษี %'}</label>
                    <input
                      type="number"
                      className={fieldClass()}
                      value={form.vat_percent}
                      onChange={(e) => setForm({ ...form, vat_percent: e.target.value })}
                      placeholder="7"
                      min="0"
                      max="100"
                      step="0.01"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Discount' : 'ส่วนลด'}</label>
                    <input
                      type="number"
                      className={fieldClass()}
                      value={form.discount}
                      onChange={(e) => setForm({ ...form, discount: e.target.value })}
                      placeholder="0"
                      min="0"
                      step="0.01"
                    />
                  </div>
                </div>
              </div>

              {/* Extra costs */}
              <div className="rounded-lg border border-[color:var(--color-border)] p-4">
                <h3 className="mb-3 text-sm font-medium">{isEn ? 'Additional Costs' : 'ค่าใช้จ่ายเพิ่มเติม'}</h3>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Shipping' : 'ค่าขนส่ง'}</label>
                    <input type="number" className={fieldClass()} value={form.shipping_cost} onChange={(e) => setForm({ ...form, shipping_cost: e.target.value })} placeholder="0" min="0" step="0.01" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Fuel' : 'ค่าน้ำมัน'}</label>
                    <input type="number" className={fieldClass()} value={form.fuel_cost} onChange={(e) => setForm({ ...form, fuel_cost: e.target.value })} placeholder="0" min="0" step="0.01" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Labor' : 'ค่าแรง'}</label>
                    <input type="number" className={fieldClass()} value={form.labor_cost} onChange={(e) => setForm({ ...form, labor_cost: e.target.value })} placeholder="0" min="0" step="0.01" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Utility' : 'ค่าสาธารณูปโภค'}</label>
                    <input type="number" className={fieldClass()} value={form.utility_cost} onChange={(e) => setForm({ ...form, utility_cost: e.target.value })} placeholder="0" min="0" step="0.01" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Supplier fee' : 'ค่าธรรมเนียม'}</label>
                    <input type="number" className={fieldClass()} value={form.supplier_fee} onChange={(e) => setForm({ ...form, supplier_fee: e.target.value })} placeholder="0" min="0" step="0.01" />
                  </div>
                </div>
              </div>

              {/* Options row */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Source type' : 'แหล่งที่มา'}</label>
                  <select className={fieldClass()} value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
                    {SOURCE_TYPES.map((s) => (
                      <option key={s.value} value={s.value}>{isEn ? s.en : s.th}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Status' : 'สถานะ'}</label>
                  <select className={fieldClass()} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s.value} value={s.value}>{isEn ? s.en : s.th}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Min qty' : 'จำนวนขั้นต่ำ'}</label>
                  <input type="number" className={fieldClass()} value={form.quantity_min} onChange={(e) => setForm({ ...form, quantity_min: e.target.value })} min="1" step="1" />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Max qty' : 'จำนวนสูงสุด'}</label>
                  <input type="number" className={fieldClass()} value={form.quantity_max} onChange={(e) => setForm({ ...form, quantity_max: e.target.value })} placeholder={isEn ? 'No limit' : 'ไม่จำกัด'} min="1" step="1" />
                </div>
              </div>

              {/* Note */}
              <div>
                <label className="mb-1 block text-xs text-[color:var(--color-muted)]">{isEn ? 'Note' : 'หมายเหตุ'}</label>
                <textarea className={`${fieldClass()} min-h-[60px]`} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
              </div>

              {/* Preview total */}
              <div className="rounded-lg bg-[color:var(--color-primary)]/10 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{isEn ? 'Estimated total cost' : 'ต้นทุนรวมโดยประมาณ'}</span>
                  <span className="text-lg font-bold text-[color:var(--color-primary)]">
                    ฿{previewTotal > 0 ? previewTotal.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}
                  </span>
                </div>
                {previewBase > 0 && (
                  <div className="mt-1 text-xs text-[color:var(--color-muted)]">
                    {isEn ? 'Base' : 'ราคาฐาน'} ฿{previewBase.toLocaleString('th-TH', { minimumFractionDigits: 2 })}
                    {previewVat > 0 && ` + VAT ฿${previewVat.toLocaleString('th-TH', { minimumFractionDigits: 2 })}`}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  className="rounded-lg border border-[color:var(--color-border)] px-4 py-2 text-sm hover:bg-white/5"
                  onClick={() => { setShowForm(false); resetForm() }}
                >
                  {isEn ? 'Cancel' : 'ยกเลิก'}
                </button>
                <button
                  className="rounded-lg bg-[color:var(--color-primary)] px-4 py-2 text-sm font-medium text-black shadow hover:opacity-90 disabled:opacity-50"
                  disabled={saving}
                  onClick={handleSave}
                >
                  {saving
                    ? (isEn ? 'Saving...' : 'กำลังบันทึก...')
                    : editingId
                      ? (isEn ? 'Update' : 'อัปเดต')
                      : (isEn ? 'Save' : 'บันทึก')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Data table */}
      <div className="card surface-panel overflow-hidden rounded-xl border">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[color:var(--color-border)] text-left text-xs text-[color:var(--color-muted)]">
                <th className="px-4 py-3 font-medium">{isEn ? 'Product' : 'สินค้า'}</th>
                <th className="px-4 py-3 font-medium">{isEn ? 'Supplier' : 'ร้านค้า'}</th>
                <th className="px-4 py-3 font-medium text-right">{isEn ? 'Base price' : 'ราคาฐาน'}</th>
                <th className="px-4 py-3 font-medium text-right">{isEn ? 'Total cost' : 'ต้นทุนรวม'}</th>
                <th className="px-4 py-3 font-medium">{isEn ? 'Source' : 'แหล่งที่มา'}</th>
                <th className="px-4 py-3 font-medium">{isEn ? 'Status' : 'สถานะ'}</th>
                <th className="px-4 py-3 font-medium">{isEn ? 'Updated' : 'อัปเดต'}</th>
                {canManage && <th className="px-4 py-3 font-medium"></th>}
              </tr>
            </thead>
            <tbody>
              {busy ? (
                <tr>
                  <td colSpan={canManage ? 8 : 7} className="px-4 py-8 text-center text-sm text-[color:var(--color-muted)]">
                    {isEn ? 'Loading...' : 'กำลังโหลด...'}
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={canManage ? 8 : 7} className="px-4 py-12 text-center">
                    <div className="text-[color:var(--color-muted)]">
                      <div className="mb-2 text-3xl">📋</div>
                      <div className="text-sm font-medium">{isEn ? 'No price records yet' : 'ยังไม่มีรายการราคา'}</div>
                      <div className="mt-1 text-xs">
                        {isEn
                          ? 'Click "+ Add Price" to record a purchase price from a supplier'
                          : 'กด "+ เพิ่มราคา" เพื่อบันทึกราคาซื้อจากร้านค้า'}
                      </div>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((record) => {
                  const sourceLabel = SOURCE_TYPES.find(s => s.value === record.source_type)
                  const statusLabel = STATUS_OPTIONS.find(s => s.value === record.status)
                  return (
                    <tr key={record.id} className="border-b border-[color:var(--color-border)] last:border-b-0 hover:bg-white/3">
                      <td className="px-4 py-3">
                        <div className="font-medium">{record.product_name_th || record.product_sku}</div>
                        <div className="text-xs text-[color:var(--color-muted)]">{record.product_sku}</div>
                      </td>
                      <td className="px-4 py-3 text-sm">{record.supplier_name}</td>
                      <td className="px-4 py-3 text-right font-mono text-sm">{fmt(record.normalized_amount)}</td>
                      <td className="px-4 py-3 text-right font-mono text-sm font-semibold">{fmt(record.final_total_cost)}</td>
                      <td className="px-4 py-3 text-xs">{sourceLabel ? (isEn ? sourceLabel.en : sourceLabel.th) : record.source_type}</td>
                      <td className="px-4 py-3">
                        <span className={statusBadge(record.status)}>
                          {statusLabel ? (isEn ? statusLabel.en : statusLabel.th) : record.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-[color:var(--color-muted)]">
                        {record.updated_at ? new Date(record.updated_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: '2-digit' }) : '-'}
                      </td>
                      {canManage && (
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-1">
                            <button
                              className="rounded px-2 py-1 text-xs text-[color:var(--color-primary)] hover:bg-[color:var(--color-primary)]/10"
                              onClick={() => openEdit(record)}
                            >
                              {isEn ? 'Edit' : 'แก้ไข'}
                            </button>
                            {canDelete && (
                              <button
                                className="rounded px-2 py-1 text-xs text-red-400 hover:bg-red-400/10"
                                onClick={() => handleArchive(record.id)}
                              >
                                {isEn ? 'Archive' : 'เก็บ'}
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        {!busy && total > 0 && (
          <div className="border-t border-[color:var(--color-border)] px-4 py-2 text-xs text-[color:var(--color-muted)]">
            {isEn ? `Showing ${items.length} of ${total} records` : `แสดง ${items.length} จาก ${total} รายการ`}
          </div>
        )}
      </div>
    </div>
  )
}
