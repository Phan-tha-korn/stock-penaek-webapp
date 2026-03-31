import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App'
import './styles/global.css'
import { initI18n } from './services/i18n'
import { useBootstrap } from './hooks/useBootstrap'

initI18n('th')

function Root() {
  const { ready } = useBootstrap()
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-white/70">กำลังโหลด...</div>
    )
  }
  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
)

