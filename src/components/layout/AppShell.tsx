import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { HelpHint } from '../ui/HelpHint'
import { featureFlags } from '../../config/features'
import { changeLanguagePreference } from '../../services/i18n'
import { useAuthStore } from '../../store/authStore'
import { useUiPreferencesStore } from '../../store/uiPreferencesStore'
import { applyThemePreference } from '../../utils/theme'

type AppRole = 'STOCK' | 'ADMIN' | 'ACCOUNTANT' | 'OWNER' | 'DEV'

type NavItem = {
  to: string
  label: string
}

type NavSection = {
  title: string
  items: NavItem[]
}

function navClass(isActive: boolean) {
  return [
    'block rounded-lg px-3 py-2 text-sm transition',
    isActive ? 'bg-[color:var(--color-primary)] text-black shadow-sm' : 'text-[color:var(--color-muted-strong)] hover:bg-white/8',
  ].join(' ')
}

function roleDisplay(role: AppRole | undefined, isEn: boolean) {
  if (!role) return isEn ? 'User' : 'ผู้ใช้งาน'
  if (isEn) {
    return {
      OWNER: 'Owner',
      DEV: 'Developer',
      ADMIN: 'Admin',
      STOCK: 'Stock',
      ACCOUNTANT: 'Accountant',
    }[role]
  }
  return {
    OWNER: 'เจ้าของระบบ',
    DEV: 'ทีมพัฒนา',
    ADMIN: 'ผู้ดูแลระบบ',
    STOCK: 'พนักงานสต็อก',
    ACCOUNTANT: 'ฝ่ายบัญชี',
  }[role]
}

function homePathFor(role: AppRole | undefined) {
  if (role === 'OWNER') return '/zones/owner'
  if (role === 'DEV') return '/zones/dev'
  if (role === 'ADMIN') return '/zones/admin'
  return '/zones/stock/search'
}

function sectionsFor(role: AppRole | undefined, isEn: boolean): NavSection[] {
  const compareItem = { to: '/zones/search?view=compare', label: isEn ? 'Quick compare' : 'เทียบสินค้าแบบไว' }
  const queueItem = { to: '/zones/verification', label: isEn ? 'Auto review queue' : 'คิวตรวจสอบอัตโนมัติ' }
  const notificationItem = { to: '/zones/notifications', label: isEn ? 'Notifications' : 'การแจ้งเตือน' }
  const productItem = { to: '/products', label: isEn ? 'Products' : 'จัดการสินค้า' }
  const priceRecordItem = { to: '/price-records', label: isEn ? 'Price Records' : 'บันทึกราคา' }
  const supplierManageItem = { to: '/suppliers', label: isEn ? 'Suppliers' : 'จัดการร้านค้า' }
  const supplierListItem = { to: '/suppliers', label: isEn ? 'Suppliers' : 'รายชื่อร้านค้า' }
  const transactionItem = { to: '/transactions', label: isEn ? 'Transactions' : 'ธุรกรรม' }
  const reportItem = { to: '/reports', label: isEn ? 'Reports' : 'รายงาน' }
  const settingsItem = { to: '/settings', label: isEn ? 'Settings & appearance' : 'ตั้งค่าและหน้าตา' }

  if (role === 'STOCK') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/stock/search', label: isEn ? 'Find products' : 'ค้นหาสินค้าและเช็ก' },
          compareItem,
          notificationItem,
        ],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [productItem, ...(featureFlags.supplierModule ? [supplierListItem] : []), priceRecordItem, transactionItem],
      },
      {
        title: isEn ? 'Settings' : 'การตั้งค่า',
        items: [{ ...settingsItem, label: isEn ? 'Display settings' : 'ตั้งค่าหน้าตา' }],
      },
    ]
  }

  if (role === 'ADMIN') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/admin', label: isEn ? 'Operations home' : 'หน้าดูแลงานหลัก' },
          notificationItem,
        ],
      },
      {
        title: isEn ? 'Review' : 'ตรวจสอบงาน',
        items: [compareItem, queueItem],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [productItem, ...(featureFlags.supplierModule ? [supplierManageItem] : []), priceRecordItem, transactionItem, reportItem],
      },
      {
        title: isEn ? 'Settings' : 'การตั้งค่า',
        items: [settingsItem],
      },
    ]
  }

  if (role === 'DEV') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/dev', label: isEn ? 'My review home' : 'งานตรวจสอบของฉัน' },
          notificationItem,
        ],
      },
      {
        title: isEn ? 'Review' : 'ตรวจสอบงาน',
        items: [queueItem, compareItem],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [productItem, ...(featureFlags.supplierModule ? [supplierManageItem] : []), priceRecordItem, transactionItem, reportItem],
      },
      {
        title: isEn ? 'System' : 'ระบบ',
        items: [
          { to: '/admin/users', label: isEn ? 'Users' : 'จัดการผู้ใช้' },
          settingsItem,
          { to: '/dev', label: isEn ? 'Developer tools' : 'เครื่องมือพัฒนา' },
        ],
      },
    ]
  }

  if (role === 'OWNER') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/owner', label: isEn ? 'Executive home' : 'ภาพรวมผู้บริหาร' },
          notificationItem,
        ],
      },
      {
        title: isEn ? 'Review' : 'ตรวจสอบงาน',
        items: [compareItem, queueItem, { to: '/owner-check', label: isEn ? 'Deep insights' : 'มุมมองเชิงลึก' }],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [productItem, ...(featureFlags.supplierModule ? [supplierManageItem] : []), priceRecordItem, transactionItem, reportItem],
      },
      {
        title: isEn ? 'System' : 'ระบบ',
        items: [
          { to: '/admin/users', label: isEn ? 'Users' : 'จัดการผู้ใช้' },
          settingsItem,
        ],
      },
    ]
  }

  return [
    {
      title: isEn ? 'Main' : 'เมนูหลัก',
      items: [
        { to: homePathFor(role), label: isEn ? 'Work home' : 'หน้าทำงานหลัก' },
        notificationItem,
      ],
    },
    {
      title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [compareItem, ...(featureFlags.supplierModule ? [supplierListItem] : []), priceRecordItem, transactionItem, reportItem],
    },
    {
      title: isEn ? 'Settings' : 'การตั้งค่า',
      items: [{ ...settingsItem, label: isEn ? 'Display settings' : 'ตั้งค่าหน้าตา' }],
    },
  ]
}

export function AppShell() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const clearSession = useAuthStore((s) => s.clearSession)
  const helpMode = useUiPreferencesStore((s) => s.helpMode)
  const toggleHelpMode = useUiPreferencesStore((s) => s.toggleHelpMode)
  const themePreference = useUiPreferencesStore((s) => s.themePreference)
  const setThemePreference = useUiPreferencesStore((s) => s.setThemePreference)

  const role = user?.role as AppRole | undefined
  const isEn = i18n.language === 'en'
  const navSections = sectionsFor(role, isEn)
  const [collapsedSections, setCollapsedSections] = useState<Record<number, boolean>>({})

  function toggleSection(index: number) {
    setCollapsedSections((prev) => ({ ...prev, [index]: !prev[index] }))
  }

  return (
    <div className="bg-app min-h-screen text-app">
      <header className="card surface-panel border-b">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-sm font-semibold tracking-wide">
            {t('app.name')}
          </Link>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 md:flex">
              <button
                className={`rounded border px-2.5 py-1 text-xs ${themePreference === 'light' ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)] text-black' : 'border-[color:var(--color-border)] text-[color:var(--color-muted)] hover:bg-white/10'}`}
                onClick={() => {
                  setThemePreference('light')
                  applyThemePreference('light')
                }}
                type="button"
              >
                {t('theme.light')}
              </button>
              <button
                className={`rounded border px-2.5 py-1 text-xs ${themePreference === 'dark' ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)] text-black' : 'border-[color:var(--color-border)] text-[color:var(--color-muted)] hover:bg-white/10'}`}
                onClick={() => {
                  setThemePreference('dark')
                  applyThemePreference('dark')
                }}
                type="button"
              >
                {t('theme.dark')}
              </button>
              <button
                className={`rounded border px-2.5 py-1 text-xs ${themePreference === 'system' ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)] text-black' : 'border-[color:var(--color-border)] text-[color:var(--color-muted)] hover:bg-white/10'}`}
                onClick={() => {
                  setThemePreference('system')
                  applyThemePreference('system')
                }}
                type="button"
              >
                {t('theme.auto')}
              </button>
            </div>
            <button
              className={`rounded border px-3 py-1 text-xs ${helpMode ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)] text-black' : 'border-[color:var(--color-border)] text-[color:var(--color-muted)] hover:bg-white/10'}`}
              onClick={() => toggleHelpMode()}
              type="button"
            >
              {helpMode ? t('help.on') : t('help.off')}
            </button>
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-1 text-xs text-[color:var(--color-muted)] hover:bg-white/10"
              onClick={() => void changeLanguagePreference(i18n.language === 'en' ? 'th' : 'en')}
              type="button"
            >
              {t('language.switch')}
            </button>
            <HelpHint helpKey="dashboard.summary" />
            <div className="text-xs text-[color:var(--color-muted)]">{user?.display_name ?? user?.username}</div>
            <button
              className="rounded bg-[color:var(--color-primary)] px-3 py-1 text-xs font-semibold text-black hover:opacity-90"
              onClick={() => {
                clearSession()
                navigate('/login')
              }}
              type="button"
            >
              {t('app.logout')}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl grid-cols-12 gap-4 px-4 py-4">
        <aside className="col-span-12 md:col-span-4 lg:col-span-3 xl:col-span-2">
          <div className="card surface-panel rounded-xl p-3">
            <div className="border-b border-[color:var(--color-border)] pb-2">
              <div className="text-sm font-semibold">{isEn ? 'Menu' : 'เมนู'}</div>
              <div className="mt-1 text-xs text-[color:var(--color-muted)]">{roleDisplay(role, isEn)}</div>
            </div>
            <nav className="mt-3 space-y-3">
              {navSections.map((section, index) => (
                <div key={section.title} className="space-y-2">
                  <button
                    type="button"
                    onClick={() => toggleSection(index)}
                    className="surface-item flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left shadow-sm transition"
                  >
                    <span className="text-sm font-bold text-[color:var(--color-fg)]">{section.title}</span>
                    <span
                      className={`text-sm font-semibold text-[color:var(--color-muted)] transition-transform ${collapsedSections[index] ? '' : 'rotate-90'}`}
                    >
                      {'>'}
                    </span>
                  </button>
                  {!collapsedSections[index] ? (
                    <div className="space-y-1 px-1">
                      {section.items.map((item) => (
                        <NavLink key={item.to} to={item.to} className={({ isActive }) => navClass(isActive)}>
                          {item.label}
                        </NavLink>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </nav>
          </div>
        </aside>
        <main className="col-span-12 md:col-span-8 lg:col-span-9 xl:col-span-10">
          <div key={location.pathname} className="animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
