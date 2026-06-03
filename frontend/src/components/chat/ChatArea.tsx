// ─── Àrea de xat central ─────────────────────────────────────────────────────

import { useRef, useEffect, useState } from 'react'
import { Send, Paperclip, Mic, Share2, Star, MoreHorizontal, Loader2 } from 'lucide-react'
import { useAppStore } from '../../store/appStore'
import { useChat } from '../../hooks/useChat'
import { transcribeAudio } from '../../api/client'
import { MessageBubble } from './MessageBubble'

// Preguntes suggerides per agent (starters contextuals segons l'agent actiu).
const SUGGESTIONS: Record<string, string[]> = {
  tutor_mates: [
    "Fes-me un esquema d'una unitat ABP de fraccions per a 5è",
    'Explica les fraccions equivalents amb un exemple',
    'Proposa exercicis de reforç de multiplicació',
    'Crea una rúbrica per a un problema de geometria',
  ],
  secretaria: [
    'Quins dies són festius aquest curs?',
    'Què diu la NOFC sobre els permisos i les absències?',
    'Quins terminis hi ha per a la matrícula?',
    'Resumeix els drets i deures de l’alumnat',
  ],
  families: [
    'A quina hora és el menjador i quant costa?',
    'Quins dies hi ha la sortida de tercer?',
    'Com puc demanar una tutoria amb el/la mestre/a?',
    'Quin és el calendari de vacances?',
  ],
  documental: [
    'Redacta un esborrany de circular per a una sortida',
    'Resumeix l’acta del darrer claustre',
    'Genera una memòria d’activitat',
    'Cerca documents sobre el pla de convivència',
  ],
  avaluacions: [
    'Crea una rúbrica per avaluar una exposició oral a 5è',
    'Quins criteris d’avaluació LOMLOE encaixen amb un projecte ABP?',
    'Mapeja aquesta activitat amb les competències clau',
    'Dissenya nivells d’assoliment per a la competència matemàtica',
  ],
}

const SUGGESTIONS_DEFECTE = [
  'Com puc estructurar una unitat didàctica ABP?',
  'Quins documents necessito per a una sortida escolar?',
  'Resum dels acords del darrer claustre',
  'Explica la normativa de permisos del NOFC',
]

// Accions predefinides per agent: plantilles que es PRECARGUEN a l'input (amb
// camps [entre claudàtors] perquè l'usuari els completi) en lloc d'enviar-se.
const ACCIONS_RAPIDES: Record<string, { label: string; prompt: string }[]> = {
  tutor_mates: [
    { label: '📝 Rúbrica', prompt: "Crea una rúbrica d'avaluació per a una activitat de [tema] de [curs], amb criteris i nivells d'assoliment." },
    { label: '🎯 Activitat ABP', prompt: 'Dissenya una activitat ABP de [n] sessions sobre [tema] per a [curs].' },
    { label: '🔁 Reforç', prompt: 'Proposa 5 exercicis de reforç de [tema] per a [curs], de menys a més dificultat.' },
  ],
  secretaria: [
    { label: '📋 Consulta NOFC', prompt: 'Què diu la NOFC sobre [tema]?' },
    { label: '🗓️ Calendari', prompt: 'Quins dies festius o no lectius hi ha a [mes o trimestre]?' },
    { label: '📑 Tràmit', prompt: 'Quins passos i terminis té el tràmit de [tràmit]?' },
  ],
  families: [
    { label: '🍽️ Menjador', prompt: 'Informació del menjador: horaris, preus i funcionament.' },
    { label: '🎒 Sortida', prompt: 'Detalls de la sortida de [curs]: dates, què cal portar i autoritzacions.' },
    { label: '📅 Tutoria', prompt: 'Com puc demanar una tutoria amb el/la mestre/a de [curs]?' },
  ],
  documental: [
    { label: '✉️ Circular', prompt: 'Redacta una circular per a les famílies sobre [tema], amb to proper i clar.' },
    { label: '📄 Acta', prompt: "Redacta un esborrany d'acta de la reunió de [òrgan] del [data] amb aquests punts: [punts]." },
    { label: '🔎 Resumeix', prompt: 'Resumeix el document [nom] en 5 punts clau.' },
  ],
  avaluacions: [
    { label: '📊 Rúbrica', prompt: 'Crea una rúbrica per avaluar [activitat] de [curs], amb criteris i 4 nivells d’assoliment.' },
    { label: '🎯 Competències', prompt: 'Mapeja l’activitat [activitat] amb les competències clau i específiques LOMLOE de [àrea].' },
    { label: '🧾 Criteris', prompt: 'Proposa criteris d’avaluació per a [tema] de [curs] segons LOMLOE.' },
  ],
}

// Onboarding guiat per rol: primeres preguntes per a nous docents/famílies/PAS.
const ONBOARDING: Record<string, { titol: string; passos: string[] }> = {
  docent: {
    titol: 'Nou al centre? Primers passos com a docent',
    passos: [
      'Quins canals de comunicació interna fa servir el centre?',
      'Quins són els principis pedagògics del PEC que he de conèixer?',
      'Resum del NOFC: el més important per al dia a dia a l\'aula',
    ],
  },
  familia: {
    titol: 'Benvinguda família! Primeres passes',
    passos: [
      'Com funcionen el menjador i les activitats extraescolars?',
      'Quins canals de comunicació hi ha amb l\'escola?',
      'Quin és el calendari escolar i els dies festius?',
    ],
  },
  pas: {
    titol: 'Benvingut/da al PAS · per on començar',
    passos: [
      'Quins tràmits i terminis de secretaria són els més habituals?',
      'Resum del NOFC rellevant per a administració i serveis',
      'On són les plantilles de documents del centre?',
    ],
  },
}

export function ChatArea() {
  const { state } = useAppStore()
  const { sendMessage } = useChat()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [recording, setRecording] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  // Auto-scroll al final
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages])

  // Auto-resize del textarea
  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
    const ta = textareaRef.current
    if (ta) {
      ta.style.height = 'auto'
      ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`
    }
  }

  function handleSend() {
    if (!input.trim() || state.streamingId) return
    void sendMessage(input)
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  // Precarrega una plantilla a l'input perquè l'usuari la completi abans d'enviar.
  function prefill(prompt: string) {
    setInput(prompt)
    const ta = textareaRef.current
    if (ta) {
      ta.focus()
      ta.style.height = 'auto'
      ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`
    }
  }

  // Dictat per veu: grava amb el micròfon i transcriu en local (Whisper).
  async function toggleRec() {
    if (recording) {
      mediaRecorderRef.current?.stop()
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream)
      chunksRef.current = []
      mr.ondataavailable = e => {
        if (e.data.size) chunksRef.current.push(e.data)
      }
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        setRecording(false)
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        if (blob.size === 0) return
        setTranscribing(true)
        try {
          const text = await transcribeAudio(blob)
          if (text) {
            setInput(prev => (prev ? prev.trim() + ' ' : '') + text)
            textareaRef.current?.focus()
          }
        } catch {
          /* error de transcripció ignorat silenciosament */
        } finally {
          setTranscribing(false)
        }
      }
      mr.start()
      mediaRecorderRef.current = mr
      setRecording(true)
    } catch {
      /* permís de micròfon denegat */
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Capçalera de la conversa activa
  const convActiva = state.conversations.find(c => c.id === state.conversaActiva)
  const totalDocs = state.fontsActives.length

  return (
    <div className="flex flex-col flex-1 min-w-0 bg-crema h-full">
      {/* Capçalera de conversa */}
      <div className="bg-white border-b border-border px-5 py-3 flex items-center gap-3 shrink-0">
        <div className="flex-1 min-w-0">
          <h2 className="text-[15px] font-bold text-navy truncate">
            {convActiva?.titol ?? (state.conversaActiva ? 'Carregant…' : 'Nova conversa')}
          </h2>
          <p className="text-xs text-muted">
            {state.agentActiu ? `Agent: ${state.agentActiu.nom}` : 'Selecciona un agent'}
            {totalDocs > 0 && ` · ${totalDocs} documents consultats`}
            {convActiva && ` · iniciat ${new Date(convActiva.actualitzat_el).toLocaleDateString('ca')}`}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button className="w-8 h-8 rounded-md bg-crema flex items-center justify-center text-muted hover:text-dark transition-colors">
            <Share2 size={14} />
          </button>
          <button className="w-8 h-8 rounded-md bg-crema flex items-center justify-center text-muted hover:text-dark transition-colors">
            <Star size={14} />
          </button>
          <button className="w-8 h-8 rounded-md bg-crema flex items-center justify-center text-muted hover:text-dark transition-colors">
            <MoreHorizontal size={14} />
          </button>
        </div>
      </div>

      {/* Zona de missatges */}
      <div className="flex-1 overflow-y-auto py-4 space-y-1">
        {/* Data separadora */}
        {state.messages.length > 0 && (
          <div className="flex justify-center mb-2">
            <span className="bg-fons text-muted text-xs px-3 py-1 rounded-full">
              {new Date().toLocaleDateString('ca', { weekday: 'long', day: 'numeric', month: 'long' })}
            </span>
          </div>
        )}

        {/* Estat buit */}
        {state.messages.length === 0 && !state.loadingConv && (
          <div className="flex flex-col items-center justify-center h-full py-20 px-8 text-center">
            <div className="w-16 h-16 rounded-full bg-navy flex items-center justify-center mb-4">
              <span className="text-white text-2xl font-bold">IA</span>
            </div>
            <h3 className="text-lg font-bold text-navy mb-2">Hola! Sóc el teu assistent de centre.</h3>
            <p className="text-sm text-muted mb-6 max-w-md">
              {state.agentActiu
                ? `Estic preparat com a ${state.agentActiu.nom}. ${state.agentActiu.descripcio}`
                : 'Selecciona un agent al menú lateral per començar.'}
            </p>
            {state.agentActiu && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-md">
                {(SUGGESTIONS[state.agentActiu.id] ?? SUGGESTIONS_DEFECTE).map(suggestion => (
                  <button
                    key={suggestion}
                    onClick={() => void sendMessage(suggestion)}
                    className="text-left px-3 py-2 rounded-lg border border-border bg-white text-sm text-dark hover:border-navy hover:bg-crema transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}

            {state.session && ONBOARDING[state.session.rol] && (
              <div className="mt-5 w-full max-w-md text-left">
                <p className="text-xs font-bold text-muted uppercase tracking-wide mb-2">
                  {ONBOARDING[state.session.rol].titol}
                </p>
                <div className="flex flex-col gap-1.5">
                  {ONBOARDING[state.session.rol].passos.map(p => (
                    <button
                      key={p}
                      onClick={() => void sendMessage(p)}
                      className="text-left px-3 py-2 rounded-lg bg-sage/10 border border-sage/30 text-sm text-navy hover:bg-sage/20 transition-colors"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Carregant conversa */}
        {state.loadingConv && (
          <div className="flex justify-center py-12">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 border-2 border-terra border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-muted">Carregant conversa…</span>
            </div>
          </div>
        )}

        {/* Missatges */}
        {state.messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Error */}
        {state.error && (
          <div className="mx-4 px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
            ⚠️ {state.error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Barra d'entrada */}
      <div className="px-4 pb-3 pt-2 shrink-0">
        {state.agentActiu && !state.streamingId && ACCIONS_RAPIDES[state.agentActiu.id] && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            <span className="text-xs text-muted self-center mr-1">Accions ràpides:</span>
            {ACCIONS_RAPIDES[state.agentActiu.id].map(a => (
              <button
                key={a.label}
                onClick={() => prefill(a.prompt)}
                title={a.prompt}
                className="px-2.5 py-1 rounded-full border border-border bg-white text-xs text-dark hover:border-terra hover:bg-crema transition-colors"
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
        <div className="bg-white rounded-2xl border border-border shadow-sm flex items-end gap-2 px-4 py-2">
          <button className="text-muted hover:text-dark transition-colors pb-1" title="Adjuntar fitxer">
            <Paperclip size={18} />
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              state.agentActiu
                ? 'Pregunta o demana ajuda...'
                : 'Selecciona primer un agent al menú lateral…'
            }
            disabled={!state.agentActiu || !!state.streamingId}
            rows={1}
            className="flex-1 bg-transparent text-sm text-dark placeholder:text-muted outline-none resize-none py-1.5 min-h-[28px] max-h-[120px] disabled:opacity-50"
          />
          <button
            onClick={() => void toggleRec()}
            disabled={transcribing || !!state.streamingId}
            className={`pb-1 transition-colors disabled:opacity-40 ${
              recording ? 'text-red-500 animate-pulse' : 'text-muted hover:text-dark'
            }`}
            title={recording ? 'Atura i transcriu' : 'Dictar per veu (local)'}
          >
            {transcribing ? <Loader2 size={18} className="animate-spin" /> : <Mic size={18} />}
          </button>
          <button
            onClick={handleSend}
            disabled={!input.trim() || !state.agentActiu || !!state.streamingId}
            className="w-9 h-9 rounded-full bg-terra flex items-center justify-center text-white hover:bg-terra/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
          >
            {state.streamingId ? (
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <Send size={15} />
            )}
          </button>
        </div>
        <p className="text-center text-xs text-muted mt-1.5">
          La IA pot consultar documents del centre. Tot el processament és local.
        </p>
      </div>
    </div>
  )
}
