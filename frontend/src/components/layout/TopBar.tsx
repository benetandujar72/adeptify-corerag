// ─── Barra superior (navbar navy) ────────────────────────────────────────────

import { useEffect, useRef, useState } from 'react'
import { HelpCircle, ChevronDown, LogOut } from 'lucide-react'
import { useAppStore } from '../../store/appStore'
import { logoInicials, resetBranding } from '../../lib/branding'
import { useT } from '../../i18n'
import type { Vista } from '../../types'

interface NavDef {
  label: string
  i18nKey?: string  // si es defineix, sobreescriu `label` en l'idioma actiu
  vista: Vista
  agentId?: string // si l'ítem obre un agent concret
  soloSuperadmin?: boolean
  rols?: string[] // si es defineix, només visible per a aquests rols
  feature?: string // si es defineix, només visible si la llicència l'inclou
}

interface NavGroup {
  label: string
  i18nKey?: string
  items: NavDef[]
}

// "Inici" queda solt, fora de qualsevol grup.
const INICI: NavDef = { label: 'Inici', i18nKey: 'menu.inici', vista: 'inici' }

// Els ítems s'agrupen en menús desplegables per categoria. Cada NavDef
// conserva EXACTAMENT els seus camps de filtratge per rol (agentId,
// soloSuperadmin, rols); només canvia la presentació.
// NUCLI OBERT: només assistents de xat (RAG) + sistema. Els mòduls de gestió
// escolar (matrícula, avaluació, pagaments…) viuen a `adeptify-suiterag`.
const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Assistents', i18nKey: 'menu.agents',
    items: [
      { label: 'Tutoria', vista: 'tutoria', agentId: 'tutor_mates' },
      { label: 'Secretaria', vista: 'secretaria', agentId: 'secretaria' },
      { label: 'Famílies', vista: 'families', agentId: 'families' },
      { label: 'Gestió IA', vista: 'gestio', agentId: 'assistent_admin' },
    ],
  },
  {
    label: 'Sistema', i18nKey: 'menu.sistema',
    items: [
      { label: 'Documents', i18nKey: 'menu.documents', vista: 'documents' },
      { label: 'Usuaris del centre', i18nKey: 'menu.usuaris_centre', vista: 'usuaris', rols: ['direccio', 'superadmin'] },
      { label: 'Seguretat de xarxa', i18nKey: 'menu.seguretat_xarxa', vista: 'seguretat', rols: ['direccio', 'superadmin'] },
      { label: 'Configuració', i18nKey: 'menu.configuracio', vista: 'config' },
      { label: 'Administració', i18nKey: 'menu.administracio', vista: 'admin', soloSuperadmin: true },
    ],
  },
]

export function TopBar() {
  const { state, dispatch } = useAppStore()
  const { t } = useT()
  // Identifica el menú obert: etiqueta d'un grup, 'user', o null (cap obert).
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  // Botó que ha obert el menú actual, per retornar-hi el focus en prémer Escape.
  const openTriggerRef = useRef<HTMLButtonElement>(null)

  // Tanca el menú obert en clicar fora o prémer Escape (accessibilitat).
  useEffect(() => {
    if (!openMenu) return
    function onMouseDown(e: MouseEvent) {
      const target = e.target
      if (target instanceof Element && target.closest('[data-menuroot]')) return
      setOpenMenu(null)
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        openTriggerRef.current?.focus()
        setOpenMenu(null)
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [openMenu])

  // Només mostrem els ítems d'agent que el rol pot fer servir. El superadmin
  // (god mode) hi té accés a tots.
  const accessibleAgentIds = new Set(
    state.session
      ? state.session.rol === 'superadmin'
        ? state.agents.map(a => a.id)
        : state.agents.filter(a => a.rols_permesos.includes(state.session!.rol)).map(a => a.id)
      : [],
  )

  // Filtratge per features llicenciades. Si `featuresActives` és null (encara no
  // carregat) o el superadmin (operador de flota), no s'amaga res per llicència.
  function featureActiva(feature?: string): boolean {
    if (!feature) return true
    if (state.session?.rol === 'superadmin') return true
    if (state.featuresActives === null) return true  // retrocompat / carregant
    return state.featuresActives.includes(feature)
  }

  // Mateix filtratge per rol que abans (agentId / soloSuperadmin / rols) + feature.
  function isVisible(n: NavDef): boolean {
    return (
      (!n.agentId || accessibleAgentIds.has(n.agentId)) &&
      (!n.soloSuperadmin || state.session?.rol === 'superadmin') &&
      (!n.rols || (state.session ? n.rols.includes(state.session.rol) : false)) &&
      featureActiva(n.feature)
    )
  }

  // Tradueix l'etiqueta d'un ítem si té i18nKey; altrament conserva la literal.
  const tr = (n: { label: string; i18nKey?: string }) => (n.i18nKey ? t(n.i18nKey) : n.label)

  // Per a cada grup, filtra els ítems visibles; amaga el grup si queda buit.
  const visibleGroups = NAV_GROUPS.map(g => ({
    label: tr(g),
    items: g.items.filter(isVisible),
  })).filter(g => g.items.length > 0)

  function handleNav(item: NavDef) {
    dispatch({ type: 'SET_VISTA', payload: item.vista })
    if (item.agentId) {
      const agent = state.agents.find(a => a.id === item.agentId)
      if (agent) {
        dispatch({ type: 'SET_AGENT_ACTIU', payload: agent })
        dispatch({ type: 'SET_CONVERSA_ACTIVA', payload: null })
        dispatch({ type: 'SET_MESSAGES', payload: [] })
        dispatch({ type: 'SET_FONTS_ACTIVES', payload: [] })
      }
    }
    setOpenMenu(null) // tanca el desplegable després de navegar
  }

  function handleLogout() {
    localStorage.removeItem('patufet_token')
    localStorage.removeItem('patufet_usuari')
    localStorage.removeItem('patufet_rol')
    dispatch({ type: 'SET_SESSION', payload: null })
    dispatch({ type: 'SET_INSTITUCIO', payload: null })
    dispatch({ type: 'SET_AGENTS', payload: [] })
    dispatch({ type: 'SET_CONVERSATIONS', payload: [] })
    dispatch({ type: 'SET_MESSAGES', payload: [] })
    dispatch({ type: 'SET_VISTA', payload: 'inici' }) // evita que una vista privilegiada (admin) persisteixi al següent login
    resetBranding()
    setOpenMenu(null)
  }

  // Branding de la institució (amb fallback a Nou Patufet).
  const inst = state.institucio
  const instNom = inst?.nom ?? 'Nou Patufet'
  const instLema = inst?.branding?.lema ?? '· IA Assistent'
  const logoUrl = inst?.branding?.logo_url
  const logoText = logoInicials(inst?.branding, inst?.nom ?? 'Nou Patufet')

  const initials = state.session
    ? state.session.usuari
        .split(/[\s._-]/)
        .map(p => p[0]?.toUpperCase() ?? '')
        .slice(0, 2)
        .join('')
    : 'U'

  const rolLabel: Record<string, string> = {
    docent: 'Docent',
    alumne: 'Alumne',
    familia: 'Família',
    direccio: 'Direcció',
    pas: 'PAS',
    superadmin: 'Superadmin',
  }

  return (
    <header className="bg-navy flex items-center h-[60px] px-4 gap-4 shrink-0 relative z-20">
      {/* Logo (branding per institució) */}
      <div className="flex items-center gap-3 mr-6">
        <div className="w-9 h-9 rounded-full bg-terra flex items-center justify-center shrink-0 overflow-hidden">
          {logoUrl ? (
            <img src={logoUrl} alt={instNom} className="w-full h-full object-cover" />
          ) : (
            <span className="text-white font-bold text-sm leading-none">{logoText}</span>
          )}
        </div>
        <div className="leading-tight">
          <div className="text-white font-bold text-sm">{instNom}</div>
          <div className="text-sage text-xs">{instLema}</div>
        </div>
      </div>

      {/* Navegació: "Inici" solt + grups desplegables per categoria */}
      <nav className="flex items-center gap-1 flex-1">
        {/* Inici (sense desplegable) */}
        <button
          onClick={() => handleNav(INICI)}
          className={`px-3 py-1.5 text-sm rounded transition-colors relative ${
            state.vista === INICI.vista
              ? 'text-white font-semibold'
              : 'text-navyborder hover:text-white'
          }`}
        >
          {tr(INICI)}
          {state.vista === INICI.vista && (
            <span className="absolute bottom-0 left-3 right-3 h-0.5 bg-terra rounded-full" />
          )}
        </button>

        {/* Grups desplegables */}
        {visibleGroups.map((group, gi) => {
          const groupActive = group.items.some(it => it.vista === state.vista)
          const isOpen = openMenu === group.label
          const panelId = `nav-group-${gi}`
          return (
            <div key={group.label} data-menuroot className="relative">
              <button
                ref={isOpen ? openTriggerRef : null}
                onClick={() => setOpenMenu(o => (o === group.label ? null : group.label))}
                aria-expanded={isOpen}
                aria-controls={panelId}
                className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded transition-colors relative ${
                  groupActive || isOpen
                    ? 'text-white font-semibold'
                    : 'text-navyborder hover:text-white'
                }`}
              >
                {group.label}
                <ChevronDown
                  size={14}
                  className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
                />
                {groupActive && (
                  <span className="absolute bottom-0 left-3 right-3 h-0.5 bg-terra rounded-full" />
                )}
              </button>

              {isOpen && (
                <div
                  id={panelId}
                  className="absolute left-0 top-full mt-2 min-w-[200px] bg-white rounded-lg shadow-lg border border-border py-1 z-50"
                >
                  {group.items.map(item => {
                    const itemActive = state.vista === item.vista
                    return (
                      <button
                        key={item.vista}
                        onClick={() => handleNav(item)}
                        className={`w-full flex items-center justify-between gap-2 px-4 py-2 text-sm text-left transition-colors ${
                          itemActive
                            ? 'text-terra font-semibold bg-crema'
                            : 'text-dark hover:bg-crema'
                        }`}
                      >
                        {tr(item)}
                        {itemActive && (
                          <span className="w-1.5 h-1.5 rounded-full bg-terra shrink-0" />
                        )}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      {/* Badge sistema local */}
      <div className="hidden md:flex items-center gap-2 bg-navylight px-3 py-1.5 rounded-full">
        <span className="w-2 h-2 rounded-full bg-green shrink-0" />
        <span className="text-white text-xs whitespace-nowrap">Sistema local · 100% intern</span>
      </div>

      {/* Usuari */}
      {state.session && (
        <div data-menuroot className="relative ml-2">
          <button
            ref={openMenu === 'user' ? openTriggerRef : null}
            onClick={() => setOpenMenu(o => (o === 'user' ? null : 'user'))}
            aria-expanded={openMenu === 'user'}
            aria-controls="user-menu"
            className="flex items-center gap-2 hover:opacity-90 transition-opacity"
          >
            <div className="text-right hidden sm:block">
              <div className="text-white text-xs font-medium leading-tight">{state.session.usuari}</div>
              <div className="text-sage text-xs leading-tight">{rolLabel[state.session.rol] ?? state.session.rol}</div>
            </div>
            <div className="w-9 h-9 rounded-full bg-terra flex items-center justify-center shrink-0">
              <span className="text-white font-bold text-sm">{initials}</span>
            </div>
            <ChevronDown size={14} className="text-white" />
          </button>

          {openMenu === 'user' && (
            <div id="user-menu" className="absolute right-0 top-full mt-2 w-44 bg-white rounded-lg shadow-lg border border-border py-1 z-50">
              <div className="px-4 py-2 text-xs text-muted border-b border-border">
                {state.session.usuari}
                <br />
                <span className="font-medium">{rolLabel[state.session.rol]}</span>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-4 py-2 text-sm text-dark hover:bg-crema transition-colors"
              >
                <LogOut size={14} />
                {t('menu.tanca_sessio')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Ajuda */}
      <button
        onClick={() => dispatch({ type: 'SET_VISTA', payload: 'ajuda' })}
        title="Ajuda"
        className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
          state.vista === 'ajuda' ? 'bg-terra' : 'bg-navylight hover:bg-navy'
        }`}
      >
        <HelpCircle size={16} className="text-white" />
      </button>
    </header>
  )
}
