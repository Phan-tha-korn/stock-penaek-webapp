import { useEffect, useState } from 'react'

import type { AttachmentItem, Supplier, SupplierProposal } from '../../types/models'
import { useAuthStore } from '../../store/authStore'
import { useAlert, useConfirm, usePrompt } from '../../components/ui/ConfirmDialog'
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
    'input-surface w-full rounded border border-[color:var(--color-border)] px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]',
    multiline ? 'min-h-[92px]' : '',
  ].join(' ')
}

function supplierStatusLabel(status: string) {
  switch (status) {
    case 'ACTIVE':
      return 'พร้อมใช้งาน'
    case 'INACTIVE':
      return 'ปิดใช้งาน'
    case 'ARCHIVED':
      return 'เก็บถาวร'
    default:
      return status
  }
}

function proposalActionLabel(action: string) {
  switch (action) {
    case 'create':
      return 'คำขอสร้างร้านค้า'
    case 'update':
      return 'คำขอแก้ไขร้านค้า'
    case 'archive':
      return 'คำขอเก็บร้านค้า'
    default:
      return action
  }
}

function attachmentTypeLabel(value: string) {
  switch (value) {
    case 'supplier_profile':
      return 'ข้อมูลร้านค้า'
    case 'quote_document':
      return 'ใบเสนอราคา'
    case 'invoice':
      return 'ใบแจ้งหนี้'
    case 'chat_proof':
      return 'หลักฐานแชต'
    case 'zip_archive':
      return 'ไฟล์ ZIP'
    case 'other':
      return 'อื่น ๆ'
    default:
      return value
  }
}

function reliabilityMetricLabel(metricKey: string) {
  switch (metricKey) {
    case 'price_competitiveness':
      return 'ความคุ้มค่าด้านราคา'
    case 'purchase_frequency':
      return 'ความถี่ในการสั่งซื้อ'
    case 'delivery_reliability':
      return 'ความสม่ำเสมอในการส่งของ'
    case 'data_completeness':
      return 'ความครบถ้วนของข้อมูล'
    case 'verification_confidence':
      return 'ความมั่นใจจากการตรวจสอบ'
    case 'dispute_reject':
      return 'ประวัติข้อพิพาทหรือการปฏิเสธ'
    default:
      return metricKey
  }
}

function malwareStatusLabel(value: string) {
  switch (value) {
    case 'clean':
      return 'ผ่านการตรวจไฟล์'
    case 'pending':
      return 'รอตรวจไฟล์'
    case 'flagged':
      return 'พบความเสี่ยง'
    case 'failed':
      return 'ตรวจไฟล์ไม่สำเร็จ'
    default:
      return value
  }
}

export function SuppliersPage() {
  const role = useAuthStore((s) => s.role)
  const canManage = role === 'ADMIN' || role === 'OWNER' || role === 'DEV'
  const canVerify = role === 'OWNER' || role === 'DEV'
  const showAlert = useAlert()
  const showConfirm = useConfirm()
  const showPrompt = usePrompt()

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
        if (!cancelled) setMessage(error?.response?.data?.detail || error?.message || 'โหลดข้อมูลร้านค้าไม่สำเร็จ')
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
      await showAlert('กรุณากรอกชื่อร้านค้า')
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
        setMessage('บันทึกเป็นคำขอแล้ว รอ Dev หรือ Owner ตรวจสอบ')
        setCreating(false)
      } else {
        setSelectedSupplierId(result.id)
        setSelectedSupplier(result)
        setCreating(false)
        setMessage('บันทึกร้านค้าเรียบร้อยแล้ว')
      }
      await loadSuppliers()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'บันทึกร้านค้าไม่สำเร็จ')
    } finally {
      setSaving(false)
    }
  }

  async function handleArchive() {
    if (!selectedSupplierId || !canManage) return
    const reason = (await showPrompt('ระบุเหตุผลที่ต้องการลบร้านค้านี้ออกจากรายการใช้งาน')) || ''
    if (!(await showConfirm('ยืนยันการลบร้านค้านี้ออกจากรายการใช้งานหรือไม่?'))) return
    try {
      const result = await archiveSupplier(selectedSupplierId, reason)
      setMessage(isProposal(result) ? 'สร้างคำขอลบร้านค้าออกจากรายการแล้ว' : 'ลบร้านค้าออกจากรายการเรียบร้อยแล้ว')
      await loadSuppliers()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'ลบร้านค้าออกจากรายการไม่สำเร็จ')
    }
  }

  async function handleUploadAttachment() {
    if (!selectedSupplierId || !attachmentFile) return
    try {
      await uploadSupplierAttachment(selectedSupplierId, attachmentFile, attachmentClassification)
      setAttachmentFile(null)
      setMessage('อัปโหลดไฟล์แนบเรียบร้อยแล้ว')
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
      setMessage('เก็บไฟล์แนบเรียบร้อยแล้ว')
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'เก็บไฟล์แนบไม่สำเร็จ')
    }
  }

  async function reviewProposal(item: SupplierProposal, action: 'approve' | 'reject') {
    const reviewNote = (await showPrompt(action === 'approve' ? 'หมายเหตุสำหรับการอนุมัติ' : 'เหตุผลที่ไม่อนุมัติ')) || ''
    try {
      if (action === 'approve') await approveSupplierProposal(item.id, reviewNote)
      else await rejectSupplierProposal(item.id, reviewNote)
      setMessage(action === 'approve' ? 'อนุมัติคำขอเรียบร้อยแล้ว' : 'ไม่อนุมัติคำขอเรียบร้อยแล้ว')
      await loadSuppliers()
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || error?.message || 'อัปเดตคำขอไม่สำเร็จ')
    }
  }

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">จัดการร้านค้า</div>
            <div className="text-xs text-[color:var(--color-muted)]">จัดการข้อมูลร้านค้า คะแนนความน่าเชื่อถือ คำขอรอตรวจ และไฟล์แนบจากหน้าเดียว</div>
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
              สร้างร้านค้าใหม่
            </button>
          ) : null}
        </div>
        {message ? <div className="mt-3 rounded border border-[color:var(--color-border)] surface-soft px-3 py-2 text-sm text-[color:var(--color-fg)]">{message}</div> : null}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
            <input
              className={fieldClassName()}
              placeholder="ค้นหาชื่อร้าน เบอร์โทร หรือรหัสร้าน"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="mt-3 space-y-2">
              {busy && items.length === 0 ? <div className="text-sm text-[color:var(--color-muted)]">กำลังโหลดข้อมูลร้านค้า...</div> : null}
              {items.map((supplier) => (
                <button
                  key={supplier.id}
                  type="button"
                  className={`w-full rounded border px-3 py-3 text-left text-sm ${
                    selectedSupplierId === supplier.id
                      ? 'border-[color:var(--color-primary)] surface-soft'
                      : 'border-[color:var(--color-border)] surface-soft hover:bg-white/5'
                  }`}
                  onClick={() => selectSupplier(supplier)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold">{supplier.name}</div>
                    <div className="rounded border border-[color:var(--color-border)] px-2 py-0.5 text-[11px] text-[color:var(--color-muted)]">
                      {supplierStatusLabel(supplier.status)}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-[color:var(--color-muted)]">{supplier.code} • เชื่อมกับสินค้า {supplier.product_count} รายการ</div>
                  <div className="mt-1 text-xs text-[color:var(--color-muted-strong)]">คะแนนที่ใช้จริง {supplier.reliability?.effective_score ?? 0}</div>
                </button>
              ))}
              {!busy && items.length === 0 ? <div className="text-sm text-[color:var(--color-muted)]">ยังไม่พบร้านค้า</div> : null}
            </div>
          </div>

          {canManage ? (
            <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
              <div className="text-sm font-semibold">คำขอรอตรวจสอบ</div>
              <div className="mt-3 space-y-2">
                {proposals.map((proposal) => (
                  <div key={proposal.id} className="rounded border border-[color:var(--color-border)] surface-soft p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-semibold">{proposalActionLabel(proposal.action)}</div>
                      <div className="text-xs text-[color:var(--color-muted)]">รอตรวจสอบ</div>
                    </div>
                    <div className="mt-1 text-xs text-[color:var(--color-muted)]">คำขอ #{proposal.id.slice(0, 8)}</div>
                    {canVerify ? (
                      <div className="mt-3 flex gap-2">
                        <button className="rounded border border-emerald-400/30 px-3 py-1.5 text-xs text-emerald-100 hover:bg-emerald-500/10" type="button" onClick={() => reviewProposal(proposal, 'approve')}>
                          อนุมัติ
                        </button>
                        <button className="rounded border border-red-400/30 px-3 py-1.5 text-xs text-red-100 hover:bg-red-500/10" type="button" onClick={() => reviewProposal(proposal, 'reject')}>
                          ไม่อนุมัติ
                        </button>
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-[color:var(--color-muted)]">Admin สร้างคำขอได้ แต่การอนุมัติหรือไม่อนุมัติต้องให้ Dev หรือ Owner ดำเนินการ</div>
                    )}
                  </div>
                ))}
                {proposals.length === 0 ? <div className="text-sm text-[color:var(--color-muted)]">ไม่มีคำขอค้างอยู่</div> : null}
              </div>
            </div>
          ) : null}
        </div>

        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          {!creating && !selectedSupplier ? (
            <div className="text-sm text-[color:var(--color-muted)]">เลือกร้านค้าจากด้านซ้าย หรือกดสร้างร้านค้าใหม่</div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input className={fieldClassName()} placeholder="ชื่อร้านค้า" value={draft.name} onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))} />
                <input className={fieldClassName()} placeholder="เบอร์โทร" value={draft.phone} onChange={(event) => setDraft((prev) => ({ ...prev, phone: event.target.value }))} />
                <input className={fieldClassName()} placeholder="ไอดีไลน์" value={draft.line_id} onChange={(event) => setDraft((prev) => ({ ...prev, line_id: event.target.value }))} />
                <input className={fieldClassName()} placeholder="ลิงก์ Facebook" value={draft.facebook_url} onChange={(event) => setDraft((prev) => ({ ...prev, facebook_url: event.target.value }))} />
                <input className={fieldClassName()} placeholder="ลิงก์เว็บไซต์" value={draft.website_url} onChange={(event) => setDraft((prev) => ({ ...prev, website_url: event.target.value }))} />
                <select className={fieldClassName()} value={draft.status} onChange={(event) => setDraft((prev) => ({ ...prev, status: event.target.value }))}>
                  <option value="ACTIVE">พร้อมใช้งาน</option>
                  <option value="INACTIVE">ปิดใช้งาน</option>
                  <option value="ARCHIVED">เก็บถาวร</option>
                </select>
              </div>

              <textarea className={fieldClassName(true)} placeholder="ที่อยู่ร้านค้า" value={draft.address} onChange={(event) => setDraft((prev) => ({ ...prev, address: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="ข้อมูลจุดรับสินค้า หรือรายละเอียดการรับสินค้า" value={draft.pickup_notes} onChange={(event) => setDraft((prev) => ({ ...prev, pickup_notes: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="รายละเอียดแหล่งที่มาหรือช่องทางติดต่อร้าน" value={draft.source_details} onChange={(event) => setDraft((prev) => ({ ...prev, source_details: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="ประวัติการซื้อหรือหมายเหตุการสั่งของ" value={draft.purchase_history_notes} onChange={(event) => setDraft((prev) => ({ ...prev, purchase_history_notes: event.target.value }))} />
              <textarea className={fieldClassName(true)} placeholder="หมายเหตุเรื่องความน่าเชื่อถือ" value={draft.reliability_note} onChange={(event) => setDraft((prev) => ({ ...prev, reliability_note: event.target.value }))} />

              <label className="flex items-center gap-2 text-sm text-[color:var(--color-fg)]">
                <input type="checkbox" checked={draft.is_verified} onChange={(event) => setDraft((prev) => ({ ...prev, is_verified: event.target.checked }))} />
                ยืนยันแล้วว่าเป็นร้านค้าที่ตรวจสอบข้อมูลเบื้องต้นแล้ว
              </label>

              {selectedSupplier?.reliability ? (
                <div className="rounded border border-[color:var(--color-border)] surface-soft p-4">
                  <div className="text-sm font-semibold">สรุปคะแนนความน่าเชื่อถือ</div>
                  <div className="mt-1 text-xs text-[color:var(--color-muted)]">ใช้ดูภาพรวมความน่าเชื่อถือของร้านค้าและเหตุผลที่ทำให้คะแนนสูงหรือต่ำ</div>
                  <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
                    <div className="rounded border border-[color:var(--color-border)] surface-soft p-3 text-sm">คะแนนรวม {selectedSupplier.reliability.overall_score}</div>
                    <div className="rounded border border-[color:var(--color-border)] surface-soft p-3 text-sm">คะแนนจากระบบ {selectedSupplier.reliability.auto_score}</div>
                    <div className="rounded border border-[color:var(--color-border)] surface-soft p-3 text-sm">คะแนนที่ใช้จริง {selectedSupplier.reliability.effective_score}</div>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                    {selectedSupplier.reliability.breakdown.map((item) => (
                      <div key={item.metric_key} className="rounded border border-[color:var(--color-border)] surface-soft px-3 py-2 text-xs text-[color:var(--color-muted)]">
                        {reliabilityMetricLabel(item.metric_key)}: {item.score_value} / น้ำหนัก {item.weight}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {canManage ? (
                <div className="flex flex-wrap gap-2">
                  <button className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60" type="button" onClick={handleCreateOrUpdate} disabled={saving}>
                    {saving ? 'กำลังบันทึก...' : creating ? 'สร้างร้านค้า' : 'บันทึกการแก้ไข'}
                  </button>
                  {!creating && selectedSupplierId ? (
                    <button className="rounded border border-red-400/30 px-4 py-2 text-sm text-red-100 hover:bg-red-500/10" type="button" onClick={handleArchive}>
                      ลบร้านค้าออกจากรายการ
                    </button>
                  ) : null}
                </div>
              ) : null}
              {!creating && selectedSupplierId && canManage ? (
                <div className="text-xs text-[color:var(--color-muted)]">
                  การลบจะเป็นแบบเก็บออกจากรายการใช้งาน ข้อมูลเดิมยังอยู่ในประวัติและสำรองข้อมูล
                </div>
              ) : null}

              {!creating && selectedSupplier ? (
                <div className="rounded border border-[color:var(--color-border)] surface-soft p-4">
                  <div className="text-sm font-semibold">ไฟล์แนบ</div>
                  {canManage ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <select className={fieldClassName()} value={attachmentClassification} onChange={(event) => setAttachmentClassification(event.target.value)}>
                        <option value="supplier_profile">ข้อมูลร้านค้า</option>
                        <option value="quote_document">ใบเสนอราคา</option>
                        <option value="invoice">ใบแจ้งหนี้</option>
                        <option value="chat_proof">หลักฐานแชต</option>
                        <option value="zip_archive">ไฟล์ ZIP</option>
                        <option value="other">อื่น ๆ</option>
                      </select>
                      <input type="file" className={fieldClassName()} onChange={(event) => setAttachmentFile(event.target.files?.[0] || null)} />
                      <button className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-[color:var(--color-fg)] hover:bg-white/10" type="button" onClick={handleUploadAttachment}>
                        อัปโหลดไฟล์
                      </button>
                    </div>
                  ) : null}
                  <div className="mt-3 space-y-2">
                    {selectedSupplier.attachments.map((item) => (
                      <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-[color:var(--color-border)] surface-soft px-3 py-2 text-sm">
                        <div>
                          <div>{item.original_filename}</div>
                          <div className="text-xs text-[color:var(--color-muted)]">
                            {attachmentTypeLabel(item.classification)} • {item.content_type} • {(item.size_bytes / 1024 / 1024).toFixed(2)} MB • {malwareStatusLabel(item.malware_status)}
                          </div>
                        </div>
                        {canManage ? (
                          <button className="rounded border border-[color:var(--color-border)] px-3 py-1.5 text-xs text-[color:var(--color-fg)] hover:bg-white/10" type="button" onClick={() => handleArchiveAttachment(item)}>
                            เก็บไฟล์
                          </button>
                        ) : null}
                      </div>
                    ))}
                    {selectedSupplier.attachments.length === 0 ? <div className="text-sm text-[color:var(--color-muted)]">ยังไม่มีไฟล์แนบ</div> : null}
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
