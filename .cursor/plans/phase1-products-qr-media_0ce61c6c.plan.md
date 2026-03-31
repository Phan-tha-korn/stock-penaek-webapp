---
name: phase1-products-qr-media
overview: "Implement phase 1 focused on product management upgrades: editable products for admin+, bulk product creation with images from ZIP+CSV, persistent QR/public product view, and storage-efficient local media handling."
todos:
  - id: backend-media-pipeline
    content: Implement local media storage and image optimization (WebP + resize) utilities for product images
    status: completed
  - id: backend-bulk-zip-import
    content: Add ZIP+CSV bulk import endpoint with image matching, validation, and per-row result reporting
    status: completed
  - id: backend-product-edit-upload
    content: Enable admin+ product edit and single product create/update with image upload
    status: completed
  - id: frontend-products-workflow
    content: Add edit product UI, single image upload support, and ZIP bulk-import modal with detailed results
    status: completed
  - id: qr-public-readonly-verification
    content: Ensure permanent URL-based QR flow remains read-only and complete for scanned product details
    status: completed
  - id: menu-i18n-owner-label
    content: Rename OWNER CHECK menu/page labels to consistent TH/EN localized wording
    status: completed
  - id: phase1-validation
    content: Run end-to-end role and sync tests for phase 1 and document pass/fail outcomes
    status: completed
isProject: false
---

# Phase 1: Product + Image + QR Upgrade

## Scope

Deliver only Phase 1 features first:

- Admin+ can edit product details
- Create single product with image upload
- Bulk create products with one ZIP upload (`products.csv` + image files)
- Permanent QR workflow via stable public product URL
- Public product page is read-only and scannable from mobile/desktop
- Rename OWNER CHECK menu labels to localized TH/EN wording

## Storage-efficient approach (as requested)

- Use local filesystem storage under a dedicated media root (e.g. `storage/media/products/`)
- Normalize all uploaded images to WebP (quality/compression target) and resize max dimension to reduce disk usage
- Store only relative image path in DB, not binary blobs
- Do not store generated QR image files by default; keep canonical URL (`/public/product/:sku`) and render QR dynamically in UI (lowest disk cost)
- Optional maintenance hooks for later: remove orphan media files not referenced by DB

## Backend changes

- Extend product APIs in [c:\Stock Penaek Webapp\server\api\products.py](c:\Stock Penaek Webapp\server\api\products.py):
  - Add/update endpoint(s) for admin/owner/dev edit product fields including prices, min/max, image path
  - Add multipart endpoint for single-product create with image file
  - Add multipart endpoint for bulk import from ZIP
- Implement ZIP ingest service:
  - Parse `products.csv` from ZIP
  - Match image filename keys to CSV rows (configurable field like `image_key` or `sku`)
  - Validate required fields and return per-row success/fail summary
- Add media utility module for:
  - Safe filename/path sanitization
  - Image conversion/compression to WebP
  - Relative path generation
- Ensure public read-only product endpoint remains stable for QR target and returns all display fields

## Frontend changes

- Update products UI in [c:\Stock Penaek Webapp\src\pages\app\ProductsPage.tsx](c:\Stock Penaek Webapp\src\pages\app\ProductsPage.tsx):
  - Add “Edit product” flow for admin+
  - Single create form supports image upload directly
  - New bulk import dialog accepts ZIP and shows row-level result summary
- Keep/extend QR behavior in dashboard/public page:
  - Continue using permanent URL-based QR for each SKU
  - Ensure scan opens read-only product page with complete details
- Update localized navigation labels in [c:\Stock Penaek Webapp\src\components\layout\AppShell.tsx](c:\Stock Penaek Webapp\src\components\layout\AppShell.tsx) and i18n resources for consistent TH/EN naming replacing OWNER CHECK wording

## CSV + ZIP contract (user-facing)

- ZIP root contains:
  - `products.csv`
  - image files (`001.jpg`, `001.png`, etc.)
- `products.csv` columns (minimum + practical):
  - `sku,name_th,category,unit,stock_qty,min_stock,max_stock,cost_price,selling_price,image_key`
- Matching rule:
  - `image_key=001` maps to file `001.*` in ZIP
- Import result:
  - created / updated / failed counts + per-row error messages

## Validation and safety

- Reject unsafe ZIP paths and unsupported file types
- Limit max ZIP size and image count to prevent abuse
- Skip broken images with clear row error (do not crash whole import)
- Preserve existing role checks and auditing patterns

## Test plan

- API tests per role:
  - edit product permissions (admin/owner/dev pass, others deny)
  - single create with image upload
  - bulk ZIP import mixed valid/invalid rows
- Data consistency checks:
  - dashboard KPI totals update after imports/edits
  - product search returns newly imported items
- QR/public checks:
  - open `/public/product/:sku` from generated QR URL on desktop/mobile
  - verify page read-only and includes price/stock/image details
- Storage checks:
  - uploaded images converted to WebP and filesize reduced
  - no QR file artifacts created unnecessarily

## Deliverables

- Endpoints and UI for single+bulk creation with images
- Edit product capability for admin+
- Localized owner menu text updates
- Documented ZIP/CSV format and operational limits

