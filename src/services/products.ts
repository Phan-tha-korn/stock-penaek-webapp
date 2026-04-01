import { api } from './api'
import type { Product } from '../types/models'

export interface ProductListParams {
  q?: string
  status?: string
  is_test?: boolean
  include_deleted?: boolean
  limit?: number
  offset?: number
}

export async function listProducts(params: ProductListParams) {
  const { data } = await api.get<{ items: Product[]; total: number }>('/products', { params })
  return data
}

export async function getPublicProduct(sku: string) {
  const { data } = await api.get<Product>(`/products/public/products/${encodeURIComponent(sku)}`)
  return data
}

export interface StockAdjustData {
  qty: number
  type: 'STOCK_IN' | 'STOCK_OUT' | 'ADJUST'
  reason?: string
}

export async function adjustStock(sku: string, data: StockAdjustData) {
  const res = await api.post<Product>(`/products/${encodeURIComponent(sku)}/adjust`, data)
  return res.data
}

export interface ProductCreateData {
  sku: string
  name_th: string
  name_en?: string
  category?: string
  type?: string
  unit?: string
  cost_price?: number
  selling_price?: number | null
  stock_qty?: number
  min_stock?: number
  max_stock?: number
  is_test?: boolean
  supplier?: string
  barcode?: string
  image_url?: string | null
  notes?: string
}

export async function createProduct(data: ProductCreateData) {
  const res = await api.post<Product>('/products', data)
  return res.data
}

export type ProductUpdateData = Partial<Omit<ProductCreateData, 'sku' | 'stock_qty' | 'is_test'>>

export async function updateProduct(sku: string, data: ProductUpdateData) {
  const res = await api.put<Product>(`/products/${encodeURIComponent(sku)}`, data)
  return res.data
}

export async function updateProductWithImage(sku: string, data: ProductUpdateData, imageFile?: File) {
  const form = new FormData()
  Object.entries(data).forEach(([k, v]) => {
    if (v === undefined || v === null) return
    form.append(k, String(v))
  })
  if (imageFile) form.append('image', imageFile)
  const res = await api.post<Product>(`/products/${encodeURIComponent(sku)}/update-with-image`, form)
  return res.data
}

export async function createProductWithImage(data: ProductCreateData, imageFile?: File) {
  const form = new FormData()
  form.append('sku', data.sku)
  form.append('name_th', data.name_th)
  form.append('name_en', data.name_en || '')
  form.append('category', data.category || '')
  form.append('type', data.type || '')
  form.append('unit', data.unit || '')
  form.append('cost_price', String(data.cost_price ?? 0))
  if (data.selling_price !== undefined && data.selling_price !== null) form.append('selling_price', String(data.selling_price))
  form.append('stock_qty', String(data.stock_qty ?? 0))
  form.append('min_stock', String(data.min_stock ?? 0))
  form.append('max_stock', String(data.max_stock ?? 0))
  form.append('is_test', String(Boolean(data.is_test)))
  form.append('supplier', data.supplier || '')
  form.append('barcode', data.barcode || '')
  form.append('notes', data.notes || '')
  if (imageFile) form.append('image', imageFile)
  const res = await api.post<Product>('/products/create-with-image', form)
  return res.data
}

export interface ProductBulkRowResult {
  row: number
  sku: string
  ok: boolean
  action: string
  error?: string | null
}

export interface ProductBulkImportResult {
  ok: boolean
  created: number
  updated: number
  failed: number
  items: ProductBulkRowResult[]
}

export async function bulkImportProductsZip(file: File, overwriteExisting = false) {
  const form = new FormData()
  form.append('file', file)
  form.append('overwrite_existing', String(overwriteExisting))
  const res = await api.post<ProductBulkImportResult>('/products/bulk-import-zip', form)
  return res.data
}

export async function downloadBulkImportTemplateZip(rows: number) {
  const res = await api.get<Blob>('/products/bulk-import-template-zip', {
    params: { rows },
    responseType: 'blob',
  })
  return res.data
}

export async function deleteProduct(sku: string, reason: string) {
  const res = await api.post<Product>(`/products/${encodeURIComponent(sku)}/delete`, { reason })
  return res.data
}

export async function restoreProduct(sku: string) {
  const res = await api.post<Product>(`/products/${encodeURIComponent(sku)}/restore`, {})
  return res.data
}

export async function bulkDeleteProducts(skus: string[], reason: string) {
  const res = await api.post<{ ok: boolean; deleted?: number }>('/products/bulk-delete', { skus, reason })
  return res.data
}

export async function deleteAllTestProducts() {
  const res = await api.post<{ ok: boolean; deleted?: number }>('/products/delete-all-test', {})
  return res.data
}

export async function deleteAllProducts(confirm: string) {
  const res = await api.post<{ ok: boolean; deleted?: number; error?: string }>('/products/delete-all', { confirm })
  return res.data
}

export async function importFromSheets(params: { overwrite_stock_qty?: boolean; overwrite_prices?: boolean } = {}) {
  const res = await api.post<{ ok: boolean; created?: number; updated?: number; skipped?: number; error?: string }>('/products/import-from-sheets', params)
  return res.data
}

export async function syncToSheets() {
  const res = await api.post<{ ok: boolean; error?: string }>('/products/sync-to-sheets', {})
  return res.data
}
