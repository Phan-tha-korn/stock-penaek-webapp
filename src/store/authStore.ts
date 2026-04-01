import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { AuthTokens, Role, User } from '../types/models'

interface AuthState {
  user: User | null
  role: Role | null
  tokens: AuthTokens | null
  sessionStartedAt: string | null
  reauthRequired: boolean
  pendingMutationCount: number
  setTokens: (tokens: AuthTokens | null) => void
  setSession: (user: User, tokens: AuthTokens, options?: { freshLogin?: boolean }) => void
  markReauthRequired: (required: boolean) => void
  incrementPendingMutation: () => void
  decrementPendingMutation: () => void
  clearSession: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      role: null,
      tokens: null,
      sessionStartedAt: null,
      reauthRequired: false,
      pendingMutationCount: 0,
      setTokens: (tokens) => set({ tokens }),
      setSession: (user, tokens, options) =>
        set((state) => ({
          user,
          role: user.role,
          tokens,
          reauthRequired: false,
          sessionStartedAt: options?.freshLogin || !state.sessionStartedAt ? new Date().toISOString() : state.sessionStartedAt
        })),
      markReauthRequired: (required) => set({ reauthRequired: required }),
      incrementPendingMutation: () => set((state) => ({ pendingMutationCount: state.pendingMutationCount + 1 })),
      decrementPendingMutation: () => set((state) => ({ pendingMutationCount: Math.max(0, state.pendingMutationCount - 1) })),
      clearSession: () => set({ user: null, role: null, tokens: null, sessionStartedAt: null, reauthRequired: false, pendingMutationCount: 0 })
    }),
    {
      name: 'esp_auth_v1',
      partialize: (s) => ({ user: s.user, role: s.role, tokens: s.tokens, sessionStartedAt: s.sessionStartedAt })
    }
  )
)

