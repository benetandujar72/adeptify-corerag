// ─── Pàgina principal del dashboard (nucli obert) ────────────────────────────
// El menú superior commuta entre vistes del NUCLI: xat (inici + agents),
// documents, configuració, administració, usuaris i seguretat de xarxa.
// Els mòduls de gestió escolar viuen a `adeptify-suiterag`.

import { useEffect } from 'react'
import { TopBar } from '../components/layout/TopBar'
import { Sidebar } from '../components/sidebar/Sidebar'
import { ChatArea } from '../components/chat/ChatArea'
import { ContextPanel } from '../components/context/ContextPanel'
import { DocumentsPage } from './DocumentsPage'
import { ConfigPage } from './ConfigPage'
import { AdminPage } from './AdminPage'
import { AjudaPage } from './AjudaPage'
import { UsuarisPage } from './UsuarisPage'
import { SeguretatPage } from './SeguretatPage'
import { useAppStore } from '../store/appStore'
import type { Vista } from '../types'

const ROLS_USUARIS = ['direccio', 'superadmin']
const ROLS_SEGURETAT = ['direccio', 'superadmin']

/** Guarda d'accés per vista (RBAC al frontend; l'API ja la fa complir al backend). */
function vistaPermesa(vista: Vista, rol?: string): boolean {
  if (vista === 'admin') return rol === 'superadmin'
  if (vista === 'usuaris') return !!rol && ROLS_USUARIS.includes(rol)
  if (vista === 'seguretat') return !!rol && ROLS_SEGURETAT.includes(rol)
  return true
}

export function DashboardPage() {
  const { state, dispatch } = useAppStore()
  const rol = state.session?.rol

  // Si la vista actual no és permesa per al rol (p. ex. 'admin' heretada d'una
  // sessió anterior de superadmin), torna a 'inici'.
  useEffect(() => {
    if (!vistaPermesa(state.vista, rol)) {
      dispatch({ type: 'SET_VISTA', payload: 'inici' })
    }
  }, [state.vista, rol, dispatch])

  const vista = vistaPermesa(state.vista, rol) ? state.vista : 'inici'

  return (
    <div className="flex flex-col h-screen bg-fons overflow-hidden min-w-[900px]">
      <TopBar />
      {vista === 'documents' ? (
        <DocumentsPage />
      ) : vista === 'config' ? (
        <ConfigPage />
      ) : vista === 'admin' ? (
        <AdminPage />
      ) : vista === 'ajuda' ? (
        <AjudaPage />
      ) : vista === 'usuaris' ? (
        <UsuarisPage />
      ) : vista === 'seguretat' ? (
        <SeguretatPage />
      ) : (
        // inici · tutoria · secretaria · families → interfície de xat
        <div className="flex flex-1 min-h-0 overflow-hidden">
          <Sidebar />
          <ChatArea />
          <ContextPanel />
        </div>
      )}
    </div>
  )
}
