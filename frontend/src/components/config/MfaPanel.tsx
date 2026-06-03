// ─── Panell de verificació en dos passos (MFA/TOTP) ─────────────────────────
// L'usuari configura el seu propi segon factor: genera secret → l'afegeix a l'app
// d'autenticació → confirma amb un codi. Recomanat especialment per a direcció/admin.

import { useEffect, useState } from 'react'
import { ShieldCheck, Loader2, Copy, Check } from 'lucide-react'
import { fetchMfaEstat, setupMfa, activarMfa, desactivarMfa } from '../../api/client'
import type { MfaSetup } from '../../types'

export function MfaPanel() {
  const [actiu, setActiu] = useState<boolean | null>(null)
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [codi, setCodi] = useState('')
  const [estat, setEstat] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [copiat, setCopiat] = useState(false)

  useEffect(() => {
    fetchMfaEstat().then(setActiu).catch(() => setActiu(false))
  }, [])

  async function iniciar() {
    setBusy(true); setEstat(null)
    try { setSetup(await setupMfa()) }
    catch (e) { setEstat({ ok: false, text: (e as Error).message }) }
    finally { setBusy(false) }
  }

  async function activar() {
    setBusy(true)
    try {
      const a = await activarMfa(codi.trim())
      setActiu(a); setSetup(null); setCodi('')
      setEstat({ ok: true, text: 'Verificació en dos passos activada.' })
    } catch (e) { setEstat({ ok: false, text: (e as Error).message }) }
    finally { setBusy(false) }
  }

  async function desactivar() {
    if (!window.confirm('Desactivar la verificació en dos passos?')) return
    setBusy(true)
    try {
      const a = await desactivarMfa()
      setActiu(a)
      setEstat({ ok: true, text: 'Verificació en dos passos desactivada.' })
    } catch (e) { setEstat({ ok: false, text: (e as Error).message }) }
    finally { setBusy(false) }
  }

  return (
    <div className="bg-white rounded-xl border border-border p-5 mt-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sage"><ShieldCheck size={16} /></span>
        <h2 className="font-bold text-navy text-sm uppercase tracking-wide">Verificació en dos passos (MFA)</h2>
        {actiu !== null && (
          <span className={`ml-auto text-xs px-2 py-0.5 rounded-full ${actiu ? 'bg-green/15 text-green' : 'bg-muted/15 text-muted'}`}>
            {actiu ? 'Activada' : 'Desactivada'}
          </span>
        )}
      </div>

      {estat && (
        <div className={`mb-3 px-3 py-2 rounded-lg text-sm border ${estat.ok ? 'bg-green/10 text-green border-green/30' : 'bg-red-50 text-red-600 border-red-200'}`}>
          {estat.text}
        </div>
      )}

      {actiu === null ? (
        <div className="text-muted text-sm"><Loader2 className="animate-spin inline" size={16} /> Carregant…</div>
      ) : actiu ? (
        <>
          <p className="text-sm text-muted mb-3">El teu compte demana un codi de l'app d'autenticació en iniciar sessió.</p>
          <button onClick={() => void desactivar()} disabled={busy} className="px-3 py-2 rounded-lg border border-red-300 text-red-600 text-sm hover:bg-red-50 disabled:opacity-40">
            Desactivar
          </button>
        </>
      ) : setup ? (
        <>
          <p className="text-sm text-dark mb-2">
            1. Afegeix aquesta clau a la teva app d'autenticació (Google Authenticator, Authy, FreeOTP…),
            escanejant l'enllaç o introduint la clau manualment:
          </p>
          <div className="flex items-center gap-2 mb-1">
            <code className="flex-1 bg-navy/5 text-navy rounded px-2 py-1.5 text-xs font-mono break-all">{setup.secret}</code>
            <button
              onClick={() => { void navigator.clipboard.writeText(setup.secret); setCopiat(true); setTimeout(() => setCopiat(false), 1500) }}
              title="Copiar la clau" className="text-muted hover:text-navy shrink-0"
            >
              {copiat ? <Check size={15} className="text-green" /> : <Copy size={15} />}
            </button>
          </div>
          <a href={setup.otpauth_uri} className="text-xs text-navy underline break-all">Obrir a l'app d'autenticació (otpauth://…)</a>

          <p className="text-sm text-dark mt-3 mb-1.5">2. Introdueix el codi de 6 xifres que mostra l'app:</p>
          <div className="flex items-center gap-2">
            <input
              value={codi}
              onChange={e => setCodi(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="123456" inputMode="numeric"
              className="w-32 px-3 py-2 border border-border rounded-lg text-sm font-mono text-center tracking-widest focus:outline-none focus:border-navy"
            />
            <button onClick={() => void activar()} disabled={busy || codi.length < 6} className="px-4 py-2 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 disabled:opacity-40">
              Activar
            </button>
            <button onClick={() => { setSetup(null); setCodi('') }} className="text-xs text-muted hover:text-navy">Cancel·lar</button>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-muted mb-3">
            Afegeix una capa de seguretat: un codi temporal de la teva app d'autenticació en iniciar sessió.
            <strong> Recomanat per a direcció i administració</strong>, especialment amb accés remot.
          </p>
          <button onClick={() => void iniciar()} disabled={busy} className="px-4 py-2 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 disabled:opacity-40">
            {busy ? <Loader2 className="animate-spin inline" size={15} /> : 'Configurar MFA'}
          </button>
        </>
      )}
    </div>
  )
}
