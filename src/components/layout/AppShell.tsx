import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { featureFlags } from '../../config/features'
import { useAuthStore } from '../../store/authStore'
import i18n from '../../services/i18n'

function navClass(isActive: boolean) {
  return [
    'block rounded px-3 py-2 text-sm transition',
    isActive ? 'bg-[color:var(--color-primary)] text-black' : 'text-white/80 hover:bg-white/10'
  ].join(' ')
}

export function AppShell() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const clearSession = useAuthStore((s) => s.clearSession)

  const role = user?.role

  const homePath =
    role === 'OWNER' ? '/zones/owner' :
    role === 'DEV' ? '/zones/dev' :
    role === 'ADMIN' ? '/zones/admin' :
    '/zones/stock/search'

  const navItems = [
    { to: homePath, label: t('nav.zoneHome', { defaultValue: 'Zone Home' }), roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
    { to: '/zones/search', label: t('nav.searchWorkspace', { defaultValue: 'Search' }), roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
    { to: '/zones/notifications', label: t('nav.notificationsCenter', { defaultValue: 'Notifications' }), roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
    { to: '/dashboard', label: t('nav.dashboard'), roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
    { to: '/products', label: t('nav.products'), roles: ['STOCK', 'ADMIN', 'OWNER', 'DEV'] as const },
    ...(featureFlags.supplierModule ? [{ to: '/suppliers', label: t('nav.suppliers', { defaultValue: 'Suppliers' }), roles: ['STOCK', 'ADMIN', 'OWNER', 'DEV', 'ACCOUNTANT'] as const }] : []),
    { to: '/transactions', label: t('nav.transactions'), roles: ['STOCK', 'ADMIN', 'OWNER', 'DEV', 'ACCOUNTANT'] as const },
    { to: '/reports', label: t('nav.reports'), roles: ['ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
    { to: '/zones/verification', label: t('nav.verificationQueue', { defaultValue: 'Verification' }), roles: ['ADMIN', 'OWNER', 'DEV'] as const },
    { to: '/owner-check', label: t('nav.ownerInsights'), roles: ['OWNER'] as const },
    { to: '/admin/users', label: t('nav.adminUsers'), roles: ['OWNER', 'DEV'] as const },
    { to: '/settings', label: t('nav.settings'), roles: ['STOCK', 'ADMIN', 'ACCOUNTANT', 'OWNER', 'DEV'] as const },
    { to: '/dev', label: t('nav.devTools'), roles: ['DEV'] as const }
  ].filter((x) => (role ? x.roles.includes(role as never) : false))

  return (
    <div className="min-h-screen">
      <header className="card border-b border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-sm font-semibold tracking-wide">
            {t('app.name')}
          </Link>
          <div className="flex items-center gap-3">
            <button
              className="rounded border border-[color:var(--color-border)] px-3 py-1 text-xs text-white/80 hover:bg-white/10"
              onClick={() => i18n.changeLanguage(i18n.language === 'th' ? 'en' : 'th')}
              type="button"
            >
              {i18n.language === 'th' ? 'EN' : 'TH'}
            </button>
            <div className="text-xs text-white/70">{user?.display_name ?? user?.username}</div>
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
          <nav className="card space-y-1 rounded border border-[color:var(--color-border)] bg-[color:var(--color-card)]/85 p-2 backdrop-blur">
            {navItems.map((x) => (
              <NavLink key={x.to} to={x.to} className={({ isActive }) => navClass(isActive)}>
                {x.label}
              </NavLink>
            ))}
          </nav>
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

