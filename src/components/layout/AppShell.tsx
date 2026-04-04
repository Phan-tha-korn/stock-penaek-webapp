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
    'block rounded px-3 py-2 text-sm transition',
    isActive ? 'bg-[color:var(--color-primary)] text-black' : 'text-[color:var(--color-muted-strong)] hover:bg-white/10'
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

function homeLabel(role: AppRole | undefined, isEn: boolean) {
  if (isEn) {
    return {
      OWNER: 'Executive home',
      DEV: 'Verification home',
      ADMIN: 'Operations home',
      STOCK: 'Product search & check',
      ACCOUNTANT: 'Work home',
    }[role || 'STOCK']
  }
  return {
    OWNER: 'หน้าเริ่มต้นผู้บริหาร',
    DEV: 'หน้าตรวจสอบงาน',
    ADMIN: 'หน้าดูแลงานหลัก',
    STOCK: 'ค้นหาสินค้าและเช็ค',
    ACCOUNTANT: 'หน้าทำงานหลัก',
  }[role || 'STOCK']
}

function sidebarIntro(role: AppRole | undefined, isEn: boolean) {
  if (isEn) {
    return {
      OWNER: 'Main menus for business overview, verification, and system control.',
      DEV: 'Main menus for verification, matching, search, and system tools.',
      ADMIN: 'Main menus for supplier operations, monitoring, and daily admin work.',
      STOCK: 'Main menus for product lookup, compare, and stock-related checks.',
      ACCOUNTANT: 'Main menus for operational reports, transactions, and supporting tools.',
    }[role || 'STOCK']
  }
  return {
    OWNER: 'เมนูหลักสำหรับดูภาพรวมธุรกิจ ติดตามงานตรวจสอบ และควบคุมระบบ',
    DEV: 'เมนูหลักสำหรับตรวจสอบงาน เทียบราคา ค้นหา และดูแลเครื่องมือระบบ',
    ADMIN: 'เมนูหลักสำหรับดูแลงานร้านค้า ติดตามคิวงาน และทำงานประจำวัน',
    STOCK: 'เมนูหลักสำหรับค้นหาสินค้า เทียบราคา และตรวจเช็กข้อมูลสต็อก',
    ACCOUNTANT: 'เมนูหลักสำหรับดูรายงาน ธุรกรรม และเครื่องมือประกอบการทำงาน',
  }[role || 'STOCK']
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

  const role = user?.role
  const isEn = i18n.language === 'en'

  const homePath =
    role === 'OWNER' ? '/zones/owner' :
    role === 'DEV' ? '/zones/dev' :
    role === 'ADMIN' ? '/zones/admin' :
    '/zones/stock/search'

  const navSections = [
    {
      title: isEn ? 'Main menu' : 'เมนูหลัก',
      roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const,
      items: [
        { to: homePath, label: homeLabel(role as AppRole | undefined, isEn), roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
        { to: '/zones/notifications', label: isEn ? 'Important notifications' : 'การแจ้งเตือนสำคัญ', roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
      ],
    },
    {
      title: isEn ? 'Search & review' : 'ค้นหาและตรวจสอบ',
      roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const,
      items: [
        { to: '/zones/search', label: isEn ? 'Price compare search' : 'ค้นหาการเทียบราคา', roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
        { to: '/zones/verification', label: isEn ? 'Review queue' : 'คิวงานรอตรวจสอบ', roles: ['ADMIN', 'OWNER', 'DEV'] as const },
        { to: '/owner-check', label: isEn ? 'Owner insight view' : 'มุมมองผู้บริหาร', roles: ['OWNER'] as const },
      ],
    },
    {
      title: isEn ? 'Products & business data' : 'สินค้าและข้อมูลงาน',
      roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const,
      items: [
        { to: '/products', label: role === 'STOCK' ? (isEn ? 'Product list & check' : 'รายการสินค้าและเช็ก') : (isEn ? 'Product management' : 'จัดการสินค้า'), roles: ['STOCK', 'ADMIN', 'OWNER', 'DEV'] as const },
        ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: role === 'STOCK' ? (isEn ? 'Supplier list' : 'รายชื่อร้านค้า') : (isEn ? 'Supplier management' : 'จัดการร้านค้า'), roles: ['STOCK', 'ADMIN', 'OWNER', 'DEV', 'ACCOUNTANT'] as const }] : []),
        { to: '/transactions', label: isEn ? 'Transactions & stock movement' : 'ธุรกรรมและการเคลื่อนไหว', roles: ['STOCK', 'ADMIN', 'OWNER', 'DEV', 'ACCOUNTANT'] as const },
        { to: '/reports', label: isEn ? 'Reports & summaries' : 'รายงานและสรุปผล', roles: ['ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
        { to: '/dashboard', label: isEn ? 'Legacy overview dashboard' : 'แดชบอร์ดภาพรวมแบบเดิม', roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
      ],
    },
    {
      title: isEn ? 'System & setup' : 'ระบบและการตั้งค่า',
      roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const,
      items: [
        { to: '/admin/users', label: isEn ? 'User accounts' : 'จัดการผู้ใช้', roles: ['OWNER', 'DEV'] as const },
        { to: '/settings', label: isEn ? 'Settings & appearance' : 'ตั้งค่าและหน้าตา', roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
        { to: '/dev', label: isEn ? 'Developer tools' : 'เครื่องมือพัฒนา', roles: ['DEV'] as const },
      ],
    },
  ]
    .filter((section) => (role ? section.roles.includes(role as never) : false))
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => (role ? item.roles.includes(role as never) : false)),
    }))
    .filter((section) => section.items.length > 0)

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
        <aside className="col-span-12 md:col-span-3 lg:col-span-2">
          <div className="card rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-3 backdrop-blur">
            <div className="border-b border-[color:var(--color-border)] pb-3">
              <div className="text-sm font-semibold">{isEn ? 'Menu for your role' : 'เมนูสำหรับบทบาทนี้'}</div>
              <div className="mt-1 text-xs text-[color:var(--color-muted)]">{roleDisplay(role as AppRole | undefined, isEn)}</div>
              <div className="mt-2 text-xs leading-5 text-[color:var(--color-muted-strong)]">{sidebarIntro(role as AppRole | undefined, isEn)}</div>
            </div>
            <nav className="mt-3 space-y-4">
              {navSections.map((section) => (
                <div key={section.title} className="space-y-1">
                  <div className="px-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[color:var(--color-muted)]">
                    {section.title}
                  </div>
                  <div className="space-y-1">
                    {section.items.map((x) => (
                      <NavLink key={x.to} to={x.to} className={({ isActive }) => navClass(isActive)}>
                        {x.label}
                      </NavLink>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </aside>
        <main className="col-span-12 md:col-span-9 lg:col-span-10">
          <div key={location.pathname} className="animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

