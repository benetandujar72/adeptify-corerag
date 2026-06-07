// ─── Sincronització URL ↔ vista (deep-linking sense reescriure el render) ─────
// Manté la barra d'adreces alineada amb `state.vista` i viceversa: així hi ha URLs canòniques,
// es pot compartir l'enllaç, el botó enrere/endavant del navegador funciona i un refresc conserva
// la secció. No invasiu: la navegació interna segueix amb dispatch SET_VISTA; aquest hook només
// reflecteix l'estat a la URL i llegeix la URL inicial. Vegeu docs/REDISSENY_UI_UX.md (Fase 3).

import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import type { Vista } from '../types'

// Vistes navegables amb URL pròpia (s'exclouen els valors d'estat de matrícula: esborrany, etc.).
const ROUTABLE: Vista[] = [
  'inici', 'tutoria', 'secretaria', 'families', 'avaluacions', 'avaluacio', 'matricula',
  'assistencia', 'gestio', 'correu', 'tasques', 'importacio', 'expedients', 'pagaments', 'documents',
  'moodle_cursos', 'onboarding', 'config', 'admin', 'usuaris', 'skills', 'recursos', 'seguretat',
  'registre', 'certificats', 'comunicacions', 'panell_pas', 'agenda', 'ajuda',
]
const SET = new Set<string>(ROUTABLE)

function pathDeVista(v: Vista): string {
  return v === 'inici' ? '/' : `/${v}`
}
function vistaDePath(pathname: string): Vista | null {
  const seg = pathname.replace(/^\/+/, '').split('/')[0]
  if (seg === '') return 'inici'
  return SET.has(seg) ? (seg as Vista) : null
}

export function useUrlVistaSync() {
  const location = useLocation()
  const navigate = useNavigate()
  const { state, dispatch } = useAppStore()

  // URL → vista (càrrega inicial + enrere/endavant del navegador).
  useEffect(() => {
    const v = vistaDePath(location.pathname)
    if (v && v !== state.vista) dispatch({ type: 'SET_VISTA', payload: v })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname])

  // vista → URL (navegació interna via menú/paleta). Només per a vistes amb ruta pròpia.
  useEffect(() => {
    if (!SET.has(state.vista)) return
    const want = pathDeVista(state.vista)
    if (location.pathname !== want) navigate(want)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.vista])
}
