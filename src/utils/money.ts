export function formatTHB(value: number | string | null | undefined) {
  const n = typeof value === 'string' ? Number(value) : value ?? 0
  if (!Number.isFinite(n)) return '฿0.00'
  return new Intl.NumberFormat('th-TH', { style: 'currency', currency: 'THB' }).format(n)
}

