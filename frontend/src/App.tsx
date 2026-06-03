// ─── App root: proveïdor d'estat i routing ───────────────────────────────────

import { useReducer } from 'react'
import { AppContext, appReducer, initialState, useAppStore } from './store/appStore'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { useInitApp } from './hooks/useInitApp'

function AppContent() {
  const { state } = useAppStore()
  useInitApp()
  return state.session ? <DashboardPage /> : <LoginPage />
}

export default function App() {
  const [state, dispatch] = useReducer(appReducer, initialState)

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      <AppContent />
    </AppContext.Provider>
  )
}
