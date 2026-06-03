// ─── Pàgina «Seguretat de xarxa» (direcció / superadmin) ──────────────────
// Configura quines IPs/CIDRs poden accedir al centre. Cada institució gestiona
// la SEVA política (multi-tenant). Quan està activa, només les IPs dels CIDRs
// LAN i de la white-list poden autenticar-se i fer servir el sistema. La direcció
// i el superadmin tenen by-pass perquè no s'autobloquegin.

import { useCallback, useEffect, useState } from 'react'
import {
  ShieldCheck, ShieldAlert, Loader2, Save, Wand2,
  CheckCircle2, AlertTriangle, Info, RefreshCw, Activity,
  type LucideIcon,
} from 'lucide-react'
import {
  fetchAccesXarxa, putAccesXarxa, detectaXarxa, fetchProduccioEstat,
  type AccesXarxa, type DeteccioXarxa, type ProduccioReport, type ProduccioControl,
} from '../api/client'

const ESEMPLES_CIDR = '192.168.1.0/24, 10.0.0.0/24, ::1/128'

function esCidrOIp(s: string): boolean {
  s = s.trim()
  if (!s) return false
  // Validació molt lleugera al client (el backend és l'autoritatiu).
  if (s.includes('/')) {
    const [base, mask] = s.split('/')
    const m = Number(mask)
    if (Number.isNaN(m) || m < 0 || m > 128) return false
    return esCidrOIp(base)
  }
  // IPv4 o IPv6 bàsic.
  const v4 = /^(\d{1,3}\.){3}\d{1,3}$/
  const v6 = /^[0-9a-fA-F:]+$/
  return v4.test(s) || (s.includes(':') && v6.test(s))
}

export function SeguretatPage() {
  const [data, setData] = useState<AccesXarxa | null>(null)
  const [actiu, setActiu] = useState(false)
  const [cidrsText, setCidrsText] = useState('')
  const [ipsText, setIpsText] = useState('')
  const [carregant, setCarregant] = useState(true)
  const [desant, setDesant] = useState(false)
  const [detectant, setDetectant] = useState(false)
  const [missatge, setMissatge] = useState<{ ok: boolean; text: string } | null>(null)
  const [deteccio, setDeteccio] = useState<DeteccioXarxa | null>(null)

  const carrega = useCallback(async () => {
    setCarregant(true); setMissatge(null)
    try {
      const d = await fetchAccesXarxa()
      setData(d)
      setActiu(d.actiu)
      setCidrsText(d.cidrs_lan.join('\n'))
      setIpsText(d.ips_permeses.join('\n'))
    } catch (e) {
      setMissatge({ ok: false, text: (e as Error).message })
    } finally {
      setCarregant(false)
    }
  }, [])

  useEffect(() => { void carrega() }, [carrega])

  const cidrsList = cidrsText.split(/[\n,]+/).map(s => s.trim()).filter(Boolean)
  const ipsList = ipsText.split(/[\n,]+/).map(s => s.trim()).filter(Boolean)
  const cidrsInvalides = cidrsList.filter(c => !esCidrOIp(c))
  const ipsInvalides = ipsList.filter(c => !esCidrOIp(c))
  const teInvalides = cidrsInvalides.length + ipsInvalides.length > 0

  async function desa() {
    setDesant(true); setMissatge(null)
    try {
      const d = await putAccesXarxa({
        actiu, cidrs_lan: cidrsList, ips_permeses: ipsList,
      })
      setData(d)
      setMissatge({ ok: true, text: 'Política de xarxa desada.' })
    } catch (e) {
      // Llegim possibles invàlides del detail.
      const err = e as Error & { detail?: { invalides?: [string, string][] } }
      setMissatge({ ok: false, text: err.message })
    } finally {
      setDesant(false)
    }
  }

  async function detectaIA() {
    setDetectant(true)
    try {
      const r = await detectaXarxa()
      setDeteccio(r)
      if (r.cidr_suggerit && !cidrsList.includes(r.cidr_suggerit)) {
        setCidrsText(t => (t ? t.trimEnd() + '\n' : '') + r.cidr_suggerit)
      }
    } catch (e) {
      setMissatge({ ok: false, text: (e as Error).message })
    } finally {
      setDetectant(false)
    }
  }

  function afegirIpActual() {
    if (!data?.ip_actual) return
    if (!ipsList.includes(data.ip_actual)) {
      setIpsText(t => (t ? t.trimEnd() + '\n' : '') + data.ip_actual!)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-fons">
      <div className="max-w-3xl mx-auto px-6 py-8">
        <ProduccioPanell />

        <h1 className="text-2xl font-bold text-navy flex items-center gap-2 mb-1">
          <ShieldCheck size={22} className="text-terra" /> Seguretat de xarxa
        </h1>
        <p className="text-sm text-muted mb-4">
          Defineix qui pot accedir a aquest centre per IP. Per defecte només la xarxa local;
          afegeix IPs concretes a la llista blanca si cal accés des de fora.
          La direcció i el superadmin tenen sempre accés (per no quedar bloquejats).
        </p>

        {carregant ? (
          <div className="text-center text-muted py-12">
            <Loader2 className="animate-spin inline" size={20} /> Carregant…
          </div>
        ) : (
          <>
            {/* Estat actual: IP del peticionari + si entraria */}
            {data?.ip_actual && (
              <div className={`mb-4 p-3 rounded-lg border text-sm flex items-start gap-2 ${
                data.ip_actual_permesa ? 'border-green/40 bg-green/5 text-green' : 'border-red-300 bg-red-50 text-red-700'
              }`}>
                {data.ip_actual_permesa ? <CheckCircle2 size={16} className="shrink-0 mt-0.5" /> : <ShieldAlert size={16} className="shrink-0 mt-0.5" />}
                <div className="flex-1">
                  <div>
                    La teva IP actual és <strong className="font-mono">{data.ip_actual}</strong>.
                    {!actiu && ' La política no està activa: tothom amb credencials pot entrar.'}
                    {actiu && (data.ip_actual_permesa
                      ? ' Està autoritzada amb la política actual.'
                      : ' NO està autoritzada amb la política actual.')}
                  </div>
                  {!ipsList.includes(data.ip_actual) && (
                    <button onClick={afegirIpActual} className="text-xs underline hover:no-underline mt-1">
                      Afegeix la meva IP a la llista blanca
                    </button>
                  )}
                </div>
              </div>
            )}

            {missatge && (
              <div className={`mb-4 px-4 py-2 rounded-lg text-sm border ${
                missatge.ok ? 'bg-green/10 text-green border-green/30' : 'bg-red-50 text-red-600 border-red-200'
              }`}>
                {missatge.text}
              </div>
            )}

            <div className="bg-white rounded-xl border border-border p-5">
              {/* Activació */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={actiu} onChange={e => setActiu(e.target.checked)} />
                <span className="text-sm font-bold text-navy">Activa la política d'accés per IP</span>
              </label>
              <p className="text-xs text-muted mt-1 ml-6">
                Quan està desactivada, qualsevol usuari amb credencials vàlides pot entrar
                des de qualsevol IP (segons la política global del servidor).
              </p>

              {/* CIDRs de xarxa local */}
              <div className="mt-5">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-sm font-semibold text-navy">Xarxa local del centre (CIDRs)</label>
                  <button
                    onClick={() => void detectaIA()}
                    disabled={detectant}
                    title="Proposa el CIDR a partir de la teva IP actual"
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-terra/40 text-terra hover:bg-terra/5 disabled:opacity-40"
                  >
                    {detectant ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />} Detecta xarxa local
                  </button>
                </div>
                <textarea
                  value={cidrsText}
                  onChange={e => setCidrsText(e.target.value)}
                  rows={3}
                  placeholder={`Un per línia. Exemples: ${ESEMPLES_CIDR}`}
                  className="w-full px-3 py-2 border border-border rounded text-sm font-mono focus:outline-none focus:border-navy bg-white"
                />
                {deteccio?.missatge && (
                  <p className="text-[11px] text-muted italic mt-1 flex items-start gap-1">
                    <Info size={11} className="shrink-0 mt-0.5" /> {deteccio.missatge}
                  </p>
                )}
                {cidrsInvalides.length > 0 && (
                  <p className="text-xs text-red-600 mt-1 flex items-start gap-1">
                    <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                    Entrades invàlides: <strong className="font-mono">{cidrsInvalides.join(', ')}</strong>
                  </p>
                )}
                <p className="text-[11px] text-muted mt-1">
                  Format: <span className="font-mono">192.168.1.0/24</span> per a un rang, o una IP simple per a una sola adreça.
                </p>
              </div>

              {/* IPs permeses (white-list) */}
              <div className="mt-5">
                <label className="text-sm font-semibold text-navy block mb-1">
                  Llista blanca d'IPs (accés total)
                </label>
                <textarea
                  value={ipsText}
                  onChange={e => setIpsText(e.target.value)}
                  rows={3}
                  placeholder="IPs públiques o ranges externs autoritzats. Un per línia."
                  className="w-full px-3 py-2 border border-border rounded text-sm font-mono focus:outline-none focus:border-navy bg-white"
                />
                {ipsInvalides.length > 0 && (
                  <p className="text-xs text-red-600 mt-1 flex items-start gap-1">
                    <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                    Entrades invàlides: <strong className="font-mono">{ipsInvalides.join(', ')}</strong>
                  </p>
                )}
                <p className="text-[11px] text-muted mt-1">
                  Útil per a la IP fixa d'un teletreball autoritzat, una VPN concreta, etc.
                </p>
              </div>

              {/* Resum */}
              <div className="mt-5 flex flex-wrap gap-2 text-xs">
                <span className="px-2 py-0.5 rounded-full bg-crema text-navy">
                  CIDRs LAN: <strong>{cidrsList.length}</strong>
                </span>
                <span className="px-2 py-0.5 rounded-full bg-crema text-navy">
                  IPs llista blanca: <strong>{ipsList.length}</strong>
                </span>
                {data?.actualitzat_per && (
                  <span className="px-2 py-0.5 rounded-full bg-crema text-muted">
                    Última actualització: {data.actualitzat_per}
                    {data.actualitzat_el ? ` · ${new Date(data.actualitzat_el).toLocaleString()}` : ''}
                  </span>
                )}
              </div>

              <div className="mt-5 flex items-center gap-2">
                <button
                  onClick={() => void desa()}
                  disabled={desant || teInvalides}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-navy text-white text-sm hover:bg-navy/90 disabled:opacity-40"
                >
                  {desant ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Desa la política
                </button>
                <button
                  onClick={() => void carrega()}
                  disabled={carregant}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-muted text-sm hover:bg-crema"
                >
                  <RefreshCw size={14} /> Refresca
                </button>
              </div>
            </div>

            {/* Avís de bones pràctiques i compliment */}
            <div className="mt-6 p-3 rounded-lg border border-border bg-crema/40 text-xs text-dark">
              <div className="flex items-start gap-2">
                <Info size={14} className="text-navy shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-navy mb-1">Bones pràctiques</p>
                  <ul className="space-y-1 list-disc ml-4">
                    <li>Limita la xarxa local al rang real del centre (p. ex. <span className="font-mono">192.168.1.0/24</span>). No usis rangs molt amplis.</li>
                    <li>La llista blanca és per a excepcions concretes (IPs fixes conegudes). Evita-la si pots accedir per VPN/Tailscale.</li>
                    <li>Quan canvies la política, queda registrada a l'auditoria (<span className="font-mono">acces_xarxa_update</span>) amb el teu usuari.</li>
                    <li>Les peticions denegades per IP es registren com a <span className="font-mono">acces_xarxa_denegat</span> per a revisió posterior.</li>
                    <li>La direcció i el superadmin segueixen tenint accés (per no quedar bloquejats); la resta de rols, només des de la xarxa autoritzada.</li>
                  </ul>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Panell d'estat de producció ─────────────────────────────────────────
// Mostra el resultat de /api/system/produccio amb codi de colors. Només es
// renderitza per a direcció/PAS/superadmin (l'endpoint ja imposa 403 a la resta;
// si el GET falla, el panell s'amaga discretament).

const SEV_CLASS: Record<string, string> = {
  ok: 'border-green/40 bg-green/5 text-green',
  info: 'border-sky-300 bg-sky-50 text-sky-700',
  avis: 'border-terra/40 bg-terra/10 text-terra',
  critic: 'border-red-300 bg-red-50 text-red-700',
}
const SEV_ICONA: Record<string, LucideIcon> = {
  ok: CheckCircle2,
  info: Info,
  avis: AlertTriangle,
  critic: ShieldAlert,
}
const SEV_TXT: Record<string, string> = {
  ok: 'Tot correcte', info: 'Informatiu', avis: 'Avís', critic: 'Crític',
}

function ProduccioPanell() {
  const [data, setData] = useState<ProduccioReport | null>(null)
  const [carregant, setCarregant] = useState(true)
  const [accessible, setAccessible] = useState(true)
  const [obert, setObert] = useState(false)

  const carrega = useCallback(async () => {
    setCarregant(true)
    try {
      setData(await fetchProduccioEstat())
      setAccessible(true)
    } catch {
      setAccessible(false)
    } finally {
      setCarregant(false)
    }
  }, [])

  useEffect(() => { void carrega() }, [carrega])

  if (!accessible || (!carregant && !data)) return null

  return (
    <div className="mb-6 bg-white rounded-xl border border-border overflow-hidden">
      <button
        onClick={() => setObert(o => !o)}
        className="w-full px-5 py-3 flex items-center gap-3 text-left hover:bg-crema/50"
        aria-expanded={obert}
      >
        <Activity size={20} className="text-navy shrink-0" />
        <div className="flex-1">
          <div className="text-sm font-bold text-navy">Estat de producció</div>
          <div className="text-xs text-muted">
            {carregant ? 'Carregant…' : (
              <>
                Entorn <strong>{data?.entorn}</strong> · puntuació <strong>{data?.puntuacio}/100</strong>
              </>
            )}
          </div>
        </div>
        {!carregant && data && (
          <span className={`px-2 py-1 rounded-full text-xs font-semibold border ${SEV_CLASS[data.severitat_global]}`}>
            {SEV_TXT[data.severitat_global]}
          </span>
        )}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); void carrega() }}
          title="Refresca"
          className="ml-2 text-muted hover:text-navy"
        >
          <RefreshCw size={14} />
        </button>
      </button>
      {obert && data && (
        <div className="border-t border-border p-4 space-y-2">
          {data.controls.map(c => <ControlItem key={c.clau} control={c} />)}
          <p className="text-[11px] text-muted italic mt-3">
            Servidor: <span className="font-mono">{data.host}</span> ·
            Versió: <span className="font-mono">{data.versio}</span> ·
            Generat: <span className="font-mono">{new Date(data.ts).toLocaleString()}</span>
          </p>
        </div>
      )}
    </div>
  )
}

function ControlItem({ control }: { control: ProduccioControl }) {
  const Icona = SEV_ICONA[control.severitat] ?? Info
  return (
    <div className={`flex items-start gap-2 p-2.5 rounded-lg border ${SEV_CLASS[control.severitat]}`}>
      <Icona size={14} className="shrink-0 mt-0.5" />
      <div className="flex-1 text-sm">
        <div>
          <strong>{control.titol}:</strong> <span className="text-dark">{control.detall}</span>
        </div>
        {control.recomanacio && (
          <div className="text-xs mt-0.5 text-muted">→ {control.recomanacio}</div>
        )}
      </div>
    </div>
  )
}
