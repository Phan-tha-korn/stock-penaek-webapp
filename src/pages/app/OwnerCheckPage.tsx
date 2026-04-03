import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { fetchOwnerSummary, type OwnerSummary } from '../../services/dashboard'
import { formatTHB } from '../../utils/money'

type OwnerPeriod = OwnerSummary['period']

const COLORS: Record<string, string> = {
  FULL: '#22c55e',
  NORMAL: '#60a5fa',
  LOW: '#f59e0b',
  CRITICAL: '#ef4444',
  OUT: '#64748b',
  TEST: '#0ea5e9'
}

const PERIOD_LABELS: Record<OwnerPeriod, string> = {
  day: 'รายวัน',
  week: 'รายสัปดาห์',
  month: 'รายเดือน',
  year: 'รายปี',
}

export function OwnerCheckPage() {
  const [period, setPeriod] = useState<OwnerPeriod>('week')
  const [busy, setBusy] = useState(true)
  const [summary, setSummary] = useState<OwnerSummary | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      setBusy(true)
      try {
        const data = await fetchOwnerSummary(period)
        if (!cancelled) setSummary(data)
      } catch {
        if (!cancelled) setSummary(null)
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    run()
    const timer = window.setInterval(run, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [period])

  const timeline = summary?.timeline ?? []
  const statusChart = summary?.status_chart ?? []
  const categoryChart = summary?.category_chart ?? []

  const transactionChart = useMemo(
    () =>
      timeline.map((item) => ({
        label: item.label,
        กิจกรรม: item.activity_count,
        ธุรกรรม: item.transaction_count,
      })),
    [timeline]
  )

  const quantityChart = useMemo(
    () =>
      timeline.map((item) => ({
        label: item.label,
        รับเข้า: Number(item.stock_in_qty || 0),
        จ่ายออก: Number(item.stock_out_qty || 0),
        ปรับยอด: Number(item.adjust_qty || 0),
      })),
    [timeline]
  )

  return (
    <div className="space-y-4">
      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-sm font-semibold">สำหรับเจ้าของ</div>
            <div className="mt-1 text-xs text-white/60">ดูภาพรวมระบบแบบอัปเดต พร้อมกราฟสรุปรายวัน รายสัปดาห์ รายเดือน และรายปีในหน้าเดียว</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {(['day', 'week', 'month', 'year'] as OwnerPeriod[]).map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setPeriod(item)}
                className={`rounded px-3 py-2 text-sm font-semibold transition ${
                  period === item
                    ? 'bg-[color:var(--color-primary)] text-black'
                    : 'border border-[color:var(--color-border)] bg-black/20 text-white/75 hover:bg-white/10'
                }`}
              >
                {PERIOD_LABELS[item]}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-xs text-white/60">ผู้ใช้ทั้งหมด</div>
          <div className="mt-1 text-2xl font-bold">{summary?.user_total ?? 0}</div>
          <div className="mt-2 text-xs text-white/45">รวมทุก role ที่เข้าใช้งานระบบ</div>
        </div>
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-xs text-white/60">ออนไลน์ตอนนี้</div>
          <div className="mt-1 text-2xl font-bold">{summary?.active_users_online ?? 0}</div>
          <div className="mt-2 text-xs text-white/45">จำนวนผู้ใช้ที่กำลังออนไลน์</div>
        </div>
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-xs text-white/60">กิจกรรมช่วงนี้</div>
          <div className="mt-1 text-2xl font-bold">{summary?.activity_total ?? 0}</div>
          <div className="mt-2 text-xs text-white/45">รวม log ระบบของ{PERIOD_LABELS[period]}</div>
        </div>
        <div className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-xs text-white/60">มูลค่าสต็อก</div>
          <div className="mt-1 text-2xl font-bold">{formatTHB(summary?.stock_value ?? 0)}</div>
          <div className="mt-2 text-xs text-white/45">ต้นทุนรวมล่าสุดของสินค้าที่ยังใช้งานอยู่</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        {[
          { to: '/', title: 'Dashboard หลัก', desc: 'ดูภาพรวม realtime' },
          { to: '/products', title: 'สินค้า', desc: 'จัดการข้อมูลสินค้า' },
          { to: '/transactions', title: 'ธุรกรรม', desc: 'ตรวจการเคลื่อนไหวสต็อก' },
          { to: '/reports', title: 'สรุป', desc: 'โหลดรายวัน/สัปดาห์/เดือน/ปี' },
          { to: '/admin/users', title: 'ผู้ใช้', desc: 'จัดการ user และสิทธิ์' },
        ].map((item) => (
          <Link key={item.to} to={item.to} className="rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur transition hover:border-white/20 hover:bg-white/10">
            <div className="text-sm font-semibold">{item.title}</div>
            <div className="mt-1 text-xs text-white/55">{item.desc}</div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold">แนวโน้มกิจกรรม {PERIOD_LABELS[period]}</div>
            <div className="text-xs text-white/55">อัปเดตทุก 15 วินาที</div>
          </div>
          <div className="mt-3 h-[320px]">
            {busy ? (
              <div className="text-sm text-white/60">กำลังโหลด...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={transactionChart}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="rgba(255,255,255,0.45)" />
                  <YAxis allowDecimals={false} stroke="rgba(255,255,255,0.45)" />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="กิจกรรม" stroke="#f97316" strokeWidth={3} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="ธุรกรรม" stroke="#38bdf8" strokeWidth={2} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">สถานะสินค้า</div>
          <div className="mt-3 h-[320px]">
            {busy ? (
              <div className="text-sm text-white/60">กำลังโหลด...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusChart} dataKey="value" nameKey="name" outerRadius={110} label>
                    {statusChart.map((entry) => (
                      <Cell key={entry.name} fill={COLORS[entry.name] || '#94a3b8'} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">ปริมาณธุรกรรม {PERIOD_LABELS[period]}</div>
          <div className="mt-1 text-xs text-white/60">ถ้ายังไม่มีธุรกรรมเก่า กราฟนี้จะขึ้นใกล้ศูนย์แต่ยังพร้อมใช้งานเมื่อระบบเริ่มบันทึกเพิ่ม</div>
          <div className="mt-3 h-[320px]">
            {busy ? (
              <div className="text-sm text-white/60">กำลังโหลด...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={quantityChart}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                  <XAxis dataKey="label" stroke="rgba(255,255,255,0.45)" />
                  <YAxis stroke="rgba(255,255,255,0.45)" />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="รับเข้า" fill="#22c55e" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="จ่ายออก" fill="#ef4444" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="ปรับยอด" fill="#f59e0b" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
          <div className="text-sm font-semibold">หมวดหมู่สินค้า (Top 10)</div>
          <div className="mt-3 h-[320px]">
            {busy ? (
              <div className="text-sm text-white/60">กำลังโหลด...</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={categoryChart} dataKey="value" nameKey="name" outerRadius={110} label />
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-4 backdrop-blur">
        <div className="text-sm font-semibold">รายละเอียด</div>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">สินค้าทั้งหมด</div>
            <div className="mt-1 text-xl font-semibold">{summary?.total_products ?? 0}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">มูลค่าสต็อก (ต้นทุน)</div>
            <div className="mt-1 text-xl font-semibold">{formatTHB(summary?.stock_value ?? 0)}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">มูลค่าสต็อก (ราคาขาย)</div>
            <div className="mt-1 text-xl font-semibold">{formatTHB(summary?.sales_value ?? 0)}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">กิจกรรมช่วงนี้</div>
            <div className="mt-1 text-xl font-semibold">{summary?.activity_total ?? 0}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">ธุรกรรมช่วงนี้</div>
            <div className="mt-1 text-xl font-semibold">{summary?.transaction_total ?? 0}</div>
          </div>
          <div className="rounded border border-[color:var(--color-border)] bg-black/20 p-3">
            <div className="text-xs text-white/60">ช่วงที่กำลังดู</div>
            <div className="mt-1 text-xl font-semibold">{PERIOD_LABELS[period]}</div>
          </div>
        </div>
      </div>
    </div>
  )
}
