import { Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { SessionGuard } from './components/auth/SessionGuard'
import { AppShell } from './components/layout/AppShell'
import { AppErrorBoundary } from './components/system/AppErrorBoundary'
import { ConfirmDialogProvider } from './components/ui/ConfirmDialog'
import { featureFlags } from './config/features'
import { lazyWithRetry } from './utils/lazyWithRetry'

const DashboardPage = lazyWithRetry(() => import('./pages/app/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const ZoneLandingPage = lazyWithRetry(() => import('./pages/app/zones/ZoneLandingPage').then((m) => ({ default: m.ZoneLandingPage })))
const ZoneDashboardPage = lazyWithRetry(() => import('./pages/app/zones/ZoneDashboardPage').then((m) => ({ default: m.ZoneDashboardPage })))
const SearchWorkspacePage = lazyWithRetry(() => import('./pages/app/zones/SearchWorkspacePage').then((m) => ({ default: m.SearchWorkspacePage })))
const VerificationWorkspacePage = lazyWithRetry(() => import('./pages/app/zones/VerificationWorkspacePage').then((m) => ({ default: m.VerificationWorkspacePage })))
const NotificationsPage = lazyWithRetry(() => import('./pages/app/zones/NotificationsPage').then((m) => ({ default: m.NotificationsPage })))
const ProductsPage = lazyWithRetry(() => import('./pages/app/ProductsPage').then((m) => ({ default: m.ProductsPage })))
const SuppliersPage = lazyWithRetry(() => import('./pages/app/SuppliersPage').then((m) => ({ default: m.SuppliersPage })))
const TransactionsPage = lazyWithRetry(() => import('./pages/app/TransactionsPage').then((m) => ({ default: m.TransactionsPage })))
const ReportsPage = lazyWithRetry(() => import('./pages/app/ReportsPage').then((m) => ({ default: m.ReportsPage })))
const UsersPage = lazyWithRetry(() => import('./pages/app/UsersPage').then((m) => ({ default: m.UsersPage })))
const DevPage = lazyWithRetry(() => import('./pages/app/DevPage').then((m) => ({ default: m.DevPage })))
const OwnerCheckPage = lazyWithRetry(() => import('./pages/app/OwnerCheckPage').then((m) => ({ default: m.OwnerCheckPage })))
const SettingsPage = lazyWithRetry(() => import('./pages/app/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const LoginPage = lazyWithRetry(() => import('./pages/public/LoginPage').then((m) => ({ default: m.LoginPage })))
const ForbiddenPage = lazyWithRetry(() => import('./pages/public/ForbiddenPage').then((m) => ({ default: m.ForbiddenPage })))
const NotFoundPage = lazyWithRetry(() => import('./pages/public/NotFoundPage').then((m) => ({ default: m.NotFoundPage })))
const PublicProductPage = lazyWithRetry(() => import('./pages/public/PublicProductPage').then((m) => ({ default: m.PublicProductPage })))

function AppFallback() {
  const { t } = useTranslation()
  return <div className="flex min-h-screen items-center justify-center text-sm text-[color:var(--color-muted)]">{t('app.loading')}</div>
}

export function App() {
  return (
    <AppErrorBoundary>
      <ConfirmDialogProvider>
      <Suspense fallback={<AppFallback />}>
        <SessionGuard />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forbidden" element={<ForbiddenPage />} />
          <Route path="/public/product/:sku" element={<PublicProductPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<ZoneLandingPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/products" element={<ProductsPage />} />
              <Route path="/zones/search" element={<SearchWorkspacePage />} />
              <Route path="/zones/notifications" element={<NotificationsPage />} />
              {featureFlags.supplierModule ? <Route path="/suppliers" element={<SuppliersPage />} /> : null}
              <Route path="/transactions" element={<TransactionsPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route element={<ProtectedRoute allow={['OWNER']} />}>
                <Route path="/zones/owner" element={<ZoneDashboardPage zone="owner" />} />
              </Route>
              <Route element={<ProtectedRoute allow={['OWNER', 'DEV']} />}>
                <Route path="/zones/dev" element={<ZoneDashboardPage zone="dev" />} />
              </Route>
              <Route element={<ProtectedRoute allow={['OWNER', 'DEV', 'ADMIN']} />}>
                <Route path="/zones/admin" element={<ZoneDashboardPage zone="admin" />} />
                <Route path="/zones/verification" element={<VerificationWorkspacePage />} />
              </Route>
              <Route path="/zones/stock" element={<ZoneDashboardPage zone="stock" />} />
              <Route path="/zones/stock/search" element={<SearchWorkspacePage />} />
              <Route element={<ProtectedRoute allow={['OWNER']} />}>
                <Route path="/owner-check" element={<OwnerCheckPage />} />
              </Route>
              <Route element={<ProtectedRoute allow={['OWNER', 'DEV']} />}>
                <Route path="/admin/users" element={<UsersPage />} />
              </Route>
              <Route path="/settings" element={<SettingsPage />} />
              <Route element={<ProtectedRoute allow={['DEV']} />}>
                <Route path="/dev" element={<DevPage />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
      </ConfirmDialogProvider>
    </AppErrorBoundary>
  )
}
