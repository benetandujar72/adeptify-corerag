// ─── Hook de xat amb SSE ─────────────────────────────────────────────────────
// Gestiona enviament, streaming i actualització de l'store.

import { useCallback } from 'react'
import { streamChat, postFeedback, fetchConversations } from '../api/client'
import { useAppStore } from '../store/appStore'
import type { Font, Missatge, MissatgeUI } from '../types'

function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function useChat() {
  const { state, dispatch } = useAppStore()

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || !state.agentActiu) return

      const userMsgId = generateId()
      const userMsg: MissatgeUI = {
        id: userMsgId,
        rol: 'user',
        contingut: text.trim(),
        creat_el: new Date().toISOString(),
      }
      dispatch({ type: 'APPEND_MESSAGE', payload: userMsg })

      const asstMsgId = generateId()
      const asstMsg: MissatgeUI = {
        id: asstMsgId,
        rol: 'assistant',
        contingut: '',
        streamBuffer: '',
        streaming: true,
        agent_id: state.agentActiu.id,
        creat_el: new Date().toISOString(),
      }
      dispatch({ type: 'APPEND_MESSAGE', payload: asstMsg })
      dispatch({ type: 'SET_STREAMING_ID', payload: asstMsgId })
      dispatch({ type: 'SET_ERROR', payload: null })

      let sourcesReceived: Font[] = []

      await streamChat(
        state.agentActiu.id,
        text.trim(),
        state.conversaActiva,
        {
          onToken: (delta: string) => {
            dispatch({ type: 'UPDATE_STREAMING', payload: { id: asstMsgId, delta } })
          },
          onSources: (fonts: Font[]) => {
            sourcesReceived = fonts
            dispatch({ type: 'SET_FONTS_ACTIVES', payload: fonts })
          },
          onRecursos: recursos => {
            dispatch({ type: 'SET_RECURSOS_ACTIUS', payload: recursos })
          },
          onDone: (message: Missatge, conversationId?: string) => {
            const finalMsg: MissatgeUI = {
              ...message,
              id: asstMsgId,
              streaming: false,
              fonts: message.fonts ?? sourcesReceived,
            }
            dispatch({ type: 'FINISH_STREAMING', payload: { id: asstMsgId, missatge: finalMsg } })
            if (message.fonts?.length) {
              dispatch({ type: 'SET_FONTS_ACTIVES', payload: message.fonts })
            }
            // Fixa la conversa (nova o existent) i refresca l'historial del sidebar,
            // perquè les converses noves apareguin i el multi-torn continuï la mateixa.
            if (conversationId) {
              if (conversationId !== state.conversaActiva) {
                dispatch({ type: 'SET_CONVERSA_ACTIVA', payload: conversationId })
              }
              void fetchConversations()
                .then(cs => dispatch({ type: 'SET_CONVERSATIONS', payload: cs }))
                .catch(() => {
                  /* silenciós */
                })
            }
          },
          onError: (err: string) => {
            dispatch({
              type: 'FINISH_STREAMING',
              payload: {
                id: asstMsgId,
                missatge: {
                  id: asstMsgId,
                  rol: 'assistant',
                  contingut: `⚠️ ${err}`,
                  streaming: false,
                  creat_el: new Date().toISOString(),
                },
              },
            })
            dispatch({ type: 'SET_ERROR', payload: err })
          },
        },
      )
    },
    [state.agentActiu, state.conversaActiva, dispatch],
  )

  const sendFeedback = useCallback(
    async (messageId: string, valor: 'util' | 'millorar') => {
      try {
        await postFeedback(messageId, valor)
      } catch {
        // feedback errors silenciosos
      }
    },
    [],
  )

  return { sendMessage, sendFeedback }
}
