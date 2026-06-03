// ─── Sidebar esquerra ─────────────────────────────────────────────────────────

import { useState } from 'react'
import { Search, Plus, ChevronDown, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { useAppStore } from '../../store/appStore'
import { fetchConversation, deleteConversation } from '../../api/client'
import type { Agent, MissatgeUI } from '../../types'

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'ara mateix'
  if (mins < 60) return `fa ${mins} min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `fa ${hours} h`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'ahir'
  return new Date(iso).toLocaleDateString('ca', { day: '2-digit', month: '2-digit' })
}

function AgentDot({ color }: { color: string }) {
  return (
    <span
      className="w-3 h-3 rounded-full shrink-0 inline-block"
      style={{ background: color }}
    />
  )
}

export function Sidebar() {
  const { state, dispatch } = useAppStore()
  const [agentOpen, setAgentOpen] = useState(false)
  const [search, setSearch] = useState('')

  // Agents accessibles al rol de l'usuari
  const agentsDisponibles: Agent[] = state.session
    ? state.agents.filter(a => a.rols_permesos.includes(state.session!.rol))
    : state.agents

  const filteredConvs = state.conversations.filter(c =>
    c.titol.toLowerCase().includes(search.toLowerCase()) ||
    c.etiqueta.toLowerCase().includes(search.toLowerCase()),
  )

  async function handleSelectConv(id: string) {
    if (id === state.conversaActiva) return
    dispatch({ type: 'SET_LOADING_CONV', payload: true })
    dispatch({ type: 'SET_CONVERSA_ACTIVA', payload: id })
    dispatch({ type: 'SET_FONTS_ACTIVES', payload: [] })
    try {
      const data = await fetchConversation(id)
      dispatch({ type: 'SET_MESSAGES', payload: data.messages as MissatgeUI[] })
      // Fonts de l'últim missatge de l'assistent
      const lastAsst = [...data.messages].reverse().find(m => m.rol === 'assistant')
      if (lastAsst?.fonts) {
        dispatch({ type: 'SET_FONTS_ACTIVES', payload: lastAsst.fonts })
      }
    } catch {
      dispatch({ type: 'SET_ERROR', payload: 'No s\'ha pogut carregar la conversa.' })
    } finally {
      dispatch({ type: 'SET_LOADING_CONV', payload: false })
    }
  }

  function handleNewConv() {
    dispatch({ type: 'SET_CONVERSA_ACTIVA', payload: null })
    dispatch({ type: 'SET_MESSAGES', payload: [] })
    dispatch({ type: 'SET_FONTS_ACTIVES', payload: [] })
    dispatch({ type: 'SET_ERROR', payload: null })
  }

  async function handleDeleteConv(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    try {
      await deleteConversation(id)
      dispatch({ type: 'REMOVE_CONVERSATION', payload: id })
    } catch {
      // silenciós
    }
  }

  const ss = state.systemStatus

  return (
    <aside className="w-[220px] xl:w-[240px] shrink-0 bg-white border-r border-border flex flex-col h-full">
      {/* Nova conversa */}
      <div className="p-3">
        <button
          onClick={handleNewConv}
          className="w-full flex items-center gap-2 bg-terra text-white rounded-lg px-4 py-2.5 font-semibold text-sm hover:bg-terra/90 transition-colors shadow-sm"
        >
          <Plus size={16} />
          Nova conversa
        </button>
      </div>

      {/* Agent actiu */}
      <div className="px-3 pb-2">
        <label className="text-xs font-bold text-muted tracking-wide uppercase block mb-1.5">
          Agent actiu
        </label>
        <div className="relative">
          <button
            onClick={() => setAgentOpen(v => !v)}
            className="w-full flex items-center gap-2 bg-crema border border-border rounded-md px-3 py-2 text-sm text-dark hover:border-navy/30 transition-colors"
          >
            {state.agentActiu ? (
              <>
                <AgentDot color={state.agentActiu.color} />
                <span className="flex-1 text-left truncate">{state.agentActiu.nom}</span>
              </>
            ) : (
              <span className="flex-1 text-left text-muted">Selecciona un agent…</span>
            )}
            <ChevronDown size={14} className="text-muted shrink-0" />
          </button>

          {agentOpen && agentsDisponibles.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-border rounded-lg shadow-lg z-30 overflow-hidden">
              {agentsDisponibles.map(agent => (
                <button
                  key={agent.id}
                  onClick={() => {
                    dispatch({ type: 'SET_AGENT_ACTIU', payload: agent })
                    setAgentOpen(false)
                  }}
                  className={clsx(
                    'w-full flex items-center gap-2 px-3 py-2.5 text-sm text-dark hover:bg-crema transition-colors text-left',
                    state.agentActiu?.id === agent.id && 'bg-crema font-medium',
                  )}
                >
                  <AgentDot color={agent.color} />
                  <div>
                    <div className="font-medium">{agent.nom}</div>
                    <div className="text-xs text-muted line-clamp-1">{agent.descripcio}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Cerca converses */}
      <div className="px-3 pb-3">
        <div className="flex items-center gap-2 bg-crema border border-border rounded-md px-3 py-1.5">
          <Search size={13} className="text-muted shrink-0" />
          <input
            type="text"
            placeholder="Cerca converses..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="bg-transparent text-sm text-dark placeholder:text-muted w-full outline-none"
          />
        </div>
      </div>

      {/* Converses recents */}
      <div className="px-3 pb-1">
        <span className="text-xs font-bold text-muted tracking-wide uppercase">
          Converses recents
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-1 pb-2 space-y-1">
        {state.loadingConv && (
          <div className="flex justify-center py-4">
            <div className="w-5 h-5 border-2 border-terra border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!state.loadingConv && filteredConvs.length === 0 && (
          <div className="text-center text-muted text-xs py-6 px-4">
            {search ? 'Cap conversa coincideix amb la cerca.' : 'Encara no hi ha converses.'}
          </div>
        )}

        {filteredConvs.map(conv => {
          const isActive = conv.id === state.conversaActiva
          return (
            <button
              key={conv.id}
              onClick={() => handleSelectConv(conv.id)}
              className={clsx(
                'w-full text-left rounded-md px-3 py-2.5 transition-colors group relative',
                isActive ? 'bg-crema' : 'hover:bg-crema/60',
              )}
            >
              {isActive && (
                <span className="absolute left-0 top-0 bottom-0 w-0.5 bg-terra rounded-l-md" />
              )}
              <div className="text-sm font-medium text-dark line-clamp-1">{conv.titol}</div>
              <div className="text-xs text-muted mt-0.5">{conv.etiqueta}</div>
              <div className={clsx('text-xs mt-0.5', isActive ? 'text-terra' : 'text-muted')}>
                {timeAgo(conv.actualitzat_el)}
              </div>
              <button
                onClick={e => handleDeleteConv(e, conv.id)}
                className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 hover:text-red-500 text-muted transition-all"
                title="Eliminar conversa"
              >
                <Trash2 size={12} />
              </button>
            </button>
          )
        })}
      </div>

      {/* Estat del sistema */}
      <div className="border-t border-border px-3 py-3 space-y-2">
        <div className="text-xs font-bold text-muted tracking-wide uppercase">
          Estat del sistema
        </div>
        <div className="flex items-center gap-2">
          <span className={clsx(
            'w-2 h-2 rounded-full shrink-0',
            ss?.servidor.actiu ? 'bg-green' : 'bg-red-400',
          )} />
          <span className="text-xs text-dark">
            {ss?.servidor.actiu ? 'Servidor local actiu' : 'Servidor no disponible'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={clsx(
            'w-2 h-2 rounded-full shrink-0',
            ss?.indexacio.al_dia ? 'bg-green' : 'bg-yellow-400',
          )} />
          <span className="text-xs text-dark">
            {ss?.indexacio.al_dia ? 'Indexació al dia' : 'Indexació pendent'}
          </span>
        </div>
        <div className="text-xs text-muted">
          {ss?.versio ?? 'v0.1.0-mvp'} · Adeptify
        </div>
      </div>
    </aside>
  )
}
