import { io, type Socket } from 'socket.io-client'

let socket: Socket | null = null
let currentUserId: string | null = null

export function getSocket(userId: string | null | undefined) {
  const enabled = (import.meta as any).env?.VITE_SOCKET_ENABLED === 'true'
  const baseUrl = (import.meta as any).env?.VITE_SOCKET_URL || ''
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
  socket = io(baseUrl || '/', { path: '/socket.io', auth: { user_id: userId } })
  return socket
}

