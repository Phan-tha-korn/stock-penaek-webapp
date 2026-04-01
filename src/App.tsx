import { Suspense, lazy } from 'react'
import { Routes, Route } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'

const DashboardPage = lazy(() => import('./pages/app/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const ProductsPage = lazy(() => import('./pages/app/ProductsPage').then((m) => ({ default: m.ProductsPage })))
const TransactionsPage = lazy(() => import('./pages/app/TransactionsPage').then((m) => ({ default: m.TransactionsPage })))
const ReportsPage = lazy(() => import('./pages/app/ReportsPage').then((m) => ({ default: m.ReportsPage })))
const UsersPage = lazy(() => import('./pages/app/UsersPage').then((m) => ({ default: m.UsersPage })))
const DevPage = lazy(() => import('./pages/app/DevPage').then((m) => ({ default: m.DevPage })))
const OwnerCheckPage = lazy(() => import('./pages/app/OwnerCheckPage').then((m) => ({ default: m.OwnerCheckPage })))
const SettingsPage = lazy(() => import('./pages/app/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const LoginPage = lazy(() => import('./pages/public/LoginPage').then((m) => ({ default: m.LoginPage })))
const ForbiddenPage = lazy(() => import('./pages/public/ForbiddenPage').then((m) => ({ default: m.ForbiddenPage })))
const NotFoundPage = lazy(() => import('./pages/public/NotFoundPage').then((m) => ({ default: m.NotFoundPage })))
const PublicProductPage = lazy(() => import('./pages/public/PublicProductPage').then((m) => ({ default: m.PublicProductPage })))

export function App() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center text-sm text-white/70">กำลังโหลด...</div>}>
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
  )
}

