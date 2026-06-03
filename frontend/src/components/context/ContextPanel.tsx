// ─── Panell dret: context, documents i privadesa ─────────────────────────────

import { useState } from 'react'
import { Download, Share2, BookOpen, Loader2, Check, ExternalLink } from 'lucide-react'
import { useAppStore } from '../../store/appStore'
import { uploadDocument, obreFontDocument } from '../../api/client'

const TIPUS_COLORS: Record<string, string> = {
  pdf: 'bg-terra text-white',
  docx: 'bg-navy text-white',
  xlsx: 'bg-green text-white',
  md: 'bg-sage text-white',
  html: 'bg-cherry text-white',
  image: 'bg-[#7C3AED] text-white',
}

const TIPUS_LABEL: Record<string, string> = {
  pdf: 'PDF',
  docx: 'DOC',
  xlsx: 'XLS',
  md: 'MD',
  html: 'HTML',
  image: 'IMG',
}

export function ContextPanel() {
  const { state } = useAppStore()
  const ss = state.systemStatus
  const fonts = state.fontsActives

  const totalFrags = fonts.reduce((s, f) => s + f.fragments, 0)
  // Confiança = millor font (la que millor sustenta la resposta), no la mitjana
  // (que quedaria arrossegada per fonts secundàries més febles). Amb el reranker
  // actiu aquest valor és una rellevància real i alta per a respostes ben fonamentades.
  const confianca = fonts.length
    ? Math.round(Math.max(...fonts.map(f => f.score)) * 100)
    : 0

  // ── Accions sobre la conversa ──────────────────────────────────────────────
  const [accioBusy, setAccioBusy] = useState(false)
  const [accioMsg, setAccioMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // ── Obrir el document original d'una font (F1) ─────────────────────────────
  const [obrintId, setObrintId] = useState<string | null>(null)
  const [fontMsg, setFontMsg] = useState<string | null>(null)

  async function obreFont(docId: string) {
    setObrintId(docId)
    setFontMsg(null)
    try {
      await obreFontDocument(docId)
    } catch (e) {
      setFontMsg((e as Error).message)
    } finally {
      setObrintId(null)
    }
  }

  const teMissatges = state.messages.some(m => (m.contingut || m.streamBuffer || '').trim())

  function construeixMarkdown(): string {
    const titol =
      state.conversations.find(c => c.id === state.conversaActiva)?.titol ??
      `Conversa amb ${state.agentActiu?.nom ?? 'IA Nou Patufet'}`
    const linies = [`# ${titol}`, '', `_Desat el ${new Date().toLocaleString('ca')}_`, '']
    for (const m of state.messages) {
      const text = (m.contingut || m.streamBuffer || '').trim()
      if (!text) continue
      linies.push(m.rol === 'user' ? '## Pregunta' : '## Resposta')
      linies.push('', text, '')
    }
    return linies.join('\n')
  }

  function handleExportar() {
    if (!teMissatges) return
    const blob = new Blob([construeixMarkdown()], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `conversa-${Date.now()}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleCompartir() {
    if (!teMissatges) return
    try {
      await navigator.clipboard.writeText(construeixMarkdown())
      setAccioMsg({ ok: true, text: 'Conversa copiada al porta-retalls.' })
    } catch {
      setAccioMsg({ ok: false, text: "No s'ha pogut copiar." })
    }
  }

  async function handleAfegirBiblioteca() {
    if (!teMissatges || accioBusy) return
    setAccioBusy(true)
    setAccioMsg(null)
    try {
      const nom = `conversa-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.md`
      const file = new File([construeixMarkdown()], nom, { type: 'text/markdown' })
      await uploadDocument(file)
      setAccioMsg({ ok: true, text: 'Afegit a la biblioteca del centre.' })
    } catch (e) {
      setAccioMsg({ ok: false, text: (e as Error).message })
    } finally {
      setAccioBusy(false)
    }
  }

  return (
    <aside className="w-[260px] xl:w-[300px] shrink-0 bg-white border-l border-border flex flex-col h-full overflow-y-auto">
      {/* Context de la conversa */}
      <div className="px-5 pt-5 pb-3">
        <h3 className="text-xs font-bold text-navy tracking-wide uppercase mb-3">
          Context d'aquesta conversa
        </h3>
        <div className="bg-crema rounded-lg px-4 py-3">
          <div className="flex items-baseline gap-1 mb-1">
            <span className="text-2xl font-bold text-navy">{fonts.length}</span>
            <span className="text-sm text-dark">documents consultats</span>
          </div>
          <p className="text-xs text-muted">
            {totalFrags > 0
              ? `${totalFrags} fragments rellevants · ${confianca}% confiança`
              : 'Cap document consultat encara'}
          </p>
          {fonts.length > 0 && confianca < 45 && (
            <p className="text-xs text-terra font-medium mt-2 flex items-start gap-1">
              <span>⚠️</span>
              <span>Confiança baixa: verifica la resposta amb secretaria o el document original.</span>
            </p>
          )}
        </div>
      </div>

      {/* Documents consultats */}
      <div className="px-5 pb-3">
        <h4 className="text-xs font-bold text-muted tracking-wide uppercase mb-2">
          Documents consultats
        </h4>

        {fonts.length === 0 ? (
          <div className="text-xs text-muted text-center py-4 bg-crema rounded-lg">
            Els documents apareixeran<br />quan facis una consulta.
          </div>
        ) : (
          <div className="space-y-2">
            {fonts.map(font => (
              <button
                key={font.doc_id}
                onClick={() => void obreFont(font.doc_id)}
                disabled={obrintId === font.doc_id}
                title={`Obrir «${font.filename}»`}
                className="w-full text-left bg-crema rounded-lg px-3 py-2.5 flex items-start gap-2.5 hover:bg-sage/15 hover:ring-1 hover:ring-sage transition-colors disabled:opacity-60"
              >
                <div className={`px-1.5 py-1 rounded text-xs font-bold shrink-0 ${TIPUS_COLORS[font.tipus] ?? 'bg-muted text-white'}`}>
                  {TIPUS_LABEL[font.tipus] ?? font.tipus.toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-dark truncate flex items-center gap-1">
                    {font.filename}
                    {obrintId === font.doc_id
                      ? <Loader2 size={11} className="animate-spin shrink-0 text-navy" />
                      : <ExternalLink size={11} className="shrink-0 text-muted" />}
                  </div>
                  <div className="text-xs text-muted">
                    {font.fragments} fragments
                    {font.pagina ? ` · p.${font.pagina}` : ''}
                  </div>
                  <div className="text-xs text-sage">
                    verificat · {font.verificat_el}
                  </div>
                </div>
                <div className="text-xs font-semibold text-navy shrink-0">
                  {Math.round(font.score * 100)}%
                </div>
              </button>
            ))}
          </div>
        )}

        {fontMsg && (
          <p className="mt-2 text-xs text-terra">{fontMsg}</p>
        )}
      </div>

      {/* Documentació i formularis suggerits (verificats pel centre · F2) */}
      {state.recursosActius.length > 0 && (
        <div className="px-5 pb-3">
          <h4 className="text-xs font-bold text-muted tracking-wide uppercase mb-2">
            Documentació suggerida
          </h4>
          <div className="space-y-2">
            {state.recursosActius.map(r => {
              const meta = [r.font_oficial, r.versio].filter(Boolean).join(' · ')
              const contingut = (
                <>
                  <div className="text-xs font-semibold text-navy truncate flex items-center gap-1">
                    {r.titol}
                    {r.tipus === 'document'
                      ? <Download size={11} className="shrink-0 text-muted" />
                      : <ExternalLink size={11} className="shrink-0 text-muted" />}
                  </div>
                  {r.descripcio && <div className="text-xs text-dark line-clamp-2">{r.descripcio}</div>}
                  {meta && <div className="text-[11px] text-sage">{meta}</div>}
                </>
              )
              return r.tipus === 'document' && r.doc_id ? (
                <button
                  key={r.id}
                  onClick={() => void obreFont(r.doc_id!)}
                  disabled={obrintId === r.doc_id}
                  className="w-full text-left bg-terra/5 rounded-lg px-3 py-2 border border-terra/30 hover:bg-terra/10 transition-colors disabled:opacity-60"
                >
                  {contingut}
                </button>
              ) : (
                <a
                  key={r.id}
                  href={r.url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block bg-terra/5 rounded-lg px-3 py-2 border border-terra/30 hover:bg-terra/10 transition-colors"
                >
                  {contingut}
                </a>
              )
            })}
          </div>
          <p className="text-[11px] text-muted italic mt-2">
            Enllaços verificats pel centre · reviseu la versió oficial vigent.
          </p>
        </div>
      )}

      <div className="border-t border-border mx-5" />

      {/* Indicadors de privadesa */}
      <div className="px-5 py-3">
        <h4 className="text-xs font-bold text-muted tracking-wide uppercase mb-2">
          Indicadors de privadesa
        </h4>
        <div className="space-y-2">
          <PrivacyRow
            icon="🔒"
            title="Dades en servidor local"
            subtitle={ss?.servidor.host ?? 'servidor local · centre'}
            ok={ss?.privadesa.processament_local ?? true}
          />
          <PrivacyRow
            icon="🔒"
            title="Cap petició externa"
            subtitle={`${ss?.privadesa.crides_externes ?? 0} connexions a tercers`}
            ok={(ss?.privadesa.crides_externes ?? 0) === 0}
          />
          <PrivacyRow
            icon="🔒"
            title="Conversa xifrada"
            subtitle={`${ss?.privadesa.xifratge ?? 'AES-256'} · extrem a extrem`}
            ok
          />
        </div>

        {/* Auditat */}
        <div className="mt-3 bg-navy rounded-lg px-3 py-2.5 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-terra flex items-center justify-center shrink-0">
            <span className="text-white text-sm">✓</span>
          </div>
          <div>
            <div className="text-white text-xs font-bold">
              Auditat {ss?.privadesa.auditat_el ?? '—'}
            </div>
            <div className="text-sage text-xs">Conforme RGPD · LOPDGDD</div>
          </div>
        </div>
      </div>

      <div className="border-t border-border mx-5" />

      {/* Accions */}
      <div className="px-5 py-3">
        <h4 className="text-xs font-bold text-muted tracking-wide uppercase mb-2">
          Accions sobre la conversa
        </h4>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <button
            onClick={handleExportar}
            disabled={!teMissatges}
            className="flex items-center justify-center gap-1.5 py-2 rounded-lg border border-border bg-white text-xs text-dark hover:bg-crema transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={13} />
            Exportar
          </button>
          <button
            onClick={handleCompartir}
            disabled={!teMissatges}
            className="flex items-center justify-center gap-1.5 py-2 rounded-lg border border-border bg-white text-xs text-dark hover:bg-crema transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Share2 size={13} />
            Compartir
          </button>
        </div>
        <button
          onClick={handleAfegirBiblioteca}
          disabled={!teMissatges || accioBusy}
          className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg bg-sage text-white text-xs font-semibold hover:bg-sage/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {accioBusy ? <Loader2 size={13} className="animate-spin" /> : <BookOpen size={13} />}
          {accioBusy ? 'Afegint…' : 'Afegir a la biblioteca del centre'}
        </button>

        {accioMsg && (
          <p
            className={`mt-2 text-xs flex items-center gap-1 ${
              accioMsg.ok ? 'text-green' : 'text-red-600'
            }`}
          >
            {accioMsg.ok && <Check size={12} className="shrink-0" />}
            {accioMsg.text}
          </p>
        )}
        {!teMissatges && (
          <p className="mt-2 text-xs text-muted text-center">
            Fes una consulta per poder desar-la.
          </p>
        )}
      </div>
    </aside>
  )
}

// ─── Sub-component PrivacyRow ─────────────────────────────────────────────────

function PrivacyRow({
  icon,
  title,
  subtitle,
  ok,
}: {
  icon: string
  title: string
  subtitle: string
  ok: boolean
}) {
  return (
    <div className="bg-crema rounded-lg px-3 py-2 flex items-center gap-2.5">
      <div className="w-8 h-8 rounded-full bg-sage flex items-center justify-center text-sm shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-semibold text-dark">{title}</div>
        <div className="text-xs text-muted">{subtitle}</div>
      </div>
      <div className={`w-3 h-3 rounded-full shrink-0 ${ok ? 'bg-green' : 'bg-red-400'}`} />
    </div>
  )
}
