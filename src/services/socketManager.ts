import { io, type Socket } from 'socket.io-client'
import { useAuthStore } from '../store/authStore'

let socket: Socket | null = null
let currentUserId: string | null = null

export function getSocket(userId: string | null | undefined) {
  const enabled = import.meta.env.VITE_SOCKET_ENABLED === 'true'
  const baseUrl = import.meta.env.VITE_SOCKET_URL || ''
  if (!enabled) return null
  if (!userId) {
    if (socket) {
      socket.disconnect()
      socket = null
      currentUserId = null
    }
    return null
  }

  if (socket && currentUserId === userId) return socket

  if (socket) {
    socket.disconnect()
    socket = null
  }

  currentUserId = userId
  const token = useAuthStore.getState().tokens?.access_token || ''
  socket = io(baseUrl || '/', { path: '/socket.io', auth: { token, user_id: userId } })
  return socket
}

