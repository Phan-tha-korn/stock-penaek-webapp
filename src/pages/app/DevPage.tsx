import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../../services/api'
import { createDevBackup, getDevBackupDownloadUrl, previewDevBackup, restoreDevBackup, type DevBackupPreviewResult } from '../../services/devBackup'
import { fetchConfig } from '../../services/config'
import { fetchActivity } from '../../services/dashboard'
import { forceFullSyncToSheets, importFromSheets, syncToSheets } from '../../services/products'
import { deleteGarbage, getGarbageWhitelist, scanGarbage, updateGarbageWhitelist, type GarbageFileItem } from '../../services/devGarbage'
import { getNotificationConfig, updateNotificationConfig } from '../../services/devNotifications'
import { createDevSheet, getDevSheetsConfig, resolveDevSheetUrl, type DevSheetCreateResult, type DevSheetsConfig } from '../../services/devSheets'
import { resetStock } from '../../services/devReset'
import {
  createProductCategory,
  deleteProductCategory,
  getInventoryRuleSettings,
  listProductCategories,
  restoreProductCategory,
  updateInventoryRuleSettings,
  updateProductCategory,
} from '../../services/productCategories'
import { useAuthStore } from '../../store/authStore'
import type { ActivityItem } from '../../services/dashboard'
import type { AppConfig, InventoryRuleSettings, ProductCategory } from '../../types/models'

const GOOGLE_OAUTH_PENDING_KEY = 'google_oauth_pending_until'

function hasPendingGoogleOauth() {
  const raw = window.localStorage.getItem(GOOGLE_OAUTH_PENDING_KEY)
  const until = Number(raw || '0')
  if (!until || Number.isNaN(until)) return false
  if (until <= Date.now()) {
    window.localStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY)
    return false
  }
  return true
}

export function DevPage() {
  const navigate = useNavigate()
  const role = useAuthStore((s) => s.role)
  const canUse = role === 'DEV'

  const [busy, setBusy] = useState(true)
  const [health, setHealth] = useState<any>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])

  const [sheetMsg, setSheetMsg] = useState<string | null>(null)
  const [sheetAction, setSheetAction] = useState<'sync' | 'force-sync' | 'import' | null>(null)
  const [sheetsCfg, setSheetsCfg] = useState<DevSheetsConfig | null>(null)
  const [categoryBusy, setCategoryBusy] = useState(false)
  const [categoryMsg, setCategoryMsg] = useState<string | null>(null)
  const [categoryName, setCategoryName] = useState('')
  const [categoryDescription, setCategoryDescription] = useState('')
  const [categorySort, setCategorySort] = useState('0')
  const [categoryItems, setCategoryItems] = useState<ProductCategory[]>([])
  const [inventoryRules, setInventoryRules] = useState<InventoryRuleSettings>({ max_multiplier: 2, min_divisor: 3 })
  const [sheetsLoading, setSheetsLoading] = useState(true)
  const [googleSheetsPending, setGoogleSheetsPending] = useState(false)
  const [sheetCreateTitle, setSheetCreateTitle] = useState('')
  const [sheetShareEmails, setSheetShareEmails] = useState('')
  const [sheetCreateBusy, setSheetCreateBusy] = useState(false)
  const [lastCreatedSheet, setLastCreatedSheet] = useState<DevSheetCreateResult | null>(null)
  const [backupBusy, setBackupBusy] = useState(false)
  const [restoreBusy, setRestoreBusy] = useState(false)
  const [restoreFile, setRestoreFile] = useState<File | null>(null)
  const [resetStockBusy, setResetStockBusy] = useState(false)
  const [garbageBusy, setGarbageBusy] = useState(false)
  const [garbageItems, setGarbageItems] = useState<GarbageFileItem[]>([])
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleteMode, setDeleteMode] = useState<'backup' | 'permanent'>('backup')
  const [garbageMsg, setGarbageMsg] = useState<string | null>(null)
  const [whitelist, setWhitelist] = useState<string[]>([])
  const [whitelistInput, setWhitelistInput] = useState('')
  const [garbageExpanded, setGarbageExpanded] = useState(false)

  const [notifBusy, setNotifBusy] = useState(false)
  const [notifMsg, setNotifMsg] = useState<string | null>(null)
  const [notifEnabled, setNotifEnabled] = useState(false)
  const [notifLow, setNotifLow] = useState<number[]>([])
  const [notifHigh, setNotifHigh] = useState<number[]>([])
  const [notifRoles, setNotifRoles] = useState<string[]>([])
  const [notifLowInput, setNotifLowInput] = useState('')
  const [notifHighInput, setNotifHighInput] = useState('')
  const [notifTokenStatus, setNotifTokenStatus] = useState<Record<string, string>>({})
  const [notifLineTokens, setNotifLineTokens] = useState<Record<string, string>>({})
  const [notifTokenRole, setNotifTokenRole] = useState<string | null>(null)
  const [notifTokenInput, setNotifTokenInput] = useState('')
  const [notifIncludeName, setNotifIncludeName] = useState(true)
  const [notifIncludeSku, setNotifIncludeSku] = useState(true)
  const [notifIncludeStatus, setNotifIncludeStatus] = useState(true)
  const [notifIncludeCurrentQty, setNotifIncludeCurrentQty] = useState(true)
  const [notifIncludeTargetQty, setNotifIncludeTargetQty] = useState(true)
  const [notifIncludeRestockQty, setNotifIncludeRestockQty] = useState(true)
  const [notifIncludeActor, setNotifIncludeActor] = useState(true)
  const [notifIncludeReason, setNotifIncludeReason] = useState(true)
  const [notifIncludeImageUrl, setNotifIncludeImageUrl] = useState(false)
  const [secureAction, setSecureAction] = useState<'backup' | 'restore' | 'reset' | null>(null)
  const [securePassword, setSecurePassword] = useState('')
  const [sheetGuardOpen, setSheetGuardOpen] = useState(false)
  const [sheetGuardMode, setSheetGuardMode] = useState<'missing' | 'sync'>('missing')
  const [restorePreview, setRestorePreview] = useState<DevBackupPreviewResult | null>(null)

  async function reload() {
    setBusy(true)
    try {
      const [h, c, a] = await Promise.all([
        api.get('/health').then((r) => r.data),
        fetchConfig(),
        fetchActivity().then((r) => r.items)
      ])
      setHealth(h)
      setConfig(c)
      setActivity(a)
    } finally {
      setBusy(false)
    }
  }

  async function reloadCategoryTools() {
    const [cats, rules] = await Promise.all([
      listProductCategories(true),
      getInventoryRuleSettings(),
    ])
    setCategoryItems(cats.items)
    setInventoryRules(rules)
  }

  async function scanNow() {
    setGarbageBusy(true)
    setGarbageMsg(null)
    try {
      const [scanRes, wl] = await Promise.all([scanGarbage(false), getGarbageWhitelist()])
      setGarbageItems(scanRes.items)
      setWhitelist(wl.items)
      setSelectedPaths([])
    } catch (e: any) {
      setGarbageMsg(e?.response?.data?.detail || e?.message || 'สแกนไฟล์ขยะไม่สำเร็จ')
    } finally {
      setGarbageBusy(false)
    }
  }

  function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`
    const kb = bytes / 1024
    if (kb < 1024) return `${kb.toFixed(1)} KB`
    const mb = kb / 1024
    if (mb < 1024) return `${mb.toFixed(1)} MB`
    const gb = mb / 1024
    return `${gb.toFixed(2)} GB`
  }

  async function downloadAuthorizedFile(downloadUrl: string, fileName: string) {
    const token = useAuthStore.getState().tokens?.access_token
    const res = await fetch(downloadUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!res.ok) throw new Error('download_failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  async function downloadProtectedFile(downloadUrl: string, fileName: string) {
    await downloadAuthorizedFile(getDevBackupDownloadUrl(downloadUrl), fileName)
  }

  function requireSheetsReady(action: () => void, mode: 'missing' | 'sync' = 'missing') {
    if (sheetsCfg?.enabled) {
      action()
      return
    }
    setSheetGuardMode(mode)
    setSheetGuardOpen(true)
    window.setTimeout(() => setSheetGuardOpen(false), 3000)
  }

  function openSheetUrl(url?: string, mode: 'missing' | 'sync' = 'sync') {
    requireSheetsReady(() => {
      const target = resolveDevSheetUrl(String(url || ''))
      if (!target) {
        setSheetMsg('ยังไม่พบลิงก์ Google Sheets สำหรับรายการนี้')
        return
      }
      window.open(target, '_blank', 'noopener,noreferrer')
    }, mode)
  }

  function downloadSheetFile(url?: string, fileName = 'stock-sheet.csv', mode: 'missing' | 'sync' = 'sync') {
    requireSheetsReady(() => {
      const target = resolveDevSheetUrl(String(url || ''))
      if (!target) {
        setSheetMsg('ยังไม่พบลิงก์ดาวน์โหลดสำหรับรายการนี้')
        return
      }
      setSheetMsg(null)
      void (async () => {
        try {
          await downloadAuthorizedFile(target, fileName)
          setSheetMsg(`ดาวน์โหลดไฟล์แล้ว: ${fileName}`)
        } catch (e: any) {
          setSheetMsg(e?.response?.data?.detail || e?.message || 'ดาวน์โหลดไฟล์จาก Google Sheets ไม่สำเร็จ')
        }
      })()
    }, mode)
  }

  async function runSecureAction() {
    const password = securePassword.trim()
    if (!password || !secureAction) return
    if (secureAction === 'backup') {
      setSheetMsg(null)
      setBackupBusy(true)
      try {
        const res = await createDevBackup(password)
        await downloadProtectedFile(res.download_url, res.file_name)
        setSheetMsg(`สร้าง Backup Now และดาวน์โหลดแล้ว: ${res.file_name}`)
      } catch (e: any) {
        setSheetMsg(e?.response?.data?.detail || e?.message || 'สร้าง backup ไม่สำเร็จ')
      } finally {
        setBackupBusy(false)
      }
      return
    }
    if (secureAction === 'restore') {
      if (!restoreFile) {
        setSheetMsg('กรุณาเลือกไฟล์ backup ก่อน')
        return
      }
      setSheetMsg(null)
      setRestoreBusy(true)
      try {
        const res = await restoreDevBackup(password, restoreFile)
        setSheetMsg(`กู้คืน backup แล้ว: users ${res.restored.users || 0}, products ${res.restored.products || 0}, transactions ${res.restored.transactions || 0}`)
        setRestoreFile(null)
        await reload()
        setSheetsCfg(await getDevSheetsConfig())
      } catch (e: any) {
        setSheetMsg(e?.response?.data?.detail || e?.message || 'กู้คืน backup ไม่สำเร็จ')
      } finally {
        setRestoreBusy(false)
      }
      return
    }
    setSheetMsg(null)
    setResetStockBusy(true)
    try {
      const res = await resetStock(password)
      await downloadProtectedFile(res.backup_download_url, res.backup_file_name)
      setSheetMsg(`ล้างสต็อกแล้วและดาวน์โหลด backup ให้แล้ว: สินค้า ${res.deleted_products}, ธุรกรรม ${res.deleted_transactions}`)
      await reload()
    } catch (e: any) {
      setSheetMsg(e?.response?.data?.detail || e?.message || 'ล้างสต็อกไม่สำเร็จ')
    } finally {
      setResetStockBusy(false)
    }
  }

  useEffect(() => {
    reload()
    scanNow()
    void reloadCategoryTools().catch(() => {})
    ;(async () => {
      try {
        const cfg = await getNotificationConfig()
        setNotifEnabled(Boolean(cfg.enabled))
        setNotifLow(cfg.low_levels_pct || [])
        setNotifHigh(cfg.high_levels_pct || [])
        setNotifRoles(cfg.roles || [])
        setNotifTokenStatus(cfg.line_token_status || {})
        setNotifIncludeName(cfg.include_name !== false)
        setNotifIncludeSku(cfg.include_sku !== false)
        setNotifIncludeStatus(cfg.include_status !== false)
        setNotifIncludeCurrentQty(cfg.include_current_qty !== false)
        setNotifIncludeTargetQty(cfg.include_target_qty !== false)
        setNotifIncludeRestockQty(cfg.include_restock_qty !== false)
        setNotifIncludeActor(cfg.include_actor !== false)
        setNotifIncludeReason(cfg.include_reason !== false)
        setNotifIncludeImageUrl(Boolean(cfg.include_image_url))
      } catch (e: any) {
        setNotifMsg(e?.response?.data?.detail || e?.message || 'โหลดการตั้งค่าแจ้งเตือนไม่สำเร็จ')
      }
    })()
    ;(async () => {
      const pending = hasPendingGoogleOauth()
      setGoogleSheetsPending(pending)
      setSheetsLoading(true)
      try {
        let c = await getDevSheetsConfig()
        setSheetsCfg(c)
        if (pending && !c.usable) {
          const startedAt = Date.now()
          while (Date.now() - startedAt < 15_000 && !c.usable) {
            await new Promise((resolve) => window.setTimeout(resolve, 1200))
            c = await getDevSheetsConfig()
            setSheetsCfg(c)
            if (c.usable || c.enabled) break
          }
        }
      } catch {
      } finally {
        if (pending) window.localStorage.removeItem(GOOGLE_OAUTH_PENDING_KEY)
        setGoogleSheetsPending(false)
        setSheetsLoading(false)
      }
    })()
  }, [])

  if (!canUse) {
    return (
      <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-4 text-sm text-white/80">
        หน้านี้สำหรับ DEV เท่านั้น
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">Dev tools</div>
        <div className="mt-1 text-xs text-white/60">Health / Config / Activity / Google Sheets</div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        {false ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/55 backdrop-blur-md">
            <div className="mx-4 max-w-lg rounded-2xl border border-white/10 bg-[color:var(--color-card)]/90 p-6 text-center shadow-2xl">
              <div className="text-lg font-semibold">ยังไม่ได้ตั้งค่า Google Sheets</div>
              <div className="mt-2 text-sm text-white/65">ไปที่หน้า Config เพื่อกำหนด Gmail, path credentials และให้ระบบสร้าง/เชื่อม Google Sheets อัตโนมัติก่อนใช้งานโซนนี้</div>
              <button
                className="mt-4 rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                type="button"
                onClick={() => navigate('/settings#google-setup')}
              >
                ไปตั้งค่า Google ใน Config
              </button>
              <button
                className="rounded border border-amber-400/30 px-3 py-2 text-sm text-amber-100 hover:bg-amber-500/10"
                type="button"
                disabled={sheetAction !== null}
                onClick={async () => {
                  setSheetMsg(null)
                  setSheetAction('force-sync')
                  setSheetMsg('กำลัง Force Full Sync ทั้ง workbook...')
                  try {
                    const res = await forceFullSyncToSheets()
                    setSheetMsg(res.ok ? 'Force Full Sync เสร็จแล้ว' : `Force Full Sync ไม่สำเร็จ: ${res.error || ''}`)
                    setSheetsCfg(await getDevSheetsConfig())
                  } finally {
                    setSheetAction(null)
                  }
                }}
              >
                {sheetAction === 'force-sync' ? 'กำลัง Force Sync...' : 'Force Full Sync'}
              </button>
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Garbage File Management</div>
            <div className="text-xs text-white/60">สแกน temp/cache/log/build เก่า/backup หมดอายุ/duplicate node_modules</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
              type="button"
              onClick={() => setGarbageExpanded((prev) => !prev)}
            >
              {garbageExpanded ? 'ยุบรายการ' : `ดูรายการ (${garbageItems.length})`}
            </button>
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
              type="button"
              onClick={scanNow}
              disabled={garbageBusy}
            >
              {garbageBusy ? 'กำลังสแกน...' : 'สแกนใหม่'}
            </button>
            {garbageItems.length > 0 && (
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={() => {
                  if (selectedPaths.length === garbageItems.length) {
                    setSelectedPaths([])
                  } else {
                    setSelectedPaths(garbageItems.map((x) => x.path))
                  }
                }}
              >
                {selectedPaths.length === garbageItems.length ? 'ยกเลิกเลือกทั้งหมด' : 'เลือกทั้งหมด'}
              </button>
            )}
            <button
              className="rounded bg-red-500/15 px-3 py-2 text-sm font-semibold text-red-100 hover:bg-red-500/25 disabled:opacity-50"
              type="button"
              disabled={garbageItems.length === 0}
              onClick={() => {
                setSelectedPaths(garbageItems.map((x) => x.path))
                setConfirmOpen(true)
              }}
            >
              ลบทั้งหมด
            </button>
            <button
              className="rounded bg-red-500/20 px-3 py-2 text-sm font-semibold text-red-100 hover:bg-red-500/30 disabled:opacity-50"
              type="button"
              disabled={selectedPaths.length === 0}
              onClick={() => setConfirmOpen(true)}
            >
              ลบที่เลือก ({selectedPaths.length})
            </button>
          </div>
        </div>
        {garbageMsg ? <div className="mt-2 text-xs text-yellow-300">{garbageMsg}</div> : null}
        <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 px-3 py-2 text-xs text-white/65">
          พบทั้งหมด <span className="font-semibold text-white">{garbageItems.length}</span> รายการ
          <span className="mx-2 text-white/25">•</span>
          เลือกไว้ <span className="font-semibold text-white">{selectedPaths.length}</span> รายการ
          <span className="mx-2 text-white/25">•</span>
          Whitelist <span className="font-semibold text-white">{whitelist.length}</span> รายการ
        </div>

        {garbageExpanded ? (
          <>
            <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3">
              <div className="mb-2 text-xs text-white/60">Whitelist (รองรับ wildcard เช่น dist/**, **/*.log)</div>
              <div className="flex flex-wrap gap-2">
                <input
                  className="min-w-[240px] flex-1 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={whitelistInput}
                  onChange={(e) => setWhitelistInput(e.target.value)}
                  placeholder="เพิ่ม path หรือ pattern"
                />
                <button
                  className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                  type="button"
                  onClick={async () => {
                    const v = whitelistInput.trim()
                    if (!v) return
                    const next = Array.from(new Set([...whitelist, v]))
                    await updateGarbageWhitelist(next)
                    setWhitelist(next)
                    setWhitelistInput('')
                    await scanNow()
                  }}
                >
                  เพิ่ม
                </button>
              </div>
              {whitelist.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {whitelist.map((w) => (
                    <button
                      key={w}
                      className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/70 hover:bg-white/10"
                      type="button"
                      onClick={async () => {
                        const next = whitelist.filter((x) => x !== w)
                        await updateGarbageWhitelist(next)
                        setWhitelist(next)
                        await scanNow()
                      }}
                    >
                      {w} ✕
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-white/60">
                  <tr className="border-b border-[color:var(--color-border)]">
                    <th className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={garbageItems.length > 0 && selectedPaths.length === garbageItems.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedPaths(garbageItems.map((x) => x.path))
                          } else {
                            setSelectedPaths([])
                          }
                        }}
                      />
                    </th>
                    <th className="px-3 py-2">ประเภท</th>
                    <th className="px-3 py-2">Path</th>
                    <th className="px-3 py-2">ขนาด</th>
                    <th className="px-3 py-2">แก้ไขล่าสุด</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--color-border)]">
                  {garbageItems.map((x) => (
                    <tr
                      key={x.id}
                      className="cursor-pointer hover:bg-white/5"
                      onClick={() => {
                        setSelectedPaths((prev) => {
                          if (prev.includes(x.path)) return prev.filter((p) => p !== x.path)
                          return [...prev, x.path]
                        })
                      }}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selectedPaths.includes(x.path)}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => {
                            const checked = e.target.checked
                            setSelectedPaths((prev) => {
                              if (checked) return prev.includes(x.path) ? prev : [...prev, x.path]
                              return prev.filter((p) => p !== x.path)
                            })
                          }}
                        />
                      </td>
                      <td className="px-3 py-2 text-white/70">{x.category}</td>
                      <td className="px-3 py-2 font-mono text-xs text-white/80">{x.path}</td>
                      <td className="px-3 py-2 text-white/80">{formatSize(x.size_bytes)}</td>
                      <td className="px-3 py-2 text-white/60">{new Date(x.modified_at).toLocaleString()}</td>
                    </tr>
                  ))}
                  {!garbageBusy && garbageItems.length === 0 ? (
                    <tr>
                      <td className="px-3 py-6 text-sm text-white/60" colSpan={5}>
                        ไม่พบไฟล์ขยะตามเงื่อนไข
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="mt-3 rounded border border-dashed border-[color:var(--color-border)] bg-white/5 px-4 py-5 text-sm text-white/55">
            ซ่อนรายละเอียดรายการไว้แล้ว กด “ดูรายการ” เพื่อเปิดตารางไฟล์ขยะและ whitelist
          </div>
        )}
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold">Inventory Categories + Rules</div>
            <div className="text-xs text-white/60">สร้าง/แก้ชื่อ/ลบ/กู้คืนหมวดหมู่สินค้า และตั้งสูตร Min/Max สำหรับหน้าเพิ่มสินค้า</div>
          </div>
          <button
            className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
            type="button"
            onClick={() => void reloadCategoryTools().catch(() => {})}
          >
            รีโหลดหมวดหมู่
          </button>
        </div>
        {categoryMsg ? <div className="mt-3 text-xs text-white/70">{categoryMsg}</div> : null}

        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[420px_minmax(0,1fr)]">
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-4">
            <div className="text-sm font-semibold">สร้างหมวดหมู่ใหม่</div>
            <div className="mt-3 space-y-3">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={categoryName}
                onChange={(e) => setCategoryName(e.target.value)}
                placeholder="ชื่อหมวดหมู่"
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={categoryDescription}
                onChange={(e) => setCategoryDescription(e.target.value)}
                placeholder="รายละเอียด"
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={categorySort}
                onChange={(e) => setCategorySort(e.target.value)}
                inputMode="numeric"
                placeholder="ลำดับแสดงผล"
              />
              <button
                className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-60"
                type="button"
                disabled={categoryBusy}
                onClick={async () => {
                  if (!categoryName.trim()) {
                    setCategoryMsg('กรุณากรอกชื่อหมวดหมู่')
                    return
                  }
                  setCategoryBusy(true)
                  setCategoryMsg('กำลังสร้างหมวดหมู่และกระจายแพตช์...')
                  try {
                    await createProductCategory({
                      name: categoryName.trim(),
                      description: categoryDescription.trim(),
                      sort_order: Number(categorySort || 0),
                    })
                    setCategoryName('')
                    setCategoryDescription('')
                    setCategorySort('0')
                    await reloadCategoryTools()
                    setCategoryMsg('สร้างหมวดหมู่สำเร็จ')
                  } catch (e: any) {
                    setCategoryMsg(e?.response?.data?.detail || e?.message || 'สร้างหมวดหมู่ไม่สำเร็จ')
                  } finally {
                    setCategoryBusy(false)
                  }
                }}
              >
                {categoryBusy ? 'กำลังบันทึก...' : 'สร้างหมวดหมู่'}
              </button>
            </div>

            <div className="mt-6 border-t border-[color:var(--color-border)] pt-4">
              <div className="text-sm font-semibold">สูตรคำนวณ Min / Max</div>
              <div className="mt-2 text-xs text-white/55">Max = จำนวนตั้งต้น x ตัวคูณ, Min = จำนวนตั้งต้น ÷ ตัวหาร</div>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                <input
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={String(inventoryRules.max_multiplier)}
                  onChange={(e) => setInventoryRules((prev) => ({ ...prev, max_multiplier: Number(e.target.value || 0) }))}
                  inputMode="decimal"
                  placeholder="ตัวคูณ Max"
                />
                <input
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={String(inventoryRules.min_divisor)}
                  onChange={(e) => setInventoryRules((prev) => ({ ...prev, min_divisor: Number(e.target.value || 0) }))}
                  inputMode="decimal"
                  placeholder="ตัวหาร Min"
                />
              </div>
              <button
                className="mt-3 rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-60"
                type="button"
                disabled={categoryBusy}
                onClick={async () => {
                  setCategoryBusy(true)
                  setCategoryMsg('กำลังอัปเดตสูตร...')
                  try {
                    const next = await updateInventoryRuleSettings(inventoryRules)
                    setInventoryRules(next)
                    setCategoryMsg('บันทึกสูตรคำนวณแล้ว')
                  } catch (e: any) {
                    setCategoryMsg(e?.response?.data?.detail || e?.message || 'อัปเดตสูตรไม่สำเร็จ')
                  } finally {
                    setCategoryBusy(false)
                  }
                }}
              >
                บันทึกสูตรคำนวณ
              </button>
            </div>
          </div>

          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-4">
            <div className="text-sm font-semibold">รายการหมวดหมู่ทั้งหมด</div>
            <div className="mt-3 space-y-3">
              {categoryItems.length === 0 ? (
                <div className="rounded border border-dashed border-[color:var(--color-border)] px-4 py-6 text-sm text-white/45">
                  ยังไม่มีหมวดหมู่สินค้า
                </div>
              ) : (
                categoryItems.map((item) => (
                  <div key={item.id} className="rounded border border-[color:var(--color-border)] bg-white/5 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="font-semibold">{item.name}</div>
                          {item.is_deleted ? <span className="rounded bg-red-500/15 px-2 py-0.5 text-xs text-red-200">ลบแล้ว</span> : null}
                          <span className="rounded bg-white/10 px-2 py-0.5 text-xs text-white/60">sort {item.sort_order}</span>
                        </div>
                        <div className="mt-1 text-xs text-white/55">{item.description || 'ไม่มีรายละเอียด'}</div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {!item.is_deleted ? (
                          <>
                            <button
                              className="rounded border border-[color:var(--color-border)] px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
                              type="button"
                              onClick={async () => {
                                const nextName = window.prompt('แก้ชื่อหมวดหมู่', item.name)
                                if (nextName == null) return
                                const nextDescription = window.prompt('แก้รายละเอียด', item.description || '') ?? item.description
                                const nextSort = window.prompt('ลำดับแสดงผล', String(item.sort_order ?? 0))
                                setCategoryBusy(true)
                                setCategoryMsg('กำลังอัปเดตหมวดหมู่...')
                                try {
                                  await updateProductCategory(item.id, {
                                    name: nextName.trim(),
                                    description: nextDescription.trim(),
                                    sort_order: Number(nextSort || 0),
                                  })
                                  await reloadCategoryTools()
                                  setCategoryMsg('อัปเดตหมวดหมู่แล้ว')
                                } catch (e: any) {
                                  setCategoryMsg(e?.response?.data?.detail || e?.message || 'อัปเดตหมวดหมู่ไม่สำเร็จ')
                                } finally {
                                  setCategoryBusy(false)
                                }
                              }}
                            >
                              แก้ไขชื่อ
                            </button>
                            <button
                              className="rounded border border-red-500/30 px-3 py-1.5 text-xs text-red-200 hover:bg-red-500/10"
                              type="button"
                              onClick={async () => {
                                const ok = window.confirm(`ลบหมวดหมู่ ${item.name}? สินค้าจะย้ายไปไม่ระบุหมวด`)
                                if (!ok) return
                                setCategoryBusy(true)
                                setCategoryMsg('กำลังลบหมวดหมู่และย้ายสินค้า...')
                                try {
                                  await deleteProductCategory(item.id)
                                  await reloadCategoryTools()
                                  setCategoryMsg('ลบหมวดหมู่แล้ว สินค้าย้ายไปไม่ระบุหมวด')
                                } catch (e: any) {
                                  setCategoryMsg(e?.response?.data?.detail || e?.message || 'ลบหมวดหมู่ไม่สำเร็จ')
                                } finally {
                                  setCategoryBusy(false)
                                }
                              }}
                            >
                              ลบหมวด
                            </button>
                          </>
                        ) : (
                          <button
                            className="rounded border border-emerald-500/30 px-3 py-1.5 text-xs text-emerald-200 hover:bg-emerald-500/10"
                            type="button"
                            onClick={async () => {
                              setCategoryBusy(true)
                              setCategoryMsg('กำลังกู้คืนหมวดหมู่...')
                              try {
                                await restoreProductCategory(item.id)
                                await reloadCategoryTools()
                                setCategoryMsg('กู้คืนหมวดหมู่แล้ว')
                              } catch (e: any) {
                                setCategoryMsg(e?.response?.data?.detail || e?.message || 'กู้คืนหมวดหมู่ไม่สำเร็จ')
                              } finally {
                                setCategoryBusy(false)
                              }
                            }}
                          >
                            กู้คืนหมวด
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Notification Percentage</div>
            <div className="text-xs text-white/60">
              ตั้งค่าเปอร์เซ็นต์หลายระดับสำหรับแจ้งเตือนเมื่อสต็อก “ขึ้นถึง/ลงถึง” เกณฑ์ที่กำหนด (อิงจาก stock/max_stock)
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-white/80">
              <input type="checkbox" checked={notifEnabled} onChange={(e) => setNotifEnabled(e.target.checked)} /> เปิดใช้งาน
            </label>
            <button
              className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-50"
              type="button"
              disabled={notifBusy}
              onClick={async () => {
                setNotifBusy(true)
                setNotifMsg(null)
                try {
                  if (notifRoles.length === 0) {
                    setNotifMsg('กรุณาเลือกอย่างน้อย 1 Role ที่จะรับการแจ้งเตือน')
                    return
                  }
                  const res = await updateNotificationConfig({
                    enabled: notifEnabled,
                    low_levels_pct: notifLow,
                    high_levels_pct: notifHigh,
                    roles: notifRoles,
                    line_tokens: notifLineTokens,
                    include_name: notifIncludeName,
                    include_sku: notifIncludeSku,
                    include_status: notifIncludeStatus,
                    include_current_qty: notifIncludeCurrentQty,
                    include_target_qty: notifIncludeTargetQty,
                    include_restock_qty: notifIncludeRestockQty,
                    include_actor: notifIncludeActor,
                    include_reason: notifIncludeReason,
                    include_image_url: notifIncludeImageUrl,
                  })
                  setNotifEnabled(Boolean(res.enabled))
                  setNotifLow(res.low_levels_pct || [])
                  setNotifHigh(res.high_levels_pct || [])
                  setNotifRoles(res.roles || [])
                  setNotifTokenStatus(res.line_token_status || {})
                  setNotifLineTokens({})
                  setNotifIncludeName(res.include_name !== false)
                  setNotifIncludeSku(res.include_sku !== false)
                  setNotifIncludeStatus(res.include_status !== false)
                  setNotifIncludeCurrentQty(res.include_current_qty !== false)
                  setNotifIncludeTargetQty(res.include_target_qty !== false)
                  setNotifIncludeRestockQty(res.include_restock_qty !== false)
                  setNotifIncludeActor(res.include_actor !== false)
                  setNotifIncludeReason(res.include_reason !== false)
                  setNotifIncludeImageUrl(Boolean(res.include_image_url))
                  setNotifMsg('บันทึกการตั้งค่าแจ้งเตือนแล้ว')
                } catch (e: any) {
                  setNotifMsg(e?.response?.data?.detail || e?.message || 'บันทึกการตั้งค่าแจ้งเตือนไม่สำเร็จ')
                } finally {
                  setNotifBusy(false)
                }
              }}
            >
              {notifBusy ? 'กำลังบันทึก...' : 'บันทึก'}
            </button>
          </div>
        </div>
        {notifMsg ? <div className="mt-2 text-xs text-yellow-300">{notifMsg}</div> : null}

        <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3">
          <div className="text-xs text-white/60">ตั้งค่าด่วน</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-xs text-white/80 hover:bg-white/10"
              type="button"
              onClick={() => {
                setNotifLow([50, 20, 10, 0])
                setNotifHigh([80, 90, 100])
                setNotifMsg('โหลดชุดแจ้งเตือนพื้นฐานแล้ว')
              }}
            >
              พื้นฐานร้านทั่วไป
            </button>
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-xs text-white/80 hover:bg-white/10"
              type="button"
              onClick={() => {
                setNotifLow([70, 50, 30, 15, 5, 0])
                setNotifHigh([60, 80, 90, 100])
                setNotifMsg('โหลดชุดแจ้งเตือนละเอียดแล้ว')
              }}
            >
              ละเอียดมาก
            </button>
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-xs text-white/80 hover:bg-white/10"
              type="button"
              onClick={() => {
                setNotifLow([30, 10, 0])
                setNotifHigh([95, 100])
                setNotifMsg('โหลดชุดแจ้งเตือนแบบกระชับแล้ว')
              }}
            >
              กระชับ
            </button>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs font-semibold text-white/80">โซนแจ้งเตือนฝั่งสต็อกลดลง</div>
            <div className="mt-1 text-xs text-white/50">กำหนดว่าเมื่อสต็อกเหลือต่ำกว่ากี่ % ของจำนวนที่ควรมี ให้แจ้งเตือนทันที</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                className="w-28 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={notifLowInput}
                onChange={(e) => setNotifLowInput(e.target.value)}
                placeholder="เช่น 20"
                inputMode="numeric"
              />
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={() => {
                  const n = Number(notifLowInput)
                  if (!Number.isFinite(n) || n < 0 || n > 100) {
                    setNotifMsg('เปอร์เซ็นต์ต้องอยู่ระหว่าง 0 ถึง 100')
                    return
                  }
                  const v = Math.round(n)
                  setNotifLow((prev) => Array.from(new Set([...prev, v])).sort((a, b) => b - a))
                  setNotifLowInput('')
                  setNotifMsg(null)
                }}
              >
                เพิ่ม
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {notifLow.map((x) => (
                <button
                  key={x}
                  className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/70 hover:bg-white/10"
                  type="button"
                  onClick={() => setNotifLow((prev) => prev.filter((v) => v !== x))}
                >
                  {x}% ✕
                </button>
              ))}
              {notifLow.length === 0 ? <div className="text-xs text-white/50">ยังไม่ได้ตั้งค่า</div> : null}
            </div>
          </div>

          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs font-semibold text-white/80">โซนแจ้งเตือนฝั่งสต็อกเพิ่มขึ้น</div>
            <div className="mt-1 text-xs text-white/50">ใช้ติดตามว่าเติมของกลับมาถึงระดับไหนแล้ว เช่น 80%, 90%, 100%</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                className="w-28 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={notifHighInput}
                onChange={(e) => setNotifHighInput(e.target.value)}
                placeholder="เช่น 90"
                inputMode="numeric"
              />
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={() => {
                  const n = Number(notifHighInput)
                  if (!Number.isFinite(n) || n < 0 || n > 100) {
                    setNotifMsg('เปอร์เซ็นต์ต้องอยู่ระหว่าง 0 ถึง 100')
                    return
                  }
                  const v = Math.round(n)
                  setNotifHigh((prev) => Array.from(new Set([...prev, v])).sort((a, b) => a - b))
                  setNotifHighInput('')
                  setNotifMsg(null)
                }}
              >
                เพิ่ม
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {notifHigh.map((x) => (
                <button
                  key={x}
                  className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/70 hover:bg-white/10"
                  type="button"
                  onClick={() => setNotifHigh((prev) => prev.filter((v) => v !== x))}
                >
                  {x}% ✕
                </button>
              ))}
              {notifHigh.length === 0 ? <div className="text-xs text-white/50">ยังไม่ได้ตั้งค่า</div> : null}
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
          <div className="rounded border border-green-500/30 bg-green-500/10 p-3 text-xs text-green-100">
            <div className="font-semibold">สีเขียว</div>
            <div className="mt-1 text-green-100/80">ปกติหรือพร้อมใช้งาน</div>
          </div>
          <div className="rounded border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-100">
            <div className="font-semibold">สีเหลือง</div>
            <div className="mt-1 text-yellow-100/80">เริ่มเข้าใกล้จุดเตือน</div>
          </div>
          <div className="rounded border border-orange-500/30 bg-orange-500/10 p-3 text-xs text-orange-100">
            <div className="font-semibold">สีส้ม</div>
            <div className="mt-1 text-orange-100/80">ควรเติมหรือควรเช็กทันที</div>
          </div>
          <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-100">
            <div className="font-semibold">สีแดง</div>
            <div className="mt-1 text-red-100/80">สำคัญมากหรือสต็อกหมด</div>
          </div>
        </div>

        <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3">
          <div className="text-xs text-white/60">Role ที่จะรับการแจ้งเตือน</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {(['OWNER', 'ADMIN', 'STOCK', 'ACCOUNTANT', 'DEV'] as const).map((r) => (
              <button
                key={r}
                className={`rounded px-3 py-2 text-sm ${
                  notifRoles.includes(r)
                    ? 'bg-[color:var(--color-primary)] text-black'
                    : 'border border-[color:var(--color-border)] text-white/80 hover:bg-white/10'
                }`}
                type="button"
                onClick={() => {
                  setNotifRoles((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]))
                }}
              >
                {r}
              </button>
            ))}
          </div>
          <div className="mt-2 text-xs text-white/50">
            หมายเหตุ: การแจ้งเตือนจะส่งผ่าน LINE Notify ตาม token ของ role ที่ตั้งไว้ใน config.json
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs font-semibold text-white/80">รายละเอียดที่ให้แจ้งใน LINE</div>
            <div className="mt-1 text-xs text-white/50">เลือกได้หลายหัวข้อ และ token สามารถเป็น token ของ LINE ส่วนตัวหรือ group ที่สร้างไว้ได้</div>
            <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
              {[
                { label: 'ชื่อสินค้า', checked: notifIncludeName, setter: setNotifIncludeName },
                { label: 'SKU', checked: notifIncludeSku, setter: setNotifIncludeSku },
                { label: 'สถานะ', checked: notifIncludeStatus, setter: setNotifIncludeStatus },
                { label: 'จำนวนคงเหลือ', checked: notifIncludeCurrentQty, setter: setNotifIncludeCurrentQty },
                { label: 'จำนวนที่ควรมี', checked: notifIncludeTargetQty, setter: setNotifIncludeTargetQty },
                { label: 'จำนวนที่ต้องเติม', checked: notifIncludeRestockQty, setter: setNotifIncludeRestockQty },
                { label: 'ผู้ทำรายการ', checked: notifIncludeActor, setter: setNotifIncludeActor },
                { label: 'เหตุผล/หมายเหตุ', checked: notifIncludeReason, setter: setNotifIncludeReason },
                { label: 'ลิงก์รูปสินค้า', checked: notifIncludeImageUrl, setter: setNotifIncludeImageUrl },
              ].map((item) => (
                <label key={item.label} className="flex items-center gap-2 rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80">
                  <input type="checkbox" checked={item.checked} onChange={(e) => item.setter(e.target.checked)} />
                  {item.label}
                </label>
              ))}
            </div>
          </div>

          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs font-semibold text-white/80">จัดการ LINE Token แยกตาม Role</div>
            <div className="mt-1 text-xs text-white/50">กดเลือก role แล้วระบบจะให้กรอก token แบบ popup ก่อนบันทึก</div>
            <div className="mt-3 space-y-2">
              {(['OWNER', 'ADMIN', 'STOCK', 'ACCOUNTANT', 'DEV'] as const).map((roleName) => (
                <div key={roleName} className="flex items-center justify-between gap-2 rounded border border-[color:var(--color-border)] px-3 py-2">
                  <div>
                    <div className="text-sm font-semibold">{roleName}</div>
                    <div className="text-xs text-white/50">{notifTokenStatus[roleName] ? `ตั้งค่าแล้ว: ${notifTokenStatus[roleName]}` : 'ยังไม่มี token'}</div>
                  </div>
                  <button
                    className="rounded border border-[color:var(--color-border)] px-3 py-2 text-xs text-white/80 hover:bg-white/10"
                    type="button"
                    onClick={() => {
                      setNotifTokenRole(roleName)
                      setNotifTokenInput('')
                    }}
                  >
                    ตั้งค่า Token
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {notifTokenRole ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="w-full max-w-md rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="border-b border-[color:var(--color-border)] px-5 py-4 text-sm font-semibold">ตั้งค่า LINE Token สำหรับ {notifTokenRole}</div>
              <div className="space-y-3 px-5 py-4">
                <div className="text-sm text-white/70">รองรับ token ที่ใช้แจ้งเข้า LINE ส่วนตัวหรือ LINE Group ที่สร้าง token ไว้แล้ว</div>
                <input
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={notifTokenInput}
                  onChange={(e) => setNotifTokenInput(e.target.value)}
                  placeholder="วาง LINE token ที่นี่"
                />
              </div>
              <div className="flex justify-end gap-2 border-t border-[color:var(--color-border)] px-5 py-4">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  type="button"
                  onClick={() => {
                    setNotifTokenRole(null)
                    setNotifTokenInput('')
                  }}
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                  type="button"
                  onClick={() => {
                    setNotifLineTokens((prev) => ({ ...prev, [notifTokenRole]: notifTokenInput.trim() }))
                    setNotifTokenStatus((prev) => ({ ...prev, [notifTokenRole]: notifTokenInput.trim() ? `${notifTokenInput.trim().slice(0, 4)}...${notifTokenInput.trim().slice(-4)}` : '' }))
                    setNotifTokenRole(null)
                    setNotifTokenInput('')
                    setNotifMsg(`เตรียม token สำหรับ ${notifTokenRole} แล้ว กดบันทึกเพื่อใช้งานจริง`)
                  }}
                >
                  ใช้ Token นี้
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {sheetGuardOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-4 backdrop-blur-md">
          <div className="flex min-h-full items-center justify-center">
            <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[color:var(--color-card)]/95 p-6 text-center shadow-2xl">
              <div className="text-xl font-semibold">ยังไม่ได้ sync Google Sheets</div>
              <div className="mt-2 text-sm text-white/65">
                {sheetGuardMode === 'missing'
                  ? 'โซนนี้ใช้ข้อมูลที่เก็บกับ Google Sheets กรุณาเชื่อม Google หรือ Sync ให้พร้อมก่อนใช้งาน'
                  : 'กรุณา Sync Google Sheets ก่อน เพื่อให้ข้อมูลล่าสุดพร้อมสำหรับการเปิดดูหรือดาวน์โหลด'}
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  type="button"
                  onClick={() => {
                    setSheetGuardOpen(false)
                    navigate('/settings#google-setup')
                  }}
                >
                  ไปตั้งค่า Google
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                  type="button"
                  onClick={async () => {
                    setSheetGuardOpen(false)
                    setSheetMsg('กำลัง Sync ไปชีต...')
                    setSheetAction('sync')
                    try {
                      const res = await syncToSheets()
                      setSheetMsg(res.ok ? 'Sync ไปชีตเสร็จแล้ว' : `Sync ไม่สำเร็จ: ${res.error || ''}`)
                      setSheetsCfg(await getDevSheetsConfig())
                    } finally {
                      setSheetAction(null)
                    }
                  }}
                >
                  ไป Sync Google Sheets
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {secureAction ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="w-full max-w-md rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="border-b border-[color:var(--color-border)] px-5 py-4 text-sm font-semibold">
                {secureAction === 'backup' ? 'ยืนยันสร้าง Backup Now' : secureAction === 'restore' ? 'ยืนยันกู้คืน Backup' : 'ยืนยันล้าง Stock'}
              </div>
              <div className="space-y-3 px-5 py-4">
                <div className="text-sm text-white/70">
                  {secureAction === 'backup'
                    ? 'กรอกรหัสเพื่อสร้างไฟล์ backup แบบ realtime แล้วดาวน์โหลดทันที'
                    : secureAction === 'restore'
                      ? `กรอกรหัสเพื่อกู้คืนจากไฟล์ ${restoreFile?.name || '-'} และแทนที่ข้อมูลทั้งหมดในระบบ`
                      : 'กรอกรหัสเพื่อสำรองข้อมูลก่อน แล้วล้างสินค้า/ธุรกรรม/alert ทั้งหมดโดยคงผู้ใช้ไว้'}
                </div>
                <input
                  type="password"
                  value={securePassword}
                  onChange={(e) => setSecurePassword(e.target.value)}
                  placeholder="กรอกรหัสยืนยัน"
                  className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                />
                <div className="text-xs text-white/45">ต้องใช้รหัส: phanthakorn</div>
              </div>
              <div className="flex justify-end gap-2 border-t border-[color:var(--color-border)] px-5 py-4">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  type="button"
                  onClick={() => {
                    setSecureAction(null)
                    setSecurePassword('')
                  }}
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-50"
                  type="button"
                  disabled={!securePassword.trim() || backupBusy || restoreBusy || resetStockBusy}
                  onClick={async () => {
                    await runSecureAction()
                    setSecureAction(null)
                    setSecurePassword('')
                  }}
                >
                  ยืนยัน
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {confirmOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-4 backdrop-blur-sm">
          <div className="flex min-h-full items-center justify-center">
            <div className="w-full max-w-2xl rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl">
              <div className="border-b border-[color:var(--color-border)] px-5 py-4 text-sm font-semibold">ยืนยันลบไฟล์ขยะ</div>
              <div className="space-y-3 px-5 py-4">
                <div className="text-sm text-white/80">
                  กำลังจะลบ {selectedPaths.length} ไฟล์/โฟลเดอร์ ขนาดรวม{' '}
                  {formatSize(
                    garbageItems.filter((x) => selectedPaths.includes(x.path)).reduce((s, x) => s + x.size_bytes, 0)
                  )}
                </div>
                <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3 text-xs text-white/60">
                  แนะนำโหมด Backup ก่อน เพื่อย้ายไฟล์ไปโฟลเดอร์สำรองและสามารถนำกลับได้
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className={`rounded px-3 py-2 text-sm ${deleteMode === 'backup' ? 'bg-[color:var(--color-primary)] text-black' : 'border border-[color:var(--color-border)] text-white/80'}`}
                    type="button"
                    onClick={() => setDeleteMode('backup')}
                  >
                    Backup ก่อนลบ
                  </button>
                  <button
                    className={`rounded px-3 py-2 text-sm ${deleteMode === 'permanent' ? 'bg-red-500/25 text-red-100' : 'border border-[color:var(--color-border)] text-white/80'}`}
                    type="button"
                    onClick={() => setDeleteMode('permanent')}
                  >
                    ลบถาวร
                  </button>
                </div>
              </div>
              <div className="flex justify-end gap-2 border-t border-[color:var(--color-border)] px-5 py-4">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  type="button"
                  onClick={() => setConfirmOpen(false)}
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-red-500/25 px-4 py-2 text-sm font-semibold text-red-100 hover:bg-red-500/35"
                  type="button"
                  onClick={async () => {
                    try {
                      const res = await deleteGarbage(selectedPaths, deleteMode, true)
                      setGarbageMsg(
                        res.ok
                          ? `ลบสำเร็จ ${res.deleted_count} รายการ${res.moved_to_backup && res.backup_path ? ` (สำรองไว้ที่ ${res.backup_path})` : ''}`
                          : `ลบบางส่วนไม่สำเร็จ: ${res.errors?.[0] || ''}`
                      )
                    } catch (e: any) {
                      setGarbageMsg(e?.response?.data?.detail || e?.message || 'ลบไฟล์ไม่สำเร็จ')
                    } finally {
                      setConfirmOpen(false)
                      await scanNow()
                    }
                  }}
                >
                  ยืนยันลบ
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">Health</div>
          <div className="mt-2 text-xs text-white/60">{busy ? 'กำลังโหลด...' : JSON.stringify(health)}</div>
          <button
            className="mt-3 rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
            type="button"
            onClick={reload}
          >
            รีเฟรช
          </button>
        </div>

        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">Config (public)</div>
          <div className="mt-2 text-xs text-white/60 break-words">{busy ? 'กำลังโหลด...' : JSON.stringify(config)}</div>
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Sheets Center + Backup Control</div>
            <div className="text-xs text-white/60">ใช้งานหลักผ่านเว็บ แต่จัดเก็บ/เรียงข้อมูลสำคัญไว้ใน Google Sheets และ Backup แบบไฟล์ ZIP</div>
          </div>
          {sheetsCfg?.usable ? (
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                disabled={sheetAction !== null}
                onClick={async () => {
                  setSheetMsg(null)
                  setSheetAction('sync')
                  setSheetMsg('กำลัง Sync ไปชีต...')
                  try {
                    const res = await syncToSheets()
                    setSheetMsg(res.ok ? 'Sync ไปชีตเสร็จแล้ว' : `Sync ไม่สำเร็จ: ${res.error || ''}`)
                    setSheetsCfg(await getDevSheetsConfig())
                  } finally {
                    setSheetAction(null)
                  }
                }}
              >
                {sheetAction === 'sync' ? 'กำลัง Sync...' : 'Sync ไปชีตตอนนี้'}
              </button>
              <button
                className="rounded border border-amber-400/30 px-3 py-2 text-sm text-amber-100 hover:bg-amber-500/10 disabled:opacity-60"
                type="button"
                disabled={sheetAction !== null}
                onClick={async () => {
                  setSheetMsg(null)
                  setSheetAction('force-sync')
                  setSheetMsg('กำลัง Force Full Sync ทั้ง workbook...')
                  try {
                    const res = await forceFullSyncToSheets()
                    setSheetMsg(res.ok ? 'Force Full Sync เสร็จแล้ว' : `Force Full Sync ไม่สำเร็จ: ${res.error || ''}`)
                    setSheetsCfg(await getDevSheetsConfig())
                  } finally {
                    setSheetAction(null)
                  }
                }}
              >
                {sheetAction === 'force-sync' ? 'กำลัง Force Sync...' : 'Force Full Sync'}
              </button>
              <button
                className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90"
                type="button"
                disabled={sheetAction !== null}
                onClick={async () => {
                  setSheetMsg(null)
                  setSheetAction('import')
                  setSheetMsg('กำลัง Import Stock → DB...')
                  try {
                    const res = await importFromSheets({ overwrite_stock_qty: false, overwrite_prices: false })
                    setSheetMsg(res.ok ? `นำเข้าเสร็จ: สร้าง ${res.created || 0}, อัปเดต ${res.updated || 0}, ข้าม ${res.skipped || 0}` : `นำเข้าไม่สำเร็จ: ${res.error || ''}`)
                    await reload()
                  } finally {
                    setSheetAction(null)
                  }
                }}
              >
                {sheetAction === 'import' ? 'กำลัง Import...' : 'Import Stock → DB'}
              </button>
            </div>
          ) : sheetsLoading || googleSheetsPending ? (
            <button
              className="rounded border border-sky-400/30 px-4 py-2 text-sm font-semibold text-sky-100"
              type="button"
              disabled
            >
              กำลังโหลดข้อมูล Google Sheets...
            </button>
          ) : (
            <button
              className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
              type="button"
              onClick={() => navigate('/settings#google-setup')}
            >
              ไปเชื่อม Google ใน Config
            </button>
          )}
        </div>
        {sheetMsg ? <div className="mt-2 text-xs text-white/70">{sheetMsg}</div> : null}

        {sheetsCfg?.usable ? (
          <>
            <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3">
              <div className="text-xs text-white/60">Google Sheets หลักของระบบ</div>
              <div className="mt-2 text-xs text-white/50 break-words">
                sheet_id: {sheetsCfg?.sheet_id ? sheetsCfg.sheet_id : '-'} | key: {sheetsCfg?.key_path ? sheetsCfg.key_path : '-'}
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded border border-green-500/30 bg-green-500/10 p-3">
                  <div className="text-sm font-semibold text-green-100">โซน Stock</div>
                  <div className="mt-1 text-xs text-green-100/80">ดูสต็อกหลัก สถานะ สี และรายการที่ควรเติม</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="rounded border border-green-400/30 px-3 py-2 text-xs text-green-50 hover:bg-green-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.stock_tab_url, 'sync')}>
                      เปิดแท็บสต็อก
                    </button>
                    <button className="rounded border border-green-400/30 px-3 py-2 text-xs text-green-50 hover:bg-green-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.download_xlsx_url, 'sync')}>
                      โหลดทั้งชีต .xlsx
                    </button>
                    <button className="rounded border border-green-400/30 px-3 py-2 text-xs text-green-50 hover:bg-green-500/10" type="button" onClick={() => downloadSheetFile(sheetsCfg?.stock_download_url, 'stock-summary.csv', 'sync')}>
                      โหลดเฉพาะสต็อก .csv
                    </button>
                  </div>
                </div>
                <div className="rounded border border-violet-500/30 bg-violet-500/10 p-3">
                  <div className="text-sm font-semibold text-violet-100">โซนบัญชี</div>
                  <div className="mt-1 text-xs text-violet-100/80">แยกสรุปบัญชี รายรับ รายจ่าย และภาพรวมมูลค่าสต็อก</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="rounded border border-violet-400/30 px-3 py-2 text-xs text-violet-50 hover:bg-violet-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.accounting_tab_url, 'sync')}>
                      เปิดแท็บบัญชี
                    </button>
                    <button className="rounded border border-violet-400/30 px-3 py-2 text-xs text-violet-50 hover:bg-violet-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.sheet_url, 'sync')}>
                      เปิดสมุดทั้งหมด
                    </button>
                    <button className="rounded border border-violet-400/30 px-3 py-2 text-xs text-violet-50 hover:bg-violet-500/10" type="button" onClick={() => downloadSheetFile(sheetsCfg?.accounting_download_url, 'accounting-summary.csv', 'sync')}>
                      โหลดเฉพาะบัญชี .csv
                    </button>
                  </div>
                </div>
                <div className="rounded border border-red-500/30 bg-red-500/10 p-3">
                  <div className="text-sm font-semibold text-red-100">โซน Log</div>
                  <div className="mt-1 text-xs text-red-100/80">เก็บการแก้ไขสำคัญ Add/Edit/Sell/Audit แยกหัวข้อให้อ่านง่าย</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="rounded border border-red-400/30 px-3 py-2 text-xs text-red-50 hover:bg-red-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.logs_tab_url, 'sync')}>
                      เปิดแท็บ Log
                    </button>
                    <button className="rounded border border-red-400/30 px-3 py-2 text-xs text-red-50 hover:bg-red-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.download_xlsx_url, 'sync')}>
                      โหลดทั้งชีต .xlsx
                    </button>
                    <button className="rounded border border-red-400/30 px-3 py-2 text-xs text-red-50 hover:bg-red-500/10" type="button" onClick={() => downloadSheetFile(sheetsCfg?.logs_download_url, 'audit-log.csv', 'sync')}>
                      โหลดเฉพาะ Log .csv
                    </button>
                  </div>
                </div>
                <div className="rounded border border-sky-500/30 bg-sky-500/10 p-3">
                  <div className="text-sm font-semibold text-sky-100">โซนบัญชีผู้ใช้</div>
                  <div className="mt-1 text-xs text-sky-100/80">รวมข้อมูลบัญชีของผู้ใช้ในระบบเพื่อใช้ดูสรุปและ export เป็นไฟล์</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="rounded border border-sky-400/30 px-3 py-2 text-xs text-sky-50 hover:bg-sky-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.users_tab_url, 'sync')}>
                      เปิดแท็บผู้ใช้
                    </button>
                    <button className="rounded border border-sky-400/30 px-3 py-2 text-xs text-sky-50 hover:bg-sky-500/10" type="button" onClick={() => openSheetUrl(sheetsCfg?.download_xlsx_url, 'sync')}>
                      โหลดทั้งชีต .xlsx
                    </button>
                    <button className="rounded border border-sky-400/30 px-3 py-2 text-xs text-sky-50 hover:bg-sky-500/10" type="button" onClick={() => downloadSheetFile(sheetsCfg?.users_download_url, 'user-accounts.csv', 'sync')}>
                      โหลดบัญชีผู้ใช้ .csv
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3">
              <div className="text-xs text-white/60">สร้าง Google Sheet ใหม่และตั้งค่าให้ระบบ</div>
              <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-5">
                <input
                  className="md:col-span-2 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={sheetCreateTitle}
                  onChange={(e) => setSheetCreateTitle(e.target.value)}
                  placeholder="ชื่อชีตใหม่ (เช่น Stock Penaek)"
                />
                <input
                  className="md:col-span-2 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                  value={sheetShareEmails}
                  onChange={(e) => setSheetShareEmails(e.target.value)}
                  placeholder="แชร์ให้ (คั่นด้วย ,) เช่น you@gmail.com"
                />
                <button
                  className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-50"
                  type="button"
                  disabled={sheetCreateBusy}
                  onClick={async () => {
                    setSheetMsg(null)
                    setSheetCreateBusy(true)
                    try {
                      const emails = sheetShareEmails
                        .split(',')
                        .map((x) => x.trim())
                        .filter(Boolean)
                      const res = await createDevSheet({ title: sheetCreateTitle.trim(), share_emails: emails, set_as_default: true })
                      setLastCreatedSheet(res)
                      setSheetMsg('กำลัง Sync ไปชีตใหม่...')
                      try {
                        const s = await syncToSheets()
                        setSheetMsg(s.ok ? `สร้างชีตใหม่และ Sync แล้ว: ${res.sheet_id}` : `สร้างชีตใหม่แล้ว แต่ Sync ไม่สำเร็จ: ${s.error || ''}`)
                      } catch {
                        setSheetMsg(`สร้างชีตใหม่แล้ว แต่ Sync ไม่สำเร็จ`)
                      }
                      setSheetsCfg(await getDevSheetsConfig())
                    } catch (e: any) {
                      setSheetMsg(e?.response?.data?.detail || e?.message || 'สร้างชีตไม่สำเร็จ')
                    } finally {
                      setSheetCreateBusy(false)
                    }
                  }}
                >
                  {sheetCreateBusy ? 'กำลังสร้าง/Sync...' : 'สร้างชีตใหม่ + Sync'}
                </button>
              </div>
              {lastCreatedSheet ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                    type="button"
                    onClick={() => openSheetUrl(lastCreatedSheet.sheet_url, 'sync')}
                  >
                    เปิดชีตที่สร้างล่าสุด
                  </button>
                  <button
                    className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                    type="button"
                    onClick={() => openSheetUrl(lastCreatedSheet.download_xlsx_url, 'sync')}
                  >
                    ดาวน์โหลดชีตล่าสุด (.xlsx)
                  </button>
                </div>
              ) : null}
            </div>
          </>
        ) : sheetsLoading || googleSheetsPending ? (
          <div className="mt-3 relative overflow-hidden rounded border border-sky-500/30 bg-sky-500/10 p-5">
            <div className="absolute inset-0 bg-black/35 backdrop-blur-sm" />
            <div className="relative text-center">
              <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-white/20 border-t-[color:var(--color-primary)]" />
              <div className="text-base font-semibold text-sky-100">กำลังโหลดข้อมูล Google Sheets</div>
              <div className="mt-2 text-sm text-sky-50/85">เชื่อม Google แล้ว ระบบกำลังดึงสถานะล่าสุดและเตรียมข้อมูลให้พร้อมใช้งาน กรุณารอสักครู่โดยไม่ต้องกดเชื่อมซ้ำ</div>
            </div>
          </div>
        ) : (
          <div className="mt-3 relative overflow-hidden rounded border border-[color:var(--color-border)] bg-black/20 p-5">
            <div className="absolute inset-0 bg-black/55 backdrop-blur-md" />
            <div className="relative text-center">
              <div className="text-base font-semibold">ปิดโซน Google Sheets ชั่วคราว</div>
              <div className="mt-2 text-sm text-white/65">ยังไม่สามารถเชื่อม/Sync Google Sheets ได้ ระบบจึงซ่อนโซนนี้ไว้ก่อน</div>
              <div className="mt-1 text-xs text-white/45">สถานะ: {sheetsCfg?.error || 'not_configured'}</div>
              <button
                className="mt-4 rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                type="button"
                onClick={() => navigate('/settings#google-setup')}
              >
                ไปเชื่อม Google ใน Config
              </button>
            </div>
          </div>
        )}

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded border border-blue-500/30 bg-blue-500/10 p-3">
            <div className="text-sm font-semibold text-blue-100">Backup Now</div>
            <div className="mt-1 text-xs text-blue-100/80">สร้างไฟล์ ZIP ของข้อมูลทั้งระบบ ณ ตอนนั้น แล้วดาวน์โหลดทันที</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                className="rounded bg-blue-500 px-3 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                type="button"
                disabled={backupBusy}
                onClick={() => {
                  setSecurePassword('')
                  setSecureAction('backup')
                }}
              >
                {backupBusy ? 'กำลังสร้าง...' : 'โหลด Backup Now'}
              </button>
            </div>
          </div>

          <div className="rounded border border-amber-500/30 bg-amber-500/10 p-3">
            <div className="text-sm font-semibold text-amber-100">Restore Backup</div>
            <div className="mt-1 text-xs text-amber-100/80">เลือกไฟล์ backup ZIP แล้วแทนที่ข้อมูลทั้งหมดในระบบให้ตรงกับ backup</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <input
                type="file"
                accept=".zip,application/zip"
                className="min-w-[240px] flex-1 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm text-white/80 file:mr-3 file:rounded file:border file:border-[color:var(--color-border)] file:bg-black/40 file:px-3 file:py-1.5"
                onChange={async (e) => {
                  const file = e.target.files?.[0] || null
                  setRestoreFile(file)
                  setRestorePreview(null)
                  if (!file) return
                  try {
                    const preview = await previewDevBackup(file)
                    setRestorePreview(preview)
                  } catch (error: any) {
                    setSheetMsg(error?.response?.data?.detail || error?.message || 'อ่าน preview backup ไม่สำเร็จ')
                  }
                }}
              />
              <button
                className="rounded bg-amber-500 px-3 py-2 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-50"
                type="button"
                disabled={!restoreFile || restoreBusy}
                onClick={() => {
                  setSecurePassword('')
                  setSecureAction('restore')
                }}
              >
                {restoreBusy ? 'กำลังกู้คืน...' : 'กู้คืนจาก Backup'}
              </button>
            </div>
            {restorePreview ? (
              <div className="mt-3 rounded border border-amber-400/30 bg-black/20 p-3 text-xs text-amber-50">
                <div className="font-semibold">Preview Backup</div>
                <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3">
                  <div>App: <span className="text-white">{restorePreview.app_name || '-'}</span></div>
                  <div>สร้างเมื่อ: <span className="text-white">{restorePreview.created_at || '-'}</span></div>
                  <div>Sheet: <span className="text-white">{restorePreview.sheet_id || '-'}</span></div>
                  <div>Users: <span className="text-white">{restorePreview.counts.users || 0}</span></div>
                  <div>Products: <span className="text-white">{restorePreview.counts.products || 0}</span></div>
                  <div>Transactions: <span className="text-white">{restorePreview.counts.transactions || 0}</span></div>
                  <div>Alert states: <span className="text-white">{restorePreview.counts.alert_states || 0}</span></div>
                  <div>Audit logs: <span className="text-white">{restorePreview.counts.audit_logs || 0}</span></div>
                  <div>Media files: <span className="text-white">{restorePreview.counts.media_files || 0}</span></div>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <div className="mt-3 rounded border border-red-500/30 bg-red-500/5 p-3">
          <div className="text-xs text-white/60">ล้างสินค้า/สต็อกทั้งหมด (DB) แต่คงผู้ใช้ไว้ พร้อมดาวน์โหลด backup ก่อนล้าง</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              className="rounded bg-red-500 px-3 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
              type="button"
              disabled={resetStockBusy}
              onClick={() => {
                setSecurePassword('')
                setSecureAction('reset')
              }}
            >
              {resetStockBusy ? 'กำลังล้าง...' : 'ล้าง Stock ให้โล่ง'}
            </button>
          </div>
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 backdrop-blur">
        <div className="border-b border-[color:var(--color-border)] px-4 py-2 text-sm font-semibold">Activity ล่าสุด</div>
        <div className="max-h-[360px] overflow-y-auto">
          {activity.map((x) => (
            <div key={x.id} className="flex items-start justify-between gap-3 border-b border-[color:var(--color-border)] px-4 py-3 text-sm">
              <div className="min-w-0">
                <div className="truncate text-white/90">{x.action}</div>
                <div className="truncate text-xs text-white/60">{x.message}</div>
              </div>
              <div className="shrink-0 text-xs text-white/50">{new Date(x.created_at).toLocaleString()}</div>
            </div>
          ))}
          {!busy && activity.length === 0 ? <div className="px-4 py-6 text-sm text-white/60">ยังไม่มีรายการ</div> : null}
        </div>
      </div>
    </div>
  )
}

