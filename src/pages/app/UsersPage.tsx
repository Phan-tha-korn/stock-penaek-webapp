import { useEffect, useMemo, useState } from 'react'
import { useAuthStore } from '../../store/authStore'
import type { Role, User } from '../../types/models'
import { createUser, deleteUser, listUsers, resetUserPassword, updateUser } from '../../services/auth'
import { useAlert, useConfirm, usePrompt } from '../../components/ui/ConfirmDialog'

const roles: Role[] = ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV']

export function UsersPage() {
  const myRole = useAuthStore((s) => s.role)
  const canManage = myRole === 'OWNER' || myRole === 'DEV'
  const showAlert = useAlert()
  const showConfirm = useConfirm()
  const showPrompt = usePrompt()

  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<User[]>([])
  const [total, setTotal] = useState(0)

  const [creating, setCreating] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newRole, setNewRole] = useState<Role>('STOCK')
  const [newPassword, setNewPassword] = useState('')
  const [newSecretKey, setNewSecretKey] = useState('')

  const [resetFor, setResetFor] = useState<User | null>(null)
  const [resetPassword, setResetPassword] = useState('')

  const params = useMemo(() => ({ q: q.trim() || undefined, limit: 200, offset: 0 }), [q])

  async function reload() {
    setBusy(true)
    setError(null)
    try {
      const res = await listUsers(params)
      const safeItems = Array.isArray((res as any)?.items) ? ((res as any).items as User[]) : []
      const safeTotal = typeof (res as any)?.total === 'number' ? (res as any).total : safeItems.length
      setItems(safeItems)
      setTotal(safeTotal)
    } catch (e: any) {
      setItems([])
      setTotal(0)
      setError(e?.response?.data?.detail || e?.message || 'โหลดผู้ใช้ไม่สำเร็จ')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    reload()
  }, [params])

  if (!canManage) {
    return (
      <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-4 text-sm text-white/80">
        ไม่มีสิทธิ์เข้าถึง
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-semibold">ผู้ใช้</div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          <input
            className="w-full max-w-sm flex-1 rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="ค้นหาด้วย username / ชื่อ"
          />
          <button
            className="rounded bg-[color:var(--color-primary)] px-3 py-2 text-sm font-semibold text-black hover:opacity-90"
            onClick={() => setCreating(true)}
            type="button"
          >
            + เพิ่มผู้ใช้
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div>
      ) : null}

      {creating ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm md:items-center">
          <div className="card w-full max-w-lg rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl flex max-h-[calc(100vh-2rem)] flex-col">
            <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
              <div className="text-sm font-semibold">เพิ่มผู้ใช้</div>
              <button onClick={() => setCreating(false)} className="text-white/60 hover:text-white" type="button">
                ✕
              </button>
            </div>
            <div className="space-y-3 overflow-y-auto p-6">
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="username"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="ชื่อที่แสดง (ไม่บังคับ)"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
              />
              <select
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as Role)}
              >
                {roles.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <input
                type="password"
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="รหัสผ่าน (อย่างน้อย 6 ตัวอักษร)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <input
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="รหัสลับ (Secret Key) (ไม่บังคับ)"
                value={newSecretKey}
                onChange={(e) => setNewSecretKey(e.target.value)}
              />
              <div className="text-xs text-white/60">ถ้าตั้งรหัสลับ ผู้ใช้จะต้องใส่รหัส TOTP ตอนล็อกอิน</div>
              <div className="rounded border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                Secret Key ต้องเป็นค่า Base32 สำหรับ TOTP เท่านั้น ถ้าไม่มีความจำเป็นให้ปล่อยว่างไว้เพื่อให้ผู้ใช้ล็อกอินด้วยรหัสผ่านได้ทันที
              </div>
              <div className="flex flex-wrap justify-end gap-2 pt-2">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  onClick={() => setCreating(false)}
                  type="button"
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                  type="button"
                  onClick={async () => {
                    try {
                      await createUser({
                        username: newUsername.trim(),
                        display_name: newDisplayName.trim(),
                        role: newRole,
                        password: newPassword,
                        secret_key: newSecretKey.trim() || undefined
                      })
                      setCreating(false)
                      setNewUsername('')
                      setNewDisplayName('')
                      setNewRole('STOCK')
                      setNewPassword('')
                      setNewSecretKey('')
                      await reload()
                    } catch {
                      alert('เพิ่มผู้ใช้ไม่สำเร็จ (username ซ้ำหรือข้อมูลไม่ถูกต้อง)')
                    }
                  }}
                >
                  บันทึก
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {resetFor ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm md:items-center">
          <div className="card w-full max-w-lg rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-2xl flex max-h-[calc(100vh-2rem)] flex-col">
            <div className="flex items-center justify-between border-b border-[color:var(--color-border)] px-6 py-4">
              <div className="text-sm font-semibold">รีเซ็ตรหัสผ่าน: {resetFor.username}</div>
              <button onClick={() => setResetFor(null)} className="text-white/60 hover:text-white" type="button">
                ✕
              </button>
            </div>
            <div className="space-y-3 overflow-y-auto p-6">
              <input
                type="password"
                className="w-full rounded border border-[color:var(--color-border)] bg-black/30 px-3 py-2 text-sm outline-none focus:border-[color:var(--color-primary)]"
                placeholder="รหัสผ่านใหม่ (อย่างน้อย 6 ตัวอักษร)"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
              />
              <div className="flex justify-end gap-2 pt-2">
                <button
                  className="rounded border border-[color:var(--color-border)] px-4 py-2 text-sm text-white/80 hover:bg-white/10"
                  onClick={() => setResetFor(null)}
                  type="button"
                >
                  ยกเลิก
                </button>
                <button
                  className="rounded bg-[color:var(--color-primary)] px-4 py-2 text-sm font-semibold text-black hover:opacity-90"
                  type="button"
                  onClick={async () => {
                    if (!resetFor) return
                    try {
                      await resetUserPassword(resetFor.id, resetPassword)
                      setResetFor(null)
                      setResetPassword('')
                      await reload()
                      alert('รีเซ็ตรหัสผ่านแล้ว')
                    } catch {
                      alert('รีเซ็ตรหัสผ่านไม่สำเร็จ')
                    }
                  }}
                >
                  บันทึก
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 backdrop-blur">
        <div className="border-b border-[color:var(--color-border)] px-4 py-2 text-xs text-white/60">
          {busy ? 'กำลังโหลด...' : `${total} ผู้ใช้`}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-white/60">
              <tr className="border-b border-[color:var(--color-border)]">
                <th className="px-4 py-2">Username</th>
                <th className="px-4 py-2">ชื่อ</th>
                <th className="px-4 py-2">Role</th>
                <th className="px-4 py-2">สถานะ</th>
                <th className="px-4 py-2">จัดการ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {!busy && items.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-[color:var(--color-muted)]">
                    ยังไม่มีผู้ใช้ในระบบ
                  </td>
                </tr>
              ) : null}
              {items.map((u) => (
                <tr key={u.id} className="hover:bg-white/5">
                  <td className="px-4 py-2 font-mono text-xs text-white/80">{u.username}</td>
                  <td className="px-4 py-2 text-white/80">{u.display_name || '-'}</td>
                  <td className="px-4 py-2">
                    <select
                      className="rounded border border-[color:var(--color-border)] bg-black/30 px-2 py-1 text-xs outline-none focus:border-[color:var(--color-primary)]"
                      value={u.role}
                      onChange={async (e) => {
                        try {
                          await updateUser(u.id, { role: e.target.value })
                          await reload()
                        } catch (err: any) {
                          setError(err?.response?.data?.detail || 'อัปเดต role ไม่สำเร็จ')
                          await reload()
                        }
                      }}
                    >
                      {roles.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      className={`rounded border px-2 py-1 text-xs ${
                        u.is_active ? 'border-green-500/30 text-green-200 hover:bg-green-500/10' : 'border-red-500/30 text-red-200 hover:bg-red-500/10'
                      }`}
                      onClick={async () => {
                        try {
                          await updateUser(u.id, { is_active: !u.is_active })
                          await reload()
                        } catch (err: any) {
                          setError(err?.response?.data?.detail || 'อัปเดตสถานะไม่สำเร็จ')
                          await reload()
                        }
                      }}
                    >
                      {u.is_active ? 'ใช้งาน' : 'ปิดใช้งาน'}
                    </button>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                        type="button"
                        onClick={async () => {
                          const next = (await showPrompt('username ใหม่', u.username))?.trim()
                          if (!next || next === u.username) return
                          try {
                            await updateUser(u.id, { username: next })
                            await reload()
                          } catch {
                            await showAlert('แก้ username ไม่สำเร็จ')
                          }
                        }}
                      >
                        แก้ username
                      </button>
                      <button
                        className="rounded border border-[color:var(--color-border)] px-2 py-1 text-xs text-white/80 hover:bg-white/10"
                        type="button"
                        onClick={() => setResetFor(u)}
                      >
                        รีเซ็ตรหัสผ่าน
                      </button>
                      <button
                        className="rounded border border-red-500/30 px-2 py-1 text-xs text-red-200 hover:bg-red-500/10"
                        type="button"
                        onClick={async () => {
                          const ok = await showConfirm(`ยืนยันลบผู้ใช้ ${u.username}?`)
                          if (!ok) return
                          try {
                            await deleteUser(u.id)
                            await reload()
                          } catch (e: any) {
                            await showAlert(e?.response?.data?.detail === 'cannot_delete_self' ? 'ไม่สามารถลบบัญชีตัวเองได้' : 'ลบผู้ใช้ไม่สำเร็จ')
                          }
                        }}
                      >
                        ลบผู้ใช้
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!busy && items.length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-sm text-white/60" colSpan={5}>
                    ไม่พบผู้ใช้
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

