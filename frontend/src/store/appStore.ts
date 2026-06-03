// ─── Store global lleuger (sense Redux) ──────────────────────────────────────
// Usa React Context + useReducer. Tipus inferits de l'API.

import { createContext, useContext } from 'react'
import type {
  Agent,
  Conversa,
  Font,
  Institucio,
  MissatgeUI,
  RecursSuggerit,
  SystemStatus,
  UserSession,
  Vista,
} from '../types'

export interface AppState {
  // Navegació (vista del menú superior)
  vista: Vista
  // Auth
  session: UserSession | null
  // Institució (tenant) de l'usuari: branding + config
  institucio: Institucio | null
  // Agents
  agents: Agent[]
  agentActiu: Agent | null
  // Converses
  conversations: Conversa[]
  conversaActiva: string | null   // id
  messages: MissatgeUI[]
  // Context panell dret (última resposta IA)
  fontsActives: Font[]
  // Documentació verificada suggerida pel sistema (F2)
  recursosActius: RecursSuggerit[]
  // Sistema
  systemStatus: SystemStatus | null
  // Features llicenciades del centre (null = encara no carregat → mostra-ho tot)
  featuresActives: string[] | null
  // UI
  loading: boolean
  loadingConv: boolean
  error: string | null
  streamingId: string | null      // id del missatge en streaming
}

export type AppAction =
  | { type: 'SET_VISTA'; payload: Vista }
  | { type: 'SET_SESSION'; payload: UserSession | null }
  | { type: 'SET_INSTITUCIO'; payload: Institucio | null }
  | { type: 'SET_AGENTS'; payload: Agent[] }
  | { type: 'SET_AGENT_ACTIU'; payload: Agent | null }
  | { type: 'SET_CONVERSATIONS'; payload: Conversa[] }
  | { type: 'SET_CONVERSA_ACTIVA'; payload: string | null }
  | { type: 'SET_MESSAGES'; payload: MissatgeUI[] }
  | { type: 'APPEND_MESSAGE'; payload: MissatgeUI }
  | { type: 'UPDATE_STREAMING'; payload: { id: string; delta: string } }
  | { type: 'FINISH_STREAMING'; payload: { id: string; missatge: MissatgeUI } }
  | { type: 'SET_FONTS_ACTIVES'; payload: Font[] }
  | { type: 'SET_RECURSOS_ACTIUS'; payload: RecursSuggerit[] }
  | { type: 'SET_SYSTEM_STATUS'; payload: SystemStatus }
  | { type: 'SET_FEATURES'; payload: string[] | null }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_LOADING_CONV'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null }
  | { type: 'SET_STREAMING_ID'; payload: string | null }
  | { type: 'ADD_CONVERSATION'; payload: Conversa }
  | { type: 'REMOVE_CONVERSATION'; payload: string }

export const initialState: AppState = {
  vista: 'inici',
  session: null,
  institucio: null,
  agents: [],
  agentActiu: null,
  conversations: [],
  conversaActiva: null,
  messages: [],
  fontsActives: [],
  recursosActius: [],
  systemStatus: null,
  featuresActives: null,
  loading: false,
  loadingConv: false,
  error: null,
  streamingId: null,
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_VISTA':
      return { ...state, vista: action.payload }
    case 'SET_SESSION':
      return { ...state, session: action.payload }
    case 'SET_INSTITUCIO':
      return { ...state, institucio: action.payload }
    case 'SET_AGENTS':
      return { ...state, agents: action.payload }
    case 'SET_AGENT_ACTIU':
      return { ...state, agentActiu: action.payload }
    case 'SET_CONVERSATIONS':
      return { ...state, conversations: action.payload }
    case 'SET_CONVERSA_ACTIVA':
      return { ...state, conversaActiva: action.payload }
    case 'SET_MESSAGES':
      return { ...state, messages: action.payload }
    case 'APPEND_MESSAGE':
      return { ...state, messages: [...state.messages, action.payload] }
    case 'UPDATE_STREAMING': {
      const msgs = state.messages.map(m =>
        m.id === action.payload.id
          ? { ...m, streamBuffer: (m.streamBuffer ?? '') + action.payload.delta }
          : m,
      )
      return { ...state, messages: msgs }
    }
    case 'FINISH_STREAMING': {
      const msgs = state.messages.map(m =>
        m.id === action.payload.id ? { ...action.payload.missatge, streaming: false } : m,
      )
      return { ...state, messages: msgs, streamingId: null }
    }
    case 'SET_FONTS_ACTIVES':
      return { ...state, fontsActives: action.payload }
    case 'SET_RECURSOS_ACTIUS':
      return { ...state, recursosActius: action.payload }
    case 'SET_SYSTEM_STATUS':
      return { ...state, systemStatus: action.payload }
    case 'SET_FEATURES':
      return { ...state, featuresActives: action.payload }
    case 'SET_LOADING':
      return { ...state, loading: action.payload }
    case 'SET_LOADING_CONV':
      return { ...state, loadingConv: action.payload }
    case 'SET_ERROR':
      return { ...state, error: action.payload }
    case 'SET_STREAMING_ID':
      return { ...state, streamingId: action.payload }
    case 'ADD_CONVERSATION':
      return {
        ...state,
        conversations: [action.payload, ...state.conversations],
      }
    case 'REMOVE_CONVERSATION':
      return {
        ...state,
        conversations: state.conversations.filter(c => c.id !== action.payload),
        conversaActiva:
          state.conversaActiva === action.payload ? null : state.conversaActiva,
        messages:
          state.conversaActiva === action.payload ? [] : state.messages,
      }
    default:
      return state
  }
}

// Context
export interface AppContextValue {
  state: AppState
  dispatch: React.Dispatch<AppAction>
}

export const AppContext = createContext<AppContextValue | null>(null)

export function useAppStore(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useAppStore must be used inside AppProvider')
  return ctx
}
