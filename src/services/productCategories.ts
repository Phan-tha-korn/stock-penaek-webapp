import { api } from './api'
import type { InventoryRuleSettings, ProductCategory } from '../types/models'

export async function listProductCategories(includeDeleted = false) {
  const { data } = await api.get<{ items: ProductCategory[] }>('/product-categories', { params: { include_deleted: includeDeleted } })
  return {
    items: Array.isArray(data?.items) ? data.items : [],
  }
}

export async function createProductCategory(payload: { name: string; description?: string; sort_order?: number }) {
  const { data } = await api.post<ProductCategory>('/product-categories', payload)
  return data
}

export async function updateProductCategory(id: string, payload: { name?: string; description?: string; sort_order?: number }) {
  const { data } = await api.patch<ProductCategory>(`/product-categories/${encodeURIComponent(id)}`, payload)
  return data
}

export async function deleteProductCategory(id: string) {
  const { data } = await api.delete<{ ok: boolean }>(`/product-categories/${encodeURIComponent(id)}`)
  return data
}

export async function restoreProductCategory(id: string) {
  const { data } = await api.post<ProductCategory>(`/product-categories/${encodeURIComponent(id)}/restore`, {})
  return data
}

export async function getInventoryRuleSettings() {
  const { data } = await api.get<InventoryRuleSettings>('/product-categories/settings')
  return {
    max_multiplier: Number(data?.max_multiplier || 2),
    min_divisor: Number(data?.min_divisor || 3),
  }
}

export async function updateInventoryRuleSettings(payload: InventoryRuleSettings) {
  const { data } = await api.put<InventoryRuleSettings>('/product-categories/settings', payload)
  return {
    max_multiplier: Number(data?.max_multiplier || 2),
    min_divisor: Number(data?.min_divisor || 3),
  }
}
