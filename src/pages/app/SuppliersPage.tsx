import { useEffect, useState } from 'react'

import type { AttachmentItem, Supplier, SupplierProposal } from '../../types/models'
import { useAuthStore } from '../../store/authStore'
import {
  approveSupplierProposal,
  archiveSupplier,
  archiveSupplierAttachment,
  createSupplier,
  getSupplier,
  listSupplierProposals,
  listSuppliers,
  rejectSupplierProposal,
  updateSupplier,
  uploadSupplierAttachment,
} from '../../services/suppliers'

type SupplierDraft = {
  name: string
  phone: string
  line_id: string
  facebook_url: string
  website_url: string
  address: string
  pickup_notes: string
  source_details: string
  purchase_history_notes: string
  reliability_note: string
  status: string
  is_verified: boolean
}

function emptyDraft(): SupplierDraft {
  return {
    name: '',
    phone: '',
    line_id: '',
    facebook_url: '',
    website_url: '',
    address: '',
    pickup_notes: '',
    source_details: '',
    purchase_history_notes: '',
    reliability_note: '',
    status: 'ACTIVE',
    is_verified: false,
  }
}

function isProposal(value: Supplier | SupplierProposal): value is SupplierProposal {
  return 'action' in value && 'requires_dev_review' in value
}

function fieldClassName(multiline = false) {
  return [
    'w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]',
    multiline ? 'min-h-[92px]' : '',
  ].join(' ')
}

export function SuppliersPage() {
  const role = useAuthStore((s) => s.role)
  const canManage = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const canVerify = role === 'OWNER' || role === 'DEV'

  const [busy, setBusy] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<Supplier[]>([])
  const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null)
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null)
  const [draft, setDraft] = useState<SupplierDraft>(emptyDraft())
  const [creating, setCreating] = useState(false)
  const [proposals, setProposals] = useState<SupplierProposal[]>([])
  const [attachmentClassification, setAttachmentClassification] = useState('supplier_profile')
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null)

  async function loadSuppliers() {
    const res = await listSuppliers({ q: query.trim() || undefined, include_archived: canManage, limit: 100, offset: 0 })
    setItems(Array.isArray(res.items) ? res.items : [])
    if (selectedSupplierId) {
      const detail = await getSupplier(selectedSupplierId)
      setSelectedSupplier(detail)
      setDraft({
        name: detail.name,
        phone: detail.phone || '',
        line_id: detail.line_id || '',
        facebook_url: detail.facebook_url || '',
        website_url: detail.website_url || '',
        address: detail.address || '',
        pickup_notes: detail.pickup_notes || '',
        source_details: detail.source_details || '',
        purchase_history_notes: detail.purchase_history_notes || '',
        reliability_note: detail.reliability_note || '',
        status: detail.status || 'ACTIVE',
        is_verified: Boolean(detail.is_verified),
      })
    }
    if (canManage) {
      setProposals(await listSupplierProposals('PENDING'))
    }
  }

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    loadSuppliers()
      .catch((error: any) => {
        if (!cancelled) setMessage(error?.response?.data?.detail || error?.message || 'โหลด supplier ไม่สำเร็จ')
      })
      .finally(() => {
        if (!cancelled) setBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [query, selectedSupplierId])

  function selectSupplier(supplier: Supplier) {
    setSelectedSupplierId(supplier.id)
    setSelectedSupplier(supplier)
    setCreating(false)
  }

  async function handleCreateOrUpdate() {
    if (!canManage) return
    const payload = {
      ...draft,
      contacts: [],
      links: [],
      pickup_points: [],
    }
    if (!draft.name.trim()) {
      window.alert('กรุณากรอกชื่อ supplier')
      return
    }
    setSaving(true)
    setMessage('')
    try {
      let result: Supplier | SupplierProposal
      if (creating || !selectedSupplierId) {
        result = await createSupplier(payload)
      } else {
        result = await updateSupplier(selectedSupplierId, payload)
      }
      if (isProposal(result)) {
        setMessage('บันทึกเป็น proposal แล้ว รอ Dev/Owner ตรวจสอบ')
        setCreating(false)
      } else {
        setSelectedSupplierId(result.id)
        setSelectedSupplier(result)
        setCreating(false)
        setMessage('บันทึก supplier สำเร็จ')
      }
      await loadSuppliers()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'บันทึก supplier ไม่สำเร็จ')
    } finally {
      setSaving(false)
    }
  }

  async function handleArchive() {
    if (!selectedSupplierId || !canManage) return
    const reason = window.prompt('เหตุผลในการ archive supplier') || ''
    if (!window.confirm('ยืนยัน archive supplier นี้?')) return
    try {
      const result = await archiveSupplier(selectedSupplierId, reason)
      setMessage(isProposal(result) ? 'สร้าง archive proposal แล้ว' : 'archive supplier สำเร็จ')
      await loadSuppliers()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'archive supplier ไม่สำเร็จ')
    }
  }

  async function handleUploadAttachment() {
    if (!selectedSupplierId || !attachmentFile) return
    try {
      await uploadSupplierAttachment(selectedSupplierId, attachmentFile, attachmentClassification)
      setAttachmentFile(null)
      setMessage('อัปโหลดไฟล์แนบแล้ว')
      const detail = await getSupplier(selectedSupplierId)
      setSelectedSupplier(detail)
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'อัปโหลดไฟล์แนบไม่สำเร็จ')
    }
  }

  async function handleArchiveAttachment(item: AttachmentItem) {
    if (!selectedSupplierId) return
    try {
      await archiveSupplierAttachment(selectedSupplierId, item.id)
      const detail = await getSupplier(selectedSupplierId)
      setSelectedSupplier(detail)
      setMessage('archive ไฟล์แนบแล้ว')
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'archive ไฟล์แนบไม่สำเร็จ')
    }
  }

  async function reviewProposal(item: SupplierProposal, action: 'approve' | 'reject') {
    const reviewNote = window.prompt(action === 'approve' ? 'หมายเหตุการอนุมัติ' : 'เหตุผลที่ปฏิเสธ') || ''
    try {
      if (action === 'approve') await approveSupplierProposal(item.id, reviewNote)
      else await rejectSupplierProposal(item.id, reviewNote)
      setMessage(action === 'approve' ? 'อนุมัติ proposal แล้ว' : 'ปฏิเสธ proposal แล้ว')
      await loadSuppliers()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'อัปเดต proposal ไม่สำเร็จ')
    }
  }

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Supplier Management</div>
            <div className="text-xs text-white/60">จัดการ supplier, reliability, proposal review และ file attachment แบบ additive จากระบบเดิม</div>
          </div>
          {canManage ? (
            <button
              className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
              type="button"
              onClick={() => {
                setCreating(true)
                setSelectedSupplierId(null)
                setSelectedSupplier(null)
                setDraft(emptyDraft())
              }}
            >
              สร้าง Supplier
            </button>
          ) : null}
        </div>
        {message ? <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 px-3 py-2 text-sm text-white/80">{message}</div> : null}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
            <input
              className={fieldClassName()}
              placeholder="ค้นหา supplier"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="mt-3 space-y-2">
              {busy && items.length === 0 ? <div className="text-sm text-white/60">กำลังโหลด...</div> : null}
              {items.map((supplier) => (
                <button
                  key={supplier.id}
                  type="button"
                  className={`w-full rounded border px-3 py-3 text-left text-sm ${selectedSupplierId === supplier.id ? 'border-[color:var(--color-primary)] bg-white/10' : 'border-[color:var(--color-border)] bg-black/20 hover:bg-white/5'}`}
                  onClick={() => selectSupplier(supplier)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold text-white/90">{supplier.name}</div>
                    <div className="rounded border border-[color:var(--color-border)] px-2 py-0.5 text-[11px] text-white/60">{supplier.status}</div>
                  </div>
                  <div className="mt-1 text-xs text-white/60">{supplier.code} • linked products {supplier.product_count}</div>
                  <div className="mt-1 text-xs text-white/50">score {supplier.reliability?.effective_score ?? 0}</div>
                </button>
              ))}
              {!busy && items.length === 0 ? <div className="text-sm text-white/60">ยังไม่พบ supplier</div> : null}
            </div>
          </div>

          {canManage ? (
            <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
              <div className="text-sm font-semibold">Pending Proposals</div>
              <div className="mt-3 space-y-2">
                {proposals.map((proposal) => (
                  <div key={proposal.id} className="rounded border border-[color:var(--color-border)] bg-black/20 p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-semibold text-white/90">{proposal.action}</div>
                      <div className="text-xs text-white/60">{proposal.status}</div>
                    </div>
                    <div className="mt-1 text-xs text-white/60">proposal #{proposal.id.slice(0, 8)}</div>
                    {canVerify ? (
                      <div className="mt-3 flex gap-2">
                        <button className="rounded border border-emerald-400/30 px-3 py-1.5 text-xs text-emerald-100 hover:bg-emerald-500/10" type="button" onClick={() => reviewProposal(proposal, 'approve')}>
                          Approve
                        </button>
                        <button className="rounded border border-red-400/30 px-3 py-1.5 text-xs text-red-100 hover:bg-red-500/10" type="button" onClick={() => reviewProposal(proposal, 'reject')}>
                          Reject
                        </button>
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-white/50">Admin สร้าง proposal ได้ แต่ approve/reject ไม่ได้</div>
                    )}
                  </div>
                ))}
                {proposals.length === 0 ? <div className="text-sm text-white/60">ไม่มี proposal ค้าง</div> : null}
              </div>
            </div>
          ) : null}
        </div>

        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          {!creating && !selectedSupplier ? (
            <div className="text-sm text-white/60">เลือก supplier จากด้านซ้าย หรือกดสร้าง supplier ใหม่</div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input className={fieldClassName()} placeholder="ชื่อร้าน / Supplier" value={draft.name} onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))} />
                <input className={fieldClassName()} placeholder="เบอร์โทร" value={draft.phone} onChange={(event) => setDraft((prev) => ({ ...prev, phone: event.target.value }))} />
                <input className={fieldClassName()} placeholder="LINE ID" value={draft.line_id} onChange={(event) => setDraft((prev) => ({ ...prev, line_id: event.target.value }))} />
                <input className={fieldClassName()} placeholder="Facebook URL" value={draft.facebook_url} onChange={(event) => setDraft((prev) => ({ ...prev, facebook_url: event.target.value }))} />
                <input className={fieldClassName()} placeholder="Website URL" value={draft.website_url} onChange={(event) => setDraft((prev) => ({ ...prev, website_url: event.target.value }))} />
                <select className={fieldClassName()} value={draft.status} onChange={(event) => setDraft((prev) => ({ ...prev, status: event.target.value }))}>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="INACTIVE">INACTIVE</option>
                  <option value="ARCHIVED">ARCHIVED</option>
                </select>
              </div>

              <textarea className={fieldClassName(true)} placeholder="ที่อยู่" value={draft.address} onChange={(event) => setDraft((prev) => ({ ...prev, address: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="จุดรับสินค้า / Pickup Notes" value={draft.pickup_notes} onChange={(event) => setDraft((prev) => ({ ...prev, pickup_notes: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="รายละเอียดแหล่งที่มา" value={draft.source_details} onChange={(event) => setDraft((prev) => ({ ...prev, source_details: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="ประวัติการซื้อ" value={draft.purchase_history_notes} onChange={(event) => setDraft((prev) => ({ ...prev, purchase_history_notes: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="หมายเหตุความน่าเชื่อถือ" value={draft.reliability_note} onChange={(event) => setDraft((prev) => ({ ...prev, reliability_note: event.target.value }))} />

              <label className="flex items-center gap-2 text-sm text-white/80">
                <input type="checkbox" checked={draft.is_verified} onChange={(event) => setDraft((prev) => ({ ...prev, is_verified: event.target.checked }))} />
                Verified supplier
              </label>

              {selectedSupplier?.reliability ? (
                <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-4">
                  <div className="text-sm font-semibold">Reliability Snapshot</div>
                  <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
                    <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3 text-sm">overall {selectedSupplier.reliability.overall_score}</div>
                    <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3 text-sm">auto {selectedSupplier.reliability.auto_score}</div>
                    <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3 text-sm">effective {selectedSupplier.reliability.effective_score}</div>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                    {selectedSupplier.reliability.breakdown.map((item) => (
                      <div key={item.metric_key} className="rounded border border-[color:var(--color-border)] bg-black/10 px-3 py-2 text-xs text-white/70">
                        {item.metric_key}: {item.score_value} / weight {item.weight}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {canManage ? (
                <div className="flex flex-wrap gap-2">
                  <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60" type="button" onClick={handleCreateOrUpdate} disabled={saving}>
                    {saving ? 'กำลังบันทึก...' : creating ? 'สร้าง Supplier' : 'บันทึกการแก้ไข'}
                  </button>
                  {!creating && selectedSupplierId ? (
                    <button className="rounded border border-red-400/30 px-4 py-2 text-sm text-red-100 hover:bg-red-500/10" type="button" onClick={handleArchive}>
                      Archive Supplier
                    </button>
                  ) : null}
                </div>
              ) : null}

              {!creating && selectedSupplier ? (
                <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-4">
                  <div className="text-sm font-semibold">Attachments</div>
                  {canManage ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <select className={fieldClassName()} value={attachmentClassification} onChange={(event) => setAttachmentClassification(event.target.value)}>
                        <option value="supplier_profile">supplier_profile</option>
                        <option value="quote_document">quote_document</option>
                        <option value="invoice">invoice</option>
                        <option value="chat_proof">chat_proof</option>
                        <option value="zip_archive">zip_archive</option>
                        <option value="other">other</option>
                      </select>
                      <input type="file" className={fieldClassName()} onChange={(event) => setAttachmentFile(event.target.files?.[0] || null)} />
                      <button className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10" type="button" onClick={handleUploadAttachment}>
                        Upload
                      </button>
                    </div>
                  ) : null}
                  <div className="mt-3 space-y-2">
                    {selectedSupplier.attachments.map((item) => (
                      <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-[color:var(--color-border)] bg-black/10 px-3 py-2 text-sm">
                        <div>
                          <div className="text-white/90">{item.original_filename}</div>
                          <div className="text-xs text-white/60">
                            {item.classification} • {item.content_type} • {(item.size_bytes / 1024 / 1024).toFixed(2)} MB • {item.malware_status}
                          </div>
                        </div>
                        {canManage ? (
                          <button className="rounded border border-[color:var(--color-border)] px-3 py-1.5 text-xs text-white/80 hover:bg-white/10" type="button" onClick={() => handleArchiveAttachment(item)}>
                            Archive
                          </button>
                        ) : null}
                      </div>
                    ))}
                    {selectedSupplier.attachments.length === 0 ? <div className="text-sm text-white/60">ยังไม่มีไฟล์แนบ</div> : null}
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
