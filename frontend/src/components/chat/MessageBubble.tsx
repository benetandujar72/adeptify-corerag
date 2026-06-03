// ─── Bombolla de missatge ─────────────────────────────────────────────────────

import { useState } from 'react'
import { ThumbsUp, ThumbsDown, Copy, Bookmark, Check, Sparkles, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import type { MissatgeUI, PropostaAccio } from '../../types'
import { useChat } from '../../hooks/useChat'
import { createTasca, patchQuota } from '../../api/client'

interface Props {
  message: MissatgeUI
}

type Args = Record<string, unknown>
const txt = (v: unknown) => (v == null ? '' : String(v))

/** Registre d'accions confirmables (acció→endpoint). Afegir-ne una de nova és
 *  declarar una entrada aquí; la garantia art. 14 (confirmació humana) es manté. */
interface AccioDef {
  label: string
  boto: string
  okMsg: string
  resum: (a: Args) => React.ReactNode
  pot: (a: Args) => boolean
  executa: (a: Args) => Promise<void>
}

const ACCIONS: Record<string, AccioDef> = {
  crea_tasca: {
    label: 'Crear tasca',
    boto: 'Confirmar i crear',
    okMsg: 'Tasca creada a «Tasques».',
    resum: a => (
      <>
        {txt(a.titol) && <> · «{txt(a.titol)}»</>}
        {txt(a.prioritat) && <span className="text-muted text-xs"> · prioritat {txt(a.prioritat)}</span>}
        {txt(a.venciment) && <span className="text-muted text-xs"> · venç {txt(a.venciment)}</span>}
      </>
    ),
    pot: a => !!txt(a.titol),
    executa: async a => {
      await createTasca({
        titol: txt(a.titol), prioritat: txt(a.prioritat) || undefined,
        venciment: txt(a.venciment) || undefined,
        assignat_a: txt(a.assignat_a) || undefined,
      })
    },
  },
  marca_pagat: {
    label: 'Marcar quota com a pagada',
    boto: 'Confirmar pagament',
    okMsg: 'Quota marcada com a pagada.',
    resum: a => (
      <>
        {txt(a.alumne) && <> · {txt(a.alumne)}</>}
        {txt(a.concepte) && <span className="text-muted text-xs"> · {txt(a.concepte)}</span>}
        {a.import != null && <span className="text-muted text-xs"> · {txt(a.import)} €</span>}
      </>
    ),
    pot: a => !!txt(a.quota_id),
    executa: async a => { await patchQuota(txt(a.quota_id), { estat: 'pagat' }) },
  },
}

/** Targeta de confirmació d'una proposta d'acció de l'assistent agèntic.
 *  L'acció NO s'executa fins que la persona prem «Confirmar» (art. 14 AI Act). */
function PropostaConfirm({ proposta }: { proposta: PropostaAccio }) {
  const [estat, setEstat] = useState<'idle' | 'fent' | 'fet' | 'error'>('idle')
  const [msg, setMsg] = useState('')
  const args = (proposta.args ?? {}) as Args
  const def = ACCIONS[proposta.accio]
  const potConfirmar = def ? def.pot(args) : false

  async function confirma() {
    if (!def) {
      setMsg('Aquesta acció encara no es pot confirmar des del xat.')
      setEstat('error')
      return
    }
    setEstat('fent')
    try {
      await def.executa(args)
      setMsg(def.okMsg)
      setEstat('fet')
    } catch (e) {
      setMsg((e as Error).message)
      setEstat('error')
    }
  }

  return (
    <div className="mt-3 border border-terra/30 bg-terra/5 rounded-xl p-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-terra mb-1.5">
        <Sparkles size={13} /> Proposta d'acció · cal la teva confirmació
      </div>
      <div className="text-sm text-dark mb-2">
        <strong>{def?.label ?? proposta.accio}</strong>
        {def?.resum(args)}
      </div>
      {estat === 'fet' ? (
        <div className="flex items-center gap-1 text-sm text-green"><Check size={14} /> {msg}</div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={() => void confirma()}
            disabled={estat === 'fent' || !potConfirmar}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 disabled:opacity-40"
          >
            {estat === 'fent' ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            {def?.boto ?? 'Confirmar'}
          </button>
          {estat === 'error' && <span className="text-xs text-red-600">{msg}</span>}
        </div>
      )}
      <p className="text-[11px] text-muted italic mt-2">
        L'IA proposa; l'acció només s'executa quan la confirmes (supervisió humana, art. 14 AI Act).
      </p>
    </div>
  )
}

// Renderitza el format inline (negreta, cursiva, codi) dins de qualsevol text.
function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const regex = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*]+\*)/g
  let last = 0
  let key = 0
  let m: RegExpExecArray | null
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**') || tok.startsWith('__')) {
      nodes.push(<strong key={key++} className="font-semibold text-navy">{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('`')) {
      nodes.push(
        <code key={key++} className="bg-navy/5 text-navy rounded px-1 py-0.5 text-[0.85em] font-mono">
          {tok.slice(1, -1)}
        </code>,
      )
    } else {
      nodes.push(<em key={key++}>{tok.slice(1, -1)}</em>)
    }
    last = m.index + tok.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

// Renderitza el contingut markdown de l'assistent de manera elegant (no com a text cru):
// encapçalaments, subtítols en negreta, llistes (vinyetes i numerades), paràgrafs.
function RenderContent({ text }: { text: string }) {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let bullets: string[] = []
  let numbers: { n: string; t: string }[] = []

  function flushBullets() {
    if (bullets.length === 0) return
    const items = bullets
    bullets = []
    elements.push(
      <ul key={`ul-${elements.length}`} className="space-y-1 my-1.5 ml-1">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-sm text-dark leading-relaxed">
            <span className="shrink-0 text-terra mt-1.5 text-[0.5rem]">●</span>
            <span>{renderInline(item)}</span>
          </li>
        ))}
      </ul>,
    )
  }

  function flushNumbers() {
    if (numbers.length === 0) return
    const items = numbers
    numbers = []
    elements.push(
      <ol key={`ol-${elements.length}`} className="space-y-1.5 my-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-dark leading-relaxed">
            <span className="w-5 h-5 rounded-full bg-navy/10 text-navy text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
              {it.n}
            </span>
            <span>{renderInline(it.t)}</span>
          </li>
        ))}
      </ol>,
    )
  }

  function flush() {
    flushBullets()
    flushNumbers()
  }

  lines.forEach((rawLine, i) => {
    const line = rawLine.trimEnd()
    const numberedMatch = line.match(/^\s*(\d+)\.\s+(.+)/)
    const listMatch = line.match(/^\s*[-*•]\s+(.+)/)
    const headingMatch = line.match(/^(#{1,4})\s+(.+)/)
    // Línia tota en negreta → subtítol (p. ex. "**Criteri 1: ...**")
    const boldHeading = line.match(/^\*\*(.+?)\*\*:?\s*$/)

    if (listMatch) {
      flushNumbers()
      bullets.push(listMatch[1])
    } else if (numberedMatch) {
      flushBullets()
      numbers.push({ n: numberedMatch[1], t: numberedMatch[2] })
    } else {
      flush()
      if (headingMatch) {
        elements.push(
          <p key={i} className="text-sm font-bold text-navy mt-3 mb-1">{renderInline(headingMatch[2])}</p>,
        )
      } else if (boldHeading) {
        elements.push(
          <p key={i} className="text-sm font-semibold text-navy mt-2.5 mb-0.5">{boldHeading[1]}</p>,
        )
      } else if (line.trim() === '') {
        elements.push(<div key={i} className="h-2" />)
      } else {
        elements.push(
          <p key={i} className="text-sm text-dark leading-relaxed my-0.5">{renderInline(line)}</p>,
        )
      }
    }
  })
  flush()
  return <div className="space-y-0.5">{elements}</div>
}

export function MessageBubble({ message }: Props) {
  const { sendFeedback } = useChat()
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState<'util' | 'millorar' | null>(null)

  const isUser = message.rol === 'user'
  const text = message.streaming ? (message.streamBuffer ?? '') : message.contingut

  function handleCopy() {
    void navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function handleFeedback(valor: 'util' | 'millorar') {
    setFeedback(valor)
    await sendFeedback(message.id, valor)
  }

  const timeStr = new Date(message.creat_el).toLocaleTimeString('ca', {
    hour: '2-digit',
    minute: '2-digit',
  })

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1">
        <div className="max-w-[75%]">
          <div className="bg-userbubble rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
            <p className="text-sm text-dark whitespace-pre-wrap">{text}</p>
          </div>
          <div className="text-xs text-muted text-right mt-1">
            {timeStr} · {message.rol === 'user' ? 'Tu' : ''}
          </div>
        </div>
      </div>
    )
  }

  // Missatge de l'assistent
  return (
    <div className="px-4 py-2">
      {/* Capçalera IA */}
      <div className="flex items-center gap-2 mb-2">
        <div className="w-8 h-8 rounded-full bg-navy flex items-center justify-center shrink-0">
          <span className="text-white text-xs font-bold">IA</span>
        </div>
        <span className="text-xs font-bold text-navy">Nou Patufet IA</span>
        {message.agent_id && (
          <span className="text-xs text-muted">· {message.agent_id.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
        )}
      </div>

      {/* Bombolla */}
      <div className="ml-10">
        <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
          {message.streaming && text === '' ? (
            <div className="flex gap-1 py-1">
              <span className="w-2 h-2 rounded-full bg-muted/50 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 rounded-full bg-muted/50 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 rounded-full bg-muted/50 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          ) : (
            <RenderContent text={text} />
          )}

          {/* Streaming cursor */}
          {message.streaming && text !== '' && (
            <span className="inline-block w-0.5 h-4 bg-navy ml-0.5 animate-pulse" />
          )}

          {/* Chips de fonts */}
          {!message.streaming && message.fonts && message.fonts.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3 pt-2 border-t border-border">
              {message.fonts.map(font => (
                <span
                  key={font.doc_id}
                  className="inline-flex items-center gap-1 bg-userbubble text-navy text-xs px-2.5 py-1 rounded-full"
                >
                  {font.tipus === 'pdf' ? '📄' : font.tipus === 'xlsx' ? '📊' : font.tipus === 'docx' ? '📝' : '📄'}
                  {' '}{font.filename}{font.pagina ? ` p.${font.pagina}` : ''}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Proposta d'acció de l'assistent agèntic (confirmació humana) */}
        {!message.streaming && message.proposta?.proposta && (
          <PropostaConfirm proposta={message.proposta} />
        )}

        {/* Accions (per a missatges finalitzats) */}
        {!message.streaming && (
          <div className="flex items-center gap-1.5 mt-2">
            <button
              onClick={() => handleFeedback('util')}
              className={clsx(
                'flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs border transition-colors',
                feedback === 'util'
                  ? 'bg-green/10 border-green text-green'
                  : 'bg-white border-border text-dark hover:border-green hover:text-green',
              )}
            >
              <ThumbsUp size={12} />
              Útil
            </button>

            <button
              onClick={() => handleFeedback('millorar')}
              className={clsx(
                'flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs border transition-colors',
                feedback === 'millorar'
                  ? 'bg-red-50 border-red-400 text-red-500'
                  : 'bg-white border-border text-dark hover:border-red-400 hover:text-red-500',
              )}
            >
              <ThumbsDown size={12} />
              Millorar
            </button>

            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs border bg-white border-border text-dark hover:border-navy transition-colors"
            >
              {copied ? <Check size={12} className="text-green" /> : <Copy size={12} />}
              {copied ? 'Copiat!' : 'Copiar'}
            </button>

            <button className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs border bg-white border-border text-dark hover:border-navy transition-colors">
              <Bookmark size={12} />
              Desar
            </button>
          </div>
        )}

        {/* Hora */}
        {!message.streaming && (
          <div className="text-xs text-muted mt-1">{timeStr}</div>
        )}
      </div>
    </div>
  )
}
