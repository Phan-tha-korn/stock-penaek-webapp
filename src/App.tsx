import { Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { SessionGuard } from './components/auth/SessionGuard'
import { AppShell } from './components/layout/AppShell'
import { AppErrorBoundary } from './components/system/AppErrorBoundary'
import { lazyWithRetry } from './utils/lazyWithRetry'

const DashboardPage = lazyWithRetry(() => import('./pages/app/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const ProductsPage = lazyWithRetry(() => import('./pages/app/ProductsPage').then((m) => ({ default: m.ProductsPage })))
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
  return <div className="flex min-h-screen items-center justify-center text-sm text-white/70">กำลังโหลด...</div>
}

export function App() {
  return (
    <AppErrorBoundary>
      <Suspense fallback={<AppFallback />}>
        <SessionGuard />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forbidden" element={<ForbiddenPage />} />
          <Route path="/public/product/:sku" element={<PublicProductPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/products" element={<ProductsPage />} />
              <Route path="/transactions" element={<TransactionsPage />} />
              <Route path="/reports" element={<ReportsPage />} />
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
    </AppErrorBoundary>
  )
}
