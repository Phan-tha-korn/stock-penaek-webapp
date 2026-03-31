import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getPublicProduct } from '../../services/products'
import type { Product } from '../../types/models'
import { useConfigStore } from '../../store/configStore'
import { formatTHB } from '../../utils/money'

export function PublicProductPage() {
  const { sku } = useParams<{ sku: string }>()
  const [product, setProduct] = useState<Product | null>(null)
  const [error, setError] = useState(false)
  const config = useConfigStore((s) => s.config)

  useEffect(() => {
    if (sku) {
      getPublicProduct(sku)
        .then(setProduct)
        .catch(() => setError(true))
    }
  }, [sku])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="card max-w-md w-full rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-8 text-center backdrop-blur shadow-2xl">
          <div className="text-6xl mb-4">🔍</div>
          <h2 className="text-xl font-bold mb-2">ไม่พบสินค้า</h2>
          <p className="text-white/60 mb-6">SKU: {sku}</p>
          <Link to="/" className="text-[color:var(--color-primary)] hover:underline">
            กลับหน้าหลัก
          </Link>
        </div>
      </div>
    )
  }

  if (!product) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-white/50">กำลังโหลด...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-4 md:p-8 flex items-center justify-center">
      <div className="card w-full max-w-md overflow-hidden rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
        <div className="aspect-square w-full bg-black/30 flex items-center justify-center border-b border-[color:var(--color-border)]">
          {product.image_url ? (
            <img src={product.image_url} alt={product.name.th} className="h-full w-full object-cover" />
          ) : (
            <div className="text-white/30 text-6xl">📦</div>
          )}
        </div>
        
        <div className="p-6 space-y-4">
          <div className="text-center border-b border-white/10 pb-4">
            <div className="text-2xl font-bold">{product.name.th}</div>
            <div className="text-sm text-white/50">{product.name.en}</div>
          </div>

          <div className="grid grid-cols-2 gap-y-3 text-sm">
            <div className="text-white/60">SKU</div>
            <div className="min-w-0 font-mono text-right break-all">{product.sku}</div>
            
            <div className="text-white/60">หมวดหมู่</div>
            <div className="min-w-0 text-right break-words">{product.category}</div>
            
            <div className="text-white/60">ประเภท</div>
            <div className="min-w-0 text-right break-words">{product.type}</div>
            
            <div className="text-white/60">หน่วยนับ</div>
            <div className="min-w-0 text-right break-words">{product.unit}</div>

            <div className="text-white/60">คงเหลือ</div>
            <div className="min-w-0 text-right break-words">{product.stock_qty}</div>

            <div className="text-white/60">ขั้นต่ำ</div>
            <div className="min-w-0 text-right break-words">{product.min_stock}</div>

            <div className="text-white/60">ที่ควรมี</div>
            <div className="min-w-0 text-right break-words">{product.max_stock}</div>

            <div className="text-white/60">ต้นทุน/หน่วย</div>
            <div className="min-w-0 text-right break-words">{formatTHB(product.cost_price)}</div>

            <div className="text-white/60">ราคาขาย/หน่วย</div>
            <div className="min-w-0 text-right break-words">{product.selling_price == null ? '-' : formatTHB(product.selling_price)}</div>
          </div>

          {config?.app_name && (
            <div className="pt-4 text-center text-xs text-white/40 border-t border-white/10">
              Managed by {config.app_name}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
