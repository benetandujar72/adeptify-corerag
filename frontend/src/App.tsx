// ─── App root: proveïdor d'estat i routing ───────────────────────────────────

import { useReducer } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AppContext, appReducer, initialState, useAppStore } from './store/appStore'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { useInitApp } from './hooks/useInitApp'
import { useUrlVistaSync } from './hooks/useUrlVistaSync'

function AppContent() {
  const { state } = useAppStore()
  useInitApp()
  useUrlVistaSync() // URLs canòniques + deep-linking (sincronitza vista ↔ barra d'adreces)
  return state.session ? <DashboardPage /> : <LoginPage />
}

export default function App() {
  const [state, dispatch] = useReducer(appReducer, initialState)

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </AppContext.Provider>
  )
}
