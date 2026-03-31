import { Routes, Route } from 'react-router-dom'

import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'
import { DashboardPage } from './pages/app/DashboardPage'
import { ProductsPage } from './pages/app/ProductsPage'
import { TransactionsPage } from './pages/app/TransactionsPage'
import { ReportsPage } from './pages/app/ReportsPage'
import { UsersPage } from './pages/app/UsersPage'
import { DevPage } from './pages/app/DevPage'
import { OwnerCheckPage } from './pages/app/OwnerCheckPage'
import { SettingsPage } from './pages/app/SettingsPage'
import { LoginPage } from './pages/public/LoginPage'
import { ForbiddenPage } from './pages/public/ForbiddenPage'
import { NotFoundPage } from './pages/public/NotFoundPage'
import { PublicProductPage } from './pages/public/PublicProductPage'

export function App() {
  return (
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
  )
}

