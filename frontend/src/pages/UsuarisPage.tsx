// ─── Usuaris del centre (gestió per a la DIRECCIÓ) ───────────────────────────
// La direcció gestiona NOMÉS els usuaris del SEU centre (l'API ho força per
// institució). No es pot crear ni assignar el rol superadmin des d'aquí.

import { useCallback, useEffect, useState } from 'react'
import { Users, Plus, Trash2, Loader2, RefreshCw, KeyRound, Power } from 'lucide-react'
import {
  fetchInstitucioUsers, createInstitucioUser, updateInstitucioUser, deleteInstitucioUser,
} from '../api/client'
import { useAppStore } from '../store/appStore'
import type { User } from '../types'

const inputCls = 'w-full px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy'
// La direcció pot assignar aquests rols (MAI superadmin → ho impedeix també el backend).
const ROLS_ASSIGNABLES = ['docent', 'alumne', 'familia', 'pas', 'direccio']
const ROL_LABEL: Record<string, string> = {
  docent: 'Docent', alumne: 'Alumne', familia: 'Família', pas: 'PAS',
  direccio: 'Direcció', superadmin: 'Superadmin',
}

export function UsuarisPage() {
  const { state } = useAppStore()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [estat, setEstat] = useState<{ ok: boolean; text: string } | null>(null)
  const [nou, setNou] = useState({ username: '', contrasenya: '', rol: 'docent', nom: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setUsers(await fetchInstitucioUsers())
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function handleCrear() {
    if (!nou.username.trim() || !nou.contrasenya) return
    try {
      await createInstitucioUser({
        username: nou.username.trim(), contrasenya: nou.contrasenya,
        rol: nou.rol, nom: nou.nom || undefined,
      })
      setEstat({ ok: true, text: `Usuari «${nou.username.trim()}» creat.` })
      setNou({ username: '', contrasenya: '', rol: 'docent', nom: '' })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function toggleActiu(u: User) {
    try {
      await updateInstitucioUser(u.username, { actiu: !u.actiu })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function resetPassword(u: User) {
    const nova = window.prompt(`Nova contrasenya per a «${u.username}»:`)
    if (!nova) return
    try {
      await updateInstitucioUser(u.username, { contrasenya: nova })
      setEstat({ ok: true, text: `Contrasenya de «${u.username}» actualitzada.` })
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function esborrar(u: User) {
    if (!window.confirm(`Esborrar l'usuari «${u.username}»? Aquesta acció no es pot desfer.`)) return
    try {
      await deleteInstitucioUser(u.username)
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-fons">
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
            <Users size={22} className="text-terra" /> Usuaris del centre
          </h1>
          <button onClick={() => void load()} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-white text-sm text-dark hover:bg-crema">
            <RefreshCw size={14} /> Actualitza
          </button>
        </div>
        <p className="text-sm text-muted mb-4">
          Gestió dels usuaris de <strong>{state.institucio?.nom ?? 'el teu centre'}</strong>.
          Només veus i gestiones els usuaris d'aquesta institució.
        </p>

        {estat && (
          <div className={`mb-4 px-4 py-2 rounded-lg text-sm border ${estat.ok ? 'bg-green/10 text-green border-green/30' : 'bg-red-50 text-red-600 border-red-200'}`}>
            {estat.text}
          </div>
        )}

        {/* Nou usuari */}
        <div className="bg-white rounded-xl border border-border p-4 mb-6">
          <h2 className="text-sm font-bold text-navy mb-3 flex items-center gap-1.5"><Plus size={16} /> Nou usuari</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input value={nou.username} onChange={e => setNou({ ...nou, username: e.target.value })} placeholder="Nom d'usuari" className={inputCls} autoComplete="off" />
            <input value={nou.nom} onChange={e => setNou({ ...nou, nom: e.target.value })} placeholder="Nom complet (opcional)" className={inputCls} />
            <input type="password" value={nou.contrasenya} onChange={e => setNou({ ...nou, contrasenya: e.target.value })} placeholder="Contrasenya inicial" className={inputCls} autoComplete="new-password" />
            <label className="text-xs text-muted">Rol
              <select value={nou.rol} onChange={e => setNou({ ...nou, rol: e.target.value })} className={`${inputCls} mt-1 bg-white`}>
                {ROLS_ASSIGNABLES.map(r => <option key={r} value={r}>{ROL_LABEL[r]}</option>)}
              </select>
            </label>
          </div>
          <button onClick={() => void handleCrear()} disabled={!nou.username.trim() || !nou.contrasenya} className="mt-3 px-4 py-2 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 disabled:opacity-40">
            Crear usuari
          </button>
        </div>

        {loading ? (
          <div className="text-center text-muted py-8"><Loader2 className="animate-spin inline" size={18} /> Carregant…</div>
        ) : users.length === 0 ? (
          <div className="bg-white rounded-xl border border-border p-8 text-center text-sm text-muted">Cap usuari.</div>
        ) : (
          <div className="bg-white rounded-xl border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-crema text-muted text-left">
                  <th className="px-4 py-2 font-semibold">Usuari</th>
                  <th className="px-4 py-2 font-semibold">Nom</th>
                  <th className="px-4 py-2 font-semibold w-28">Rol</th>
                  <th className="px-4 py-2 font-semibold w-20">Estat</th>
                  <th className="px-4 py-2 font-semibold w-32 text-right">Accions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.username} className="border-t border-border">
                    <td className="px-4 py-2 font-mono text-xs text-navy">{u.username}</td>
                    <td className="px-4 py-2 text-dark">{u.nom ?? '—'}</td>
                    <td className="px-4 py-2"><span className="text-xs px-2 py-0.5 rounded bg-navy/10 text-navy">{ROL_LABEL[u.rol] ?? u.rol}</span></td>
                    <td className="px-4 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${u.actiu ? 'bg-green/15 text-green' : 'bg-muted/15 text-muted'}`}>
                        {u.actiu ? 'Actiu' : 'Inactiu'}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <button onClick={() => void toggleActiu(u)} title={u.actiu ? 'Desactivar' : 'Activar'} className="text-muted hover:text-navy mr-2"><Power size={15} /></button>
                      <button onClick={() => void resetPassword(u)} title="Restablir contrasenya" className="text-muted hover:text-navy mr-2"><KeyRound size={15} /></button>
                      <button onClick={() => void esborrar(u)} title="Esborrar" className="text-muted hover:text-red-600"><Trash2 size={15} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-muted mt-3 italic">
          Aïllament per institució: només es mostren els usuaris del teu centre · no es pot crear ni assignar el rol superadmin · auditat.
        </p>
      </div>
    </div>
  )
}
