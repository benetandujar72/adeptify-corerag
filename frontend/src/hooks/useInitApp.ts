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
import type { Rol } from '../types'

export function useInitApp() {
  const { state, dispatch } = useAppStore()
  const { setIdioma } = useT()

  // Restaura sessió des de localStorage
  useEffect(() => {
    const token = localStorage.getItem('patufet_token')
    const usuari = localStorage.getItem('patufet_usuari')
    const rol = localStorage.getItem('patufet_rol') as Rol | null

    if (token && usuari && rol) {
      dispatch({ type: 'SET_SESSION', payload: { token, usuari, rol } })
    }
  }, [dispatch])

  // Quan hi ha sessió, carrega dades
  useEffect(() => {
    if (!state.session) return

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
        dispatch({ type: 'SET_LOADING', payload: false })
      }
    }

    void loadAll()
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
