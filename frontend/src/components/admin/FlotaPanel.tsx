// ─── Panell d'operador de flota (NOMÉS superadmin) ──────────────────────────
// Llista tots els centres amb el seu pla, estat de llicència i ús vs límits.
// Permet editar la llicència (pla, dates, estat) de cada centre.

import { useCallback, useEffect, useState } from 'react'
import { Loader2, RefreshCw, Package, Save, AlertTriangle, CheckCircle2 } from 'lucide-react'
import {
  fetchFlota, fetchPlans, putLlicencia,
  type CentreFlota, type PlaComercial,
} from '../../api/client'

const ESTAT_CLASS: Record<string, string> = {
  activa: 'bg-green/15 text-green',
  prova: 'bg-sky-100 text-sky-700',
  suspesa: 'bg-amber-100 text-amber-700',
  caducada: 'bg-red-100 text-red-700',
}

function usText(us: number, limit: number): string {
  return limit > 0 ? `${us}/${limit}` : `${us}/∞`
}

export function FlotaPanel() {
  const [centres, setCentres] = useState<CentreFlota[]>([])
  const [plans, setPlans] = useState<PlaComercial[]>([])
  const [carregant, setCarregant] = useState(true)
  const [editSlug, setEditSlug] = useState<string | null>(null)
  const [form, setForm] = useState<{ pla: string; estat: string; data_caducitat: string }>(
    { pla: '', estat: 'activa', data_caducitat: '' },
  )
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [desant, setDesant] = useState(false)

  const carrega = useCallback(async () => {
    setCarregant(true)
    try {
      const [f, p] = await Promise.all([fetchFlota(), fetchPlans()])
      setCentres(f)
      setPlans(p.plans)
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    } finally {
      setCarregant(false)
    }
  }, [])

  useEffect(() => { void carrega() }, [carrega])

  function obreEdicio(c: CentreFlota) {
    setEditSlug(c.slug)
    setForm({ pla: c.pla, estat: c.estat_llicencia === 'caducada' ? 'activa' : c.estat_llicencia, data_caducitat: c.data_caducitat ?? '' })
    setMsg(null)
  }

  async function desa(slug: string) {
    setDesant(true); setMsg(null)
    try {
      await putLlicencia(slug, {
        pla: form.pla || undefined,
        estat: form.estat || undefined,
        data_caducitat: form.data_caducitat || undefined,
      })
      setMsg({ ok: true, text: `Llicència de «${slug}» desada.` })
      setEditSlug(null)
      await carrega()
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    } finally {
      setDesant(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-border p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold text-navy flex items-center gap-1.5">
          <Package size={16} /> Flota de centres · llicències
        </h2>
        <button onClick={() => void carrega()} className="text-muted hover:text-navy" title="Refresca">
          <RefreshCw size={14} />
        </button>
      </div>

      {msg && (
        <div className={`mb-3 px-3 py-2 rounded-lg text-sm border ${msg.ok ? 'bg-green/10 text-green border-green/30' : 'bg-red-50 text-red-600 border-red-200'}`}>
          {msg.text}
        </div>
      )}

      {carregant ? (
        <p className="text-sm text-muted text-center py-6"><Loader2 className="animate-spin inline" size={16} /> Carregant flota…</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-crema text-muted text-left">
                <th className="px-3 py-2 font-semibold">Centre</th>
                <th className="px-3 py-2 font-semibold">Pla</th>
                <th className="px-3 py-2 font-semibold">Estat</th>
                <th className="px-3 py-2 font-semibold">Caducitat</th>
                <th className="px-3 py-2 font-semibold">Usuaris</th>
                <th className="px-3 py-2 font-semibold">Docs</th>
                <th className="px-3 py-2 font-semibold w-24"></th>
              </tr>
            </thead>
            <tbody>
              {centres.map(c => {
                const editant = editSlug === c.slug
                const caduca_aviat = c.dies_fins_caducitat != null && c.dies_fins_caducitat <= 30
                return (
                  <tr key={c.slug} className="border-t border-border align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium text-dark">{c.nom}</div>
                      <div className="text-xs text-muted font-mono">{c.slug}</div>
                    </td>
                    <td className="px-3 py-2">
                      {editant ? (
                        <select value={form.pla} onChange={e => setForm({ ...form, pla: e.target.value })} className="px-2 py-1 border border-border rounded text-sm">
                          {plans.map(p => <option key={p.id} value={p.id}>{p.nom}</option>)}
                        </select>
                      ) : <span className="text-dark">{c.pla_nom}</span>}
                    </td>
                    <td className="px-3 py-2">
                      {editant ? (
                        <select value={form.estat} onChange={e => setForm({ ...form, estat: e.target.value })} className="px-2 py-1 border border-border rounded text-sm">
                          <option value="activa">activa</option>
                          <option value="prova">prova</option>
                          <option value="suspesa">suspesa</option>
                        </select>
                      ) : (
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${ESTAT_CLASS[c.estat_llicencia] ?? ''}`}>
                          {c.estat_llicencia}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {editant ? (
                        <input type="date" value={form.data_caducitat} onChange={e => setForm({ ...form, data_caducitat: e.target.value })} className="px-2 py-1 border border-border rounded text-sm" />
                      ) : c.data_caducitat ? (
                        <span className={caduca_aviat ? 'text-amber-700 font-semibold inline-flex items-center gap-1' : 'text-muted'}>
                          {caduca_aviat && <AlertTriangle size={11} />}
                          {c.data_caducitat}{c.dies_fins_caducitat != null ? ` (${c.dies_fins_caducitat}d)` : ''}
                        </span>
                      ) : <span className="text-muted">perpètua</span>}
                    </td>
                    <td className="px-3 py-2 text-muted">{usText(c.us.usuaris ?? 0, c.limits.max_usuaris ?? 0)}</td>
                    <td className="px-3 py-2 text-muted">{usText(c.us.documents ?? 0, c.limits.max_documents ?? 0)}</td>
                    <td className="px-3 py-2 text-right">
                      {editant ? (
                        <div className="flex gap-1 justify-end">
                          <button onClick={() => void desa(c.slug)} disabled={desant} className="text-green hover:text-green/80" title="Desa">
                            {desant ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                          </button>
                          <button onClick={() => setEditSlug(null)} className="text-muted hover:text-dark" title="Cancel·la">✕</button>
                        </div>
                      ) : (
                        <button onClick={() => obreEdicio(c)} className="text-xs text-navy underline hover:no-underline">Editar</button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {centres.length === 0 && (
                <tr><td colSpan={7} className="px-3 py-6 text-center text-muted">Cap centre.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] text-muted italic mt-2 flex items-center gap-1">
        <CheckCircle2 size={11} /> Sense llicència definida, un centre opera en pla Enterprise (tot actiu). Model: instància dedicada per centre.
      </p>
    </div>
  )
}
