import { Navigate, Outlet } from 'react-router-dom'

import { useAuthStore } from '../../store/authStore'
import type { Role } from '../../types/models'

export function ProtectedRoute(props: { allow?: Role[] }) {
  const user = useAuthStore((s) => s.user)
  const role = useAuthStore((s) => s.role)

  if (!user || !role) return <Navigate to="/login" replace />
  if (props.allow && !props.allow.includes(role)) return <Navigate to="/forbidden" replace />
  return <Outlet />
}

