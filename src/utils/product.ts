import type { Product } from '../types/models'

type PartialProduct = Partial<Product> & {
  name?: unknown
  name_th?: unknown
  name_en?: unknown
}

function asText(value: unknown) {
  if (typeof value === 'string') return value
  if (value == null) return ''
  return String(value)
}

export function normalizeProduct(product: PartialProduct): Product {
  const rawName = product?.name
  const rawNameRecord = rawName && typeof rawName === 'object' ? (rawName as unknown as Record<string, unknown>) : null
  const rawNameTh =
    rawNameRecord && 'th' in rawNameRecord
      ? rawNameRecord.th
      : product?.name_th
  const rawNameEn =
    rawNameRecord && 'en' in rawNameRecord
      ? rawNameRecord.en
      : product?.name_en

  return {
    id: asText(product?.id),
    sku: asText(product?.sku),
    branch_id: product?.branch_id == null ? null : asText(product.branch_id),
    category_id: product?.category_id ?? null,
    name: {
      th: asText(rawNameTh),
      en: asText(rawNameEn),
    },
    category: asText(product?.category),
    type: asText(product?.type),
    unit: asText(product?.unit),
    cost_price: asText(product?.cost_price || '0'),
    selling_price: product?.selling_price == null ? null : asText(product.selling_price),
    stock_qty: asText(product?.stock_qty || '0'),
    min_stock: asText(product?.min_stock || '0'),
    max_stock: asText(product?.max_stock || '0'),
    status: (product?.status as Product['status']) || 'NORMAL',
    is_test: Boolean(product?.is_test),
    supplier: asText(product?.supplier),
    barcode: asText(product?.barcode),
    image_url: product?.image_url == null ? null : asText(product.image_url),
    notes: asText(product?.notes),
    created_at: asText(product?.created_at),
    updated_at: asText(product?.updated_at),
    created_by: asText(product?.created_by),
  }
}

export function normalizeProductListResponse(data: { items?: PartialProduct[]; total?: number }) {
  return {
    items: Array.isArray(data?.items) ? data.items.map(normalizeProduct) : [],
    total: Number(data?.total || 0),
  }
}

export function productDisplayName(product: PartialProduct | null | undefined) {
  const normalized = normalizeProduct(product || {})
  return normalized.name.th || normalized.name.en || normalized.sku || '-'
}
