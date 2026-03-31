import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { AuthTokens, Role, User } from '../types/models'

interface AuthState {
  user: User | null
  role: Role | null
  tokens: AuthTokens | null
  setTokens: (tokens: AuthTokens | null) => void
  setSession: (user: User, tokens: AuthTokens) => void
  clearSession: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      role: null,
      tokens: null,
      setTokens: (tokens) => set({ tokens }),
      setSession: (user, tokens) => set({ user, role: user.role, tokens }),
      clearSession: () => set({ user: null, role: null, tokens: null })
    }),
    {
      name: 'esp_auth_v1',
      partialize: (s) => ({ user: s.user, role: s.role, tokens: s.tokens })
    }
  )
)

