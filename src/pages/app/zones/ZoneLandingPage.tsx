import { Navigate } from 'react-router-dom'

import { useAuthStore } from '../../../store/authStore'

export function ZoneLandingPage() {
  const role = useAuthStore((s) => s.role)

  if (role === 'OWNER') return <Navigate to="/zones/owner" replace />
  if (role === 'DEV') return <Navigate to="/zones/dev" replace />
  if (role === 'ADMIN') return <Navigate to="/zones/admin" replace />
  return <Navigate to="/zones/stock/search" replace />
}
