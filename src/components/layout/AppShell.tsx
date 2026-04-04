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

function navClass(isActive: boolean) {
  return [
    'block rounded-lg px-3 py-2 text-sm transition',
    isActive ? 'bg-[color:var(--color-primary)] text-black shadow-sm' : 'text-[color:var(--color-muted-strong)] hover:bg-white/8'
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

function sectionsFor(role: AppRole | undefined, isEn: boolean) {
  if (role === 'STOCK') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/stock/search', label: isEn ? 'Find products' : 'ค้นหาสินค้าและเช็ก' },
          { to: '/zones/search', label: isEn ? 'Compare prices' : 'ค้นหาการเทียบราคา' },
          { to: '/zones/notifications', label: isEn ? 'Notifications' : 'การแจ้งเตือน' },
        ],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [
          { to: '/products', label: isEn ? 'Products' : 'รายการสินค้า' },
          ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: isEn ? 'Suppliers' : 'รายชื่อร้านค้า' }] : []),
          { to: '/transactions', label: isEn ? 'Transactions' : 'ธุรกรรม' },
        ],
      },
      {
        title: isEn ? 'Settings' : 'การตั้งค่า',
        items: [{ to: '/settings', label: isEn ? 'Display settings' : 'ตั้งค่าหน้าตา' }],
      },
    ]
  }

  if (role === 'ADMIN') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/admin', label: isEn ? 'Operations home' : 'หน้าดูแลงานหลัก' },
          { to: '/zones/notifications', label: isEn ? 'Notifications' : 'การแจ้งเตือน' },
        ],
      },
      {
        title: isEn ? 'Review' : 'ตรวจสอบงาน',
        items: [
          { to: '/zones/search', label: isEn ? 'Compare prices' : 'ค้นหาการเทียบราคา' },
          { to: '/zones/verification', label: isEn ? 'Review monitor' : 'ติดตามคิวตรวจสอบ' },
        ],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [
          { to: '/products', label: isEn ? 'Products' : 'จัดการสินค้า' },
          ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: isEn ? 'Suppliers' : 'จัดการร้านค้า' }] : []),
          { to: '/transactions', label: isEn ? 'Transactions' : 'ธุรกรรม' },
          { to: '/reports', label: isEn ? 'Reports' : 'รายงาน' },
        ],
      },
      {
        title: isEn ? 'Settings' : 'การตั้งค่า',
        items: [{ to: '/settings', label: isEn ? 'Settings & appearance' : 'ตั้งค่าและหน้าตา' }],
      },
    ]
  }

  if (role === 'DEV') {
    return [
      {
        title: isEn ? 'Main' : 'เมนูหลัก',
        items: [
          { to: '/zones/dev', label: isEn ? 'My review home' : 'งานตรวจสอบของฉัน' },
          { to: '/zones/notifications', label: isEn ? 'Notifications' : 'การแจ้งเตือน' },
        ],
      },
      {
        title: isEn ? 'Review' : 'ตรวจสอบงาน',
        items: [
          { to: '/zones/verification', label: isEn ? 'Verification queue' : 'คิวงานรอตรวจสอบ' },
          { to: '/zones/search', label: isEn ? 'Compare prices' : 'ค้นหาการเทียบราคา' },
        ],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [
          { to: '/products', label: isEn ? 'Products' : 'จัดการสินค้า' },
          ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: isEn ? 'Suppliers' : 'จัดการร้านค้า' }] : []),
          { to: '/transactions', label: isEn ? 'Transactions' : 'ธุรกรรม' },
          { to: '/reports', label: isEn ? 'Reports' : 'รายงาน' },
        ],
      },
      {
        title: isEn ? 'System' : 'ระบบ',
        items: [
          { to: '/admin/users', label: isEn ? 'Users' : 'จัดการผู้ใช้' },
          { to: '/settings', label: isEn ? 'Settings & appearance' : 'ตั้งค่าและหน้าตา' },
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
          { to: '/zones/notifications', label: isEn ? 'Notifications' : 'การแจ้งเตือน' },
        ],
      },
      {
        title: isEn ? 'Review' : 'ตรวจสอบงาน',
        items: [
          { to: '/zones/search', label: isEn ? 'Compare prices' : 'ค้นหาการเทียบราคา' },
          { to: '/zones/verification', label: isEn ? 'Verification queue' : 'คิวงานรอตรวจสอบ' },
          { to: '/owner-check', label: isEn ? 'Deep insights' : 'มุมมองเชิงลึก' },
        ],
      },
      {
        title: isEn ? 'Data' : 'ข้อมูลงาน',
        items: [
          { to: '/products', label: isEn ? 'Products' : 'จัดการสินค้า' },
          ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: isEn ? 'Suppliers' : 'จัดการร้านค้า' }] : []),
          { to: '/transactions', label: isEn ? 'Transactions' : 'ธุรกรรม' },
          { to: '/reports', label: isEn ? 'Reports' : 'รายงาน' },
        ],
      },
      {
        title: isEn ? 'System' : 'ระบบ',
        items: [
          { to: '/admin/users', label: isEn ? 'Users' : 'จัดการผู้ใช้' },
          { to: '/settings', label: isEn ? 'Settings & appearance' : 'ตั้งค่าและหน้าตา' },
        ],
      },
    ]
  }

  return [
    {
      title: isEn ? 'Main' : 'เมนูหลัก',
      items: [
        { to: homePathFor(role), label: isEn ? 'Work home' : 'หน้าทำงานหลัก' },
        { to: '/zones/notifications', label: isEn ? 'Notifications' : 'การแจ้งเตือน' },
      ],
    },
    {
      title: isEn ? 'Data' : 'ข้อมูลงาน',
      items: [
        { to: '/zones/search', label: isEn ? 'Compare prices' : 'ค้นหาการเทียบราคา' },
        ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: isEn ? 'Suppliers' : 'รายชื่อร้านค้า' }] : []),
        { to: '/transactions', label: isEn ? 'Transactions' : 'ธุรกรรม' },
        { to: '/reports', label: isEn ? 'Reports' : 'รายงาน' },
      ],
    },
    {
      title: isEn ? 'Settings' : 'การตั้งค่า',
      items: [{ to: '/settings', label: isEn ? 'Display settings' : 'ตั้งค่าหน้าตา' }],
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
      <header className="card border-b border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 backdrop-blur">
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
          <div className="card rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-3 backdrop-blur">
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
                    className="flex w-full items-center justify-between rounded-xl border border-[color:var(--color-border)] bg-white/5 px-3 py-2.5 text-left shadow-sm transition hover:bg-white/8"
                  >
                    <span className="text-sm font-bold text-[color:var(--color-fg)]">
                      {section.title}
                    </span>
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
