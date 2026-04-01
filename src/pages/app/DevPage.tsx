import { useEffect, useState } from 'react'

import { api } from '../../services/api'
import { fetchConfig } from '../../services/config'
import { fetchActivity } from '../../services/dashboard'
import { importFromSheets, syncToSheets } from '../../services/products'
import { deleteGarbage, getGarbageWhitelist, scanGarbage, updateGarbageWhitelist, type GarbageFileItem } from '../../services/devGarbage'
import { getNotificationConfig, updateNotificationConfig } from '../../services/devNotifications'
import { createDevSheet, getDevSheetsConfig, type DevSheetCreateResult, type DevSheetsConfig } from '../../services/devSheets'
import { resetStock } from '../../services/devReset'
import { useAuthStore } from '../../store/authStore'
import type { ActivityItem } from '../../services/dashboard'
import type { AppConfig } from '../../types/models'

export function DevPage() {
  const role = useAuthStore((s) => s.role)
  const canUse = role === 'DEV'

  const [busy, setBusy] = useState(true)
  const [health, setHealth] = useState<any>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [activity, setActivity] = useState<ActivityItem[]>([])

  const [sheetMsg, setSheetMsg] = useState<string | null>(null)
  const [sheetAction, setSheetAction] = useState<'sync' | 'import' | null>(null)
  const [sheetsCfg, setSheetsCfg] = useState<DevSheetsConfig | null>(null)
  const [sheetCreateTitle, setSheetCreateTitle] = useState('')
  const [sheetShareEmails, setSheetShareEmails] = useState('')
  const [sheetCreateBusy, setSheetCreateBusy] = useState(false)
  const [lastCreatedSheet, setLastCreatedSheet] = useState<DevSheetCreateResult | null>(null)
  const [resetStockBusy, setResetStockBusy] = useState(false)
  const [garbageBusy, setGarbageBusy] = useState(false)
  const [garbageItems, setGarbageItems] = useState<GarbageFileItem[]>([])
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleteMode, setDeleteMode] = useState<'backup' | 'permanent'>('backup')
  const [garbageMsg, setGarbageMsg] = useState<string | null>(null)
  const [whitelist, setWhitelist] = useState<string[]>([])
  const [whitelistInput, setWhitelistInput] = useState('')

  const [notifBusy, setNotifBusy] = useState(false)
  const [notifMsg, setNotifMsg] = useState<string | null>(null)
  const [notifEnabled, setNotifEnabled] = useState(false)
  const [notifLow, setNotifLow] = useState<number[]>([])
  const [notifHigh, setNotifHigh] = useState<number[]>([])
  const [notifRoles, setNotifRoles] = useState<string[]>([])
  const [notifLowInput, setNotifLowInput] = useState('')
  const [notifHighInput, setNotifHighInput] = useState('')

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

  useEffect(() => {
    reload()
    scanNow()
    ;(async () => {
      try {
        const cfg = await getNotificationConfig()
        setNotifEnabled(Boolean(cfg.enabled))
        setNotifLow(cfg.low_levels_pct || [])
        setNotifHigh(cfg.high_levels_pct || [])
        setNotifRoles(cfg.roles || [])
      } catch (e: any) {
        setNotifMsg(e?.response?.data?.detail || e?.message || 'โหลดการตั้งค่าแจ้งเตือนไม่สำเร็จ')
      }
    })()
    ;(async () => {
      try {
        const c = await getDevSheetsConfig()
        setSheetsCfg(c)
      } catch {}
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
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Garbage File Management</div>
            <div className="text-xs text-white/60">สแกน temp/cache/log/build เก่า/backup หมดอายุ/duplicate node_modules</div>
          </div>
          <div className="flex flex-wrap gap-2">
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
                    roles: notifRoles
                  })
                  setNotifEnabled(Boolean(res.enabled))
                  setNotifLow(res.low_levels_pct || [])
                  setNotifHigh(res.high_levels_pct || [])
                  setNotifRoles(res.roles || [])
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

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">แจ้งเตือนเมื่อ “ลงถึง” (% ของ max_stock)</div>
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
            <div className="text-xs text-white/60">แจ้งเตือนเมื่อ “ขึ้นถึง” (% ของ max_stock)</div>
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
      </div>

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
            <div className="text-sm font-semibold">Google Sheets</div>
            <div className="text-xs text-white/60">นำเข้าจากชีต → DB (รอบเดียว) และสั่ง Sync ตอนนี้</div>
          </div>
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
                } finally {
                  setSheetAction(null)
                }
              }}
            >
              {sheetAction === 'sync' ? 'กำลัง Sync...' : 'Sync ไปชีตตอนนี้'}
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
        </div>
        {sheetMsg ? <div className="mt-2 text-xs text-white/70">{sheetMsg}</div> : null}

        <div className="mt-3 rounded border border-[color:var(--color-border)] bg-black/20 p-3">
          <div className="text-xs text-white/60">สร้าง Google Sheet ใหม่และตั้งค่า sheet_id ให้ระบบ</div>
          <div className="mt-2 text-xs text-white/50 break-words">
            sheet_id ปัจจุบัน: {sheetsCfg?.sheet_id ? sheetsCfg.sheet_id : '-'} | key: {sheetsCfg?.key_path ? sheetsCfg.key_path : '-'}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-50"
              type="button"
              disabled={!sheetsCfg?.sheet_id}
              onClick={() => window.open(`https://docs.google.com/spreadsheets/d/${sheetsCfg?.sheet_id}`, '_blank', 'noopener,noreferrer')}
            >
              เปิดชีตปัจจุบัน
            </button>
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10 disabled:opacity-50"
              type="button"
              disabled={!sheetsCfg?.sheet_id}
              onClick={() =>
                window.open(`https://docs.google.com/spreadsheets/d/${sheetsCfg?.sheet_id}/export?format=xlsx`, '_blank', 'noopener,noreferrer')
              }
            >
              ดาวน์โหลด .xlsx
            </button>
          </div>
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
                onClick={() => window.open(lastCreatedSheet.sheet_url, '_blank', 'noopener,noreferrer')}
              >
                เปิดชีตที่สร้างล่าสุด
              </button>
              <button
                className="rounded border border-[color:var(--color-border)] px-3 py-2 text-sm text-white/80 hover:bg-white/10"
                type="button"
                onClick={() => window.open(lastCreatedSheet.download_xlsx_url, '_blank', 'noopener,noreferrer')}
              >
                ดาวน์โหลดชีตล่าสุด (.xlsx)
              </button>
            </div>
          ) : null}
        </div>

        <div className="mt-3 rounded border border-red-500/30 bg-red-500/5 p-3">
          <div className="text-xs text-white/60">ล้างสินค้า/สต็อกทั้งหมด (DB) แต่คงผู้ใช้ไว้</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              className="rounded bg-red-500 px-3 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
              type="button"
              disabled={resetStockBusy}
              onClick={async () => {
                const ok = window.confirm('ยืนยันล้างสินค้า/สต็อกทั้งหมด? (จะลบสินค้าและธุรกรรมทั้งหมดใน DB แต่ผู้ใช้จะไม่ถูกลบ)')
                if (!ok) return
                setSheetMsg(null)
                setResetStockBusy(true)
                try {
                  const res = await resetStock()
                  setSheetMsg(`ล้างสต็อกแล้ว: สินค้า ${res.deleted_products}, ธุรกรรม ${res.deleted_transactions}`)
                  await reload()
                } catch (e: any) {
                  setSheetMsg(e?.response?.data?.detail || e?.message || 'ล้างสต็อกไม่สำเร็จ')
                } finally {
                  setResetStockBusy(false)
                }
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

