// ─── Hook d'inicialització de l'app ──────────────────────────────────────────
// Carrega agents, converses i estat del sistema al muntatge.

import { useEffect } from 'react'
import {
  fetchAgents,
  fetchConversations,
  fetchLlicencia,
  fetchMe,
  fetchMyInstitucio,
  fetchSystemStatus,
} from '../api/client'
import { applyBranding } from '../lib/branding'
import { useT, type Idioma } from '../i18n'
import { IDIOMES_ADMESOS } from '../i18n/catalogs'
import { useAppStore } from '../store/appStore'
import { teSortidaPendent } from '../auth/cookieSession'
import { ambTerminiSortida } from '../auth/terminiSortida'

export function useInitApp() {
  const { state, dispatch } = useAppStore()
  const { setIdioma } = useT()

  // La identitat es restaura des del servidor, mai des d’un JWT de JS.
  useEffect(() => {
    if (teSortidaPendent()) {
      void ambTerminiSortida(signal => fetch(`${import.meta.env.VITE_API_BASE_URL ?? '/api'}/auth/logout`, { method: 'POST', signal }))
        .then(r => { if (r.ok) localStorage.removeItem('adeptify_logout_pending') }).catch(() => {})
      return
    }
    let viu = true
    void fetchMe().then(me => {
      if (viu) dispatch({ type: 'SET_SESSION', payload: { usuari: me.usuari, rol: me.rol } })
    }).catch(() => { /* sense sessió: pantalla d’entrada */ })
    return () => { viu = false }
  }, [dispatch])

  useEffect(() => {
    const reset = () => dispatch({ type: 'SET_SESSION', payload: null })
    const changed = (event: StorageEvent) => {
      if (event.key === 'adeptify_session_changed' || event.key === 'adeptify_logout_pending') reset()
    }
    window.addEventListener('adeptify-session-expired', reset)
    window.addEventListener('storage', changed)
    return () => {
      window.removeEventListener('adeptify-session-expired', reset)
      window.removeEventListener('storage', changed)
    }
  }, [dispatch])

  // Quan hi ha sessió, carrega dades
  useEffect(() => {
    if (!state.session) return

    let viu = true
    const loadAll = async () => {
      dispatch({ type: 'SET_LOADING', payload: true })
      try {
        const [agents, conversations, status, institucio, me, llicencia] = await Promise.allSettled([
          fetchAgents(),
          fetchConversations(),
          fetchSystemStatus(),
          fetchMyInstitucio(),
          fetchMe(),
          fetchLlicencia(),
        ])
        if (!viu) return

        // Features llicenciades (per ocultar mòduls no inclosos al pla del centre).
        if (llicencia.status === 'fulfilled') {
          dispatch({ type: 'SET_FEATURES', payload: llicencia.value.features })
        }

        // Aplica l'idioma persistit al backend (si l'usuari no n'ha fet servir mai
        // un local). El selector de login el sobreescriu.
        if (me.status === 'fulfilled' && me.value.idioma && (IDIOMES_ADMESOS as string[]).includes(me.value.idioma)) {
          setIdioma(me.value.idioma as Idioma)
        }

        if (institucio.status === 'fulfilled') {
          dispatch({ type: 'SET_INSTITUCIO', payload: institucio.value })
          applyBranding(institucio.value.branding, institucio.value.nom)
        }

        if (agents.status === 'fulfilled') {
          dispatch({ type: 'SET_AGENTS', payload: agents.value })
          // Tria el primer agent accessible per al rol actual. El superadmin
          // (god mode) hi té accés a tots.
          const accessible =
            state.session!.rol === 'superadmin'
              ? agents.value
              : agents.value.filter(a => a.rols_permesos.includes(state.session!.rol))
          if (accessible.length > 0) {
            dispatch({ type: 'SET_AGENT_ACTIU', payload: accessible[0] })
          }
        }

        if (conversations.status === 'fulfilled') {
          dispatch({ type: 'SET_CONVERSATIONS', payload: conversations.value })
        }

        if (status.status === 'fulfilled') {
          dispatch({ type: 'SET_SYSTEM_STATUS', payload: status.value })
        }
      } catch {
        // errors individuals ja capturats per allSettled
      } finally {
        if (viu) dispatch({ type: 'SET_LOADING', payload: false })
      }
    }

    void loadAll()
    return () => { viu = false }
  }, [state.session, dispatch, setIdioma])

  // Refresca status del sistema cada 60 s
  useEffect(() => {
    if (!state.session) return

    const interval = setInterval(async () => {
      try {
        const status = await fetchSystemStatus()
        dispatch({ type: 'SET_SYSTEM_STATUS', payload: status })
      } catch {
        // silenciós
      }
    }, 60_000)

    return () => clearInterval(interval)
  }, [state.session, dispatch])
}
