import { api } from './api'
import type { AttachmentItem, Supplier, SupplierProposal } from '../types/models'

export interface SupplierListParams {
  q?: string
  include_archived?: boolean
  limit?: number
  offset?: number
}

export interface SupplierPayload {
  branch_id?: string | null
  name: string
  phone?: string
  line_id?: string
  facebook_url?: string
  website_url?: string
  address?: string
  pickup_notes?: string
  source_details?: string
  purchase_history_notes?: string
  reliability_note?: string
  status?: string
  is_verified?: boolean
  contacts?: Array<{ contact_type: string; label: string; value: string; is_primary: boolean }>
  links?: Array<{ link_type: string; label: string; url: string; is_primary: boolean }>
  pickup_points?: Array<{ label: string; address: string; details: string; is_primary: boolean }>
}

export async function listSuppliers(params: SupplierListParams = {}) {
  const { data } = await api.get<{ items: Supplier[]; total: number }>('/suppliers', { params })
  return data
}

export async function getSupplier(id: string) {
  const { data } = await api.get<Supplier>(`/suppliers/${encodeURIComponent(id)}`)
  return data
}

export async function createSupplier(payload: SupplierPayload) {
  const { data } = await api.post<Supplier | SupplierProposal>('/suppliers', payload)
  return data
}

export async function updateSupplier(id: string, payload: Partial<SupplierPayload>) {
  const { data } = await api.put<Supplier | SupplierProposal>(`/suppliers/${encodeURIComponent(id)}`, payload)
  return data
}

export async function archiveSupplier(id: string, reason = '') {
  const { data } = await api.delete<Supplier | SupplierProposal>(`/suppliers/${encodeURIComponent(id)}`, { params: { reason } })
  return data
}

export async function listSupplierProposals(status?: string) {
  const { data } = await api.get<SupplierProposal[]>('/suppliers/proposals', { params: { status } })
  return data
}

export async function approveSupplierProposal(id: string, review_note = '') {
  const { data } = await api.post<SupplierProposal>(`/suppliers/proposals/${encodeURIComponent(id)}/approve`, { review_note })
  return data
}

export async function rejectSupplierProposal(id: string, review_note = '') {
  const { data } = await api.post<SupplierProposal>(`/suppliers/proposals/${encodeURIComponent(id)}/reject`, { review_note })
  return data
}

export async function listSupplierAttachments(id: string) {
  const { data } = await api.get<AttachmentItem[]>(`/suppliers/${encodeURIComponent(id)}/attachments`)
  return data
}

export async function uploadSupplierAttachment(id: string, file: File, classification: string) {
  const form = new FormData()
  form.append('classification', classification)
  form.append('file', file)
  const { data } = await api.post<AttachmentItem>(`/suppliers/${encodeURIComponent(id)}/attachments`, form)
  return data
}

export async function archiveSupplierAttachment(id: string, attachmentId: string) {
  const { data } = await api.delete<AttachmentItem>(`/suppliers/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}`)
  return data
}
