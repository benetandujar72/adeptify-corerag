// ─── Pàgina d'Administració (NOMÉS superadmin) ──────────────────────────────
// Gestió d'institucions (multi-tenant) + CRUD d'usuaris + visor d'auditoria forense.

import { useCallback, useEffect, useState } from 'react'
import {
  Loader2,
  UserPlus,
  Trash2,
  ShieldCheck,
  RefreshCw,
  ScrollText,
  Building2,
  Plus,
  Save,
  X,
  Pencil,
} from 'lucide-react'
import {
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
  fetchAudit,
  fetchInstitucions,
  createInstitucio,
  updateInstitucio,
  deleteInstitucio,
} from '../api/client'
import { FlotaPanel } from '../components/admin/FlotaPanel'
import type { AuditEntry, Institucio, User } from '../types'

const ROLS = ['docent', 'alumne', 'familia', 'direccio', 'pas', 'superadmin']

interface EditInstForm {
  nom: string
  actiu: boolean
  color_primari: string
  color_secundari: string
  logo_url: string
  logo_text: string
  lema: string
  llm_model: string
  agents_actius: string // separats per comes
}

const DEFAULT_PRIMARI = '#0B2545'
const DEFAULT_SECUNDARI = '#C97B4E'

export function AdminPage() {
  const [users, setUsers] = useState<User[]>([])
  const [insts, setInsts] = useState<Institucio[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [estat, setEstat] = useState<{ ok: boolean; text: string } | null>(null)
  const [nou, setNou] = useState({
    username: '',
    contrasenya: '',
    rol: 'docent',
    nom: '',
    institucio_id: 'nou_patufet',
  })
  const [nouInst, setNouInst] = useState({
    slug: '',
    nom: '',
    color_primari: DEFAULT_PRIMARI,
    color_secundari: DEFAULT_SECUNDARI,
    logo_url: '',
    llm_model: '',
  })
  const [editSlug, setEditSlug] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditInstForm | null>(null)
  const [filtreAccio, setFiltreAccio] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [us, ins, au] = await Promise.all([
        fetchUsers(),
        fetchInstitucions(),
        fetchAudit({ limit: 100 }),
      ])
      setUsers(us)
      setInsts(ins)
      setAudit(au.entrades)
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // ─── Usuaris ────────────────────────────────────────────────────────────────

  async function handleCrear() {
    if (!nou.username.trim() || !nou.contrasenya) return
    try {
      await createUser({ ...nou, username: nou.username.trim() })
      setEstat({ ok: true, text: `Usuari "${nou.username}" creat.` })
      setNou({ username: '', contrasenya: '', rol: 'docent', nom: '', institucio_id: 'nou_patufet' })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function handleCanviRol(u: User, rol: string) {
    try {
      await updateUser(u.username, { rol }, u.institucio_id)
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function handleToggleActiu(u: User) {
    try {
      await updateUser(u.username, { actiu: !u.actiu }, u.institucio_id)
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function handleReset(u: User) {
    const pwd = window.prompt(`Nova contrasenya per a "${u.username}":`)
    if (!pwd) return
    try {
      await updateUser(u.username, { contrasenya: pwd }, u.institucio_id)
      setEstat({ ok: true, text: `Contrasenya de "${u.username}" actualitzada.` })
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function handleEsborrar(u: User) {
    if (!window.confirm(`Esborrar l'usuari "${u.username}" (${u.institucio_id})? No es pot desfer.`)) return
    try {
      await deleteUser(u.username, u.institucio_id)
      setEstat({ ok: true, text: `Usuari "${u.username}" esborrat.` })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  // ─── Institucions ─────────────────────────────────────────────────────────────

  async function handleCrearInst() {
    const slug = nouInst.slug
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/^_+|_+$/g, '')
    if (!slug || !nouInst.nom.trim()) {
      setEstat({ ok: false, text: 'Cal un identificador (slug) i un nom.' })
      return
    }
    try {
      await createInstitucio({
        slug,
        nom: nouInst.nom.trim(),
        branding: {
          color_primari: nouInst.color_primari,
          color_secundari: nouInst.color_secundari,
          ...(nouInst.logo_url.trim() ? { logo_url: nouInst.logo_url.trim() } : {}),
        },
        ...(nouInst.llm_model.trim()
          ? { config: { llm_model: nouInst.llm_model.trim() } }
          : {}),
      })
      setEstat({ ok: true, text: `Institució "${slug}" creada.` })
      setNouInst({
        slug: '',
        nom: '',
        color_primari: DEFAULT_PRIMARI,
        color_secundari: DEFAULT_SECUNDARI,
        logo_url: '',
        llm_model: '',
      })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  function startEdit(i: Institucio) {
    setEditSlug(i.slug)
    setEditForm({
      nom: i.nom,
      actiu: i.actiu,
      color_primari: i.branding?.color_primari ?? DEFAULT_PRIMARI,
      color_secundari: i.branding?.color_secundari ?? DEFAULT_SECUNDARI,
      logo_url: i.branding?.logo_url ?? '',
      logo_text: i.branding?.logo_text ?? '',
      lema: i.branding?.lema ?? '',
      llm_model: i.config?.llm_model ?? '',
      agents_actius: (i.config?.agents_actius ?? []).join(', '),
    })
  }

  function cancelEdit() {
    setEditSlug(null)
    setEditForm(null)
  }

  async function handleDesaEdit() {
    if (!editSlug || !editForm) return
    const agents = editForm.agents_actius
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
    try {
      await updateInstitucio(editSlug, {
        nom: editForm.nom.trim() || editSlug,
        actiu: editForm.actiu,
        branding: {
          color_primari: editForm.color_primari,
          color_secundari: editForm.color_secundari,
          ...(editForm.logo_url.trim() ? { logo_url: editForm.logo_url.trim() } : {}),
          ...(editForm.logo_text.trim() ? { logo_text: editForm.logo_text.trim() } : {}),
          ...(editForm.lema.trim() ? { lema: editForm.lema.trim() } : {}),
        },
        config: {
          ...(editForm.llm_model.trim() ? { llm_model: editForm.llm_model.trim() } : {}),
          ...(agents.length ? { agents_actius: agents } : {}),
        },
      })
      setEstat({ ok: true, text: `Institució "${editSlug}" actualitzada.` })
      cancelEdit()
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function handleToggleInstActiu(i: Institucio) {
    try {
      await updateInstitucio(i.slug, { actiu: !i.actiu })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  async function handleEsborrarInst(i: Institucio) {
    if (i.slug === 'nou_patufet') {
      setEstat({ ok: false, text: 'No es pot esborrar la institució per defecte.' })
      return
    }
    if (
      !window.confirm(
        `Esborrar la institució "${i.slug}"? Els seus usuaris i documents quedaran sense institució.`,
      )
    )
      return
    try {
      await deleteInstitucio(i.slug)
      setEstat({ ok: true, text: `Institució "${i.slug}" esborrada.` })
      await load()
    } catch (e) {
      setEstat({ ok: false, text: (e as Error).message })
    }
  }

  const auditFiltrat = filtreAccio ? audit.filter(a => a.accio.includes(filtreAccio)) : audit
  const opcionsInst: { slug: string; nom: string }[] =
    insts.length > 0
      ? insts.map(i => ({ slug: i.slug, nom: i.nom }))
      : [{ slug: 'nou_patufet', nom: 'Escola Nou Patufet' }]

  return (
    <div className="flex-1 overflow-y-auto bg-fons">
      <div className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
              <ShieldCheck size={22} className="text-terra" /> Administració
            </h1>
            <p className="text-sm text-muted mt-1">
              Institucions (multi-tenant), usuaris i registre forense. Accés exclusiu del superadmin.
            </p>
          </div>
          <button
            onClick={() => void load()}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-white text-sm text-dark hover:bg-crema transition-colors"
          >
            <RefreshCw size={14} /> Actualitza
          </button>
        </div>

        {estat && (
          <div
            className={`mb-4 px-4 py-2 rounded-lg text-sm border ${
              estat.ok
                ? 'bg-green/10 text-green border-green/30'
                : 'bg-red-50 text-red-600 border-red-200'
            }`}
          >
            {estat.text}
          </div>
        )}

        {/* ─── Institucions (multi-tenant) ─────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-border p-4 mb-6">
          <h2 className="text-sm font-bold text-navy mb-3 flex items-center gap-1.5">
            <Building2 size={16} /> Institucions (creador de RAGs)
          </h2>

          {/* Crear institució */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 mb-2">
            <input
              value={nouInst.slug}
              onChange={e => setNouInst({ ...nouInst, slug: e.target.value })}
              placeholder="identificador (slug)"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
            <input
              value={nouInst.nom}
              onChange={e => setNouInst({ ...nouInst, nom: e.target.value })}
              placeholder="nom de la institució"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
            <input
              value={nouInst.logo_url}
              onChange={e => setNouInst({ ...nouInst, logo_url: e.target.value })}
              placeholder="URL del logo (opcional)"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
            <input
              value={nouInst.llm_model}
              onChange={e => setNouInst({ ...nouInst, llm_model: e.target.value })}
              placeholder="model LLM (opcional)"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-muted">
              Color primari
              <input
                type="color"
                value={nouInst.color_primari}
                onChange={e => setNouInst({ ...nouInst, color_primari: e.target.value })}
                className="w-8 h-8 rounded border border-border bg-white cursor-pointer"
              />
            </label>
            <label className="flex items-center gap-1.5 text-xs text-muted">
              Color accent
              <input
                type="color"
                value={nouInst.color_secundari}
                onChange={e => setNouInst({ ...nouInst, color_secundari: e.target.value })}
                className="w-8 h-8 rounded border border-border bg-white cursor-pointer"
              />
            </label>
            <button
              onClick={() => void handleCrearInst()}
              disabled={!nouInst.slug.trim() || !nouInst.nom.trim()}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 disabled:opacity-40 ml-auto"
            >
              <Plus size={15} /> Crear institució
            </button>
          </div>

          {/* Editor d'institució */}
          {editForm && editSlug && (
            <div className="mt-4 rounded-lg border border-navy/30 bg-crema/60 p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-navy flex items-center gap-1.5">
                  <Pencil size={14} /> Editant <code className="text-terra">{editSlug}</code>
                </h3>
                <button onClick={cancelEdit} className="text-muted hover:text-dark">
                  <X size={16} />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="text-xs text-muted">
                  Nom
                  <input
                    value={editForm.nom}
                    onChange={e => setEditForm({ ...editForm, nom: e.target.value })}
                    className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm text-dark focus:outline-none focus:border-navy"
                  />
                </label>
                <label className="text-xs text-muted">
                  Lema / subtítol
                  <input
                    value={editForm.lema}
                    onChange={e => setEditForm({ ...editForm, lema: e.target.value })}
                    placeholder="· IA Assistent"
                    className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm text-dark focus:outline-none focus:border-navy"
                  />
                </label>
                <label className="text-xs text-muted">
                  URL del logo
                  <input
                    value={editForm.logo_url}
                    onChange={e => setEditForm({ ...editForm, logo_url: e.target.value })}
                    placeholder="https://…/logo.png"
                    className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm text-dark focus:outline-none focus:border-navy"
                  />
                </label>
                <label className="text-xs text-muted">
                  Inicials del logo (si no hi ha URL)
                  <input
                    value={editForm.logo_text}
                    onChange={e => setEditForm({ ...editForm, logo_text: e.target.value })}
                    placeholder="NP"
                    maxLength={3}
                    className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm text-dark focus:outline-none focus:border-navy"
                  />
                </label>
                <label className="text-xs text-muted">
                  Model LLM
                  <input
                    value={editForm.llm_model}
                    onChange={e => setEditForm({ ...editForm, llm_model: e.target.value })}
                    placeholder="qwen2.5:7b"
                    className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm text-dark focus:outline-none focus:border-navy"
                  />
                </label>
                <label className="text-xs text-muted">
                  Agents actius (ids separats per comes; buit = tots)
                  <input
                    value={editForm.agents_actius}
                    onChange={e => setEditForm({ ...editForm, agents_actius: e.target.value })}
                    placeholder="tutor_mates, secretaria, families"
                    className="mt-1 w-full px-3 py-2 border border-border rounded-lg text-sm text-dark focus:outline-none focus:border-navy"
                  />
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-4 mt-3">
                <label className="flex items-center gap-1.5 text-xs text-muted">
                  Color primari
                  <input
                    type="color"
                    value={editForm.color_primari}
                    onChange={e => setEditForm({ ...editForm, color_primari: e.target.value })}
                    className="w-8 h-8 rounded border border-border bg-white cursor-pointer"
                  />
                </label>
                <label className="flex items-center gap-1.5 text-xs text-muted">
                  Color accent
                  <input
                    type="color"
                    value={editForm.color_secundari}
                    onChange={e => setEditForm({ ...editForm, color_secundari: e.target.value })}
                    className="w-8 h-8 rounded border border-border bg-white cursor-pointer"
                  />
                </label>
                <label className="flex items-center gap-1.5 text-xs text-dark">
                  <input
                    type="checkbox"
                    checked={editForm.actiu}
                    onChange={e => setEditForm({ ...editForm, actiu: e.target.checked })}
                  />
                  Activa
                </label>
                <button
                  onClick={() => void handleDesaEdit()}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 ml-auto"
                >
                  <Save size={15} /> Desa
                </button>
              </div>
            </div>
          )}

          {/* Taula d'institucions */}
          <div className="mt-4 rounded-lg border border-border overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-crema text-muted text-left">
                  <th className="px-3 py-2 font-semibold">Slug</th>
                  <th className="px-3 py-2 font-semibold">Nom</th>
                  <th className="px-3 py-2 font-semibold w-24">Colors</th>
                  <th className="px-3 py-2 font-semibold w-32">Model</th>
                  <th className="px-3 py-2 font-semibold w-20">Estat</th>
                  <th className="px-3 py-2 font-semibold w-24"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted">
                      <Loader2 className="animate-spin inline" size={16} /> Carregant…
                    </td>
                  </tr>
                ) : (
                  insts.map(i => (
                    <tr key={i.slug} className="border-t border-border hover:bg-crema/50">
                      <td className="px-3 py-2 font-mono text-xs text-dark">{i.slug}</td>
                      <td className="px-3 py-2 text-dark">{i.nom}</td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <span
                            className="w-5 h-5 rounded border border-border"
                            style={{ backgroundColor: i.branding?.color_primari ?? DEFAULT_PRIMARI }}
                            title={i.branding?.color_primari ?? DEFAULT_PRIMARI}
                          />
                          <span
                            className="w-5 h-5 rounded border border-border"
                            style={{
                              backgroundColor: i.branding?.color_secundari ?? DEFAULT_SECUNDARI,
                            }}
                            title={i.branding?.color_secundari ?? DEFAULT_SECUNDARI}
                          />
                        </div>
                      </td>
                      <td className="px-3 py-2 text-muted text-xs">{i.config?.llm_model ?? '—'}</td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => void handleToggleInstActiu(i)}
                          className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                            i.actiu ? 'bg-green/15 text-green' : 'bg-red-100 text-red-600'
                          }`}
                        >
                          {i.actiu ? 'activa' : 'inactiva'}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <button
                          onClick={() => startEdit(i)}
                          title="Editar"
                          className="text-muted hover:text-navy mr-3"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          onClick={() => void handleEsborrarInst(i)}
                          title={
                            i.slug === 'nou_patufet'
                              ? 'No es pot esborrar la institució per defecte'
                              : 'Esborrar'
                          }
                          disabled={i.slug === 'nou_patufet'}
                          className="text-muted hover:text-red-600 disabled:opacity-30 disabled:hover:text-muted"
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
                {!loading && insts.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted">
                      Cap institució.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ─── Flota de centres · llicències ───────────────────────────────── */}
        <FlotaPanel />

        {/* ─── Crear usuari ─────────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-border p-4 mb-6">
          <h2 className="text-sm font-bold text-navy mb-3 flex items-center gap-1.5">
            <UserPlus size={16} /> Nou usuari
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-6 gap-2">
            <input
              value={nou.username}
              onChange={e => setNou({ ...nou, username: e.target.value })}
              placeholder="usuari"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
            <input
              value={nou.nom}
              onChange={e => setNou({ ...nou, nom: e.target.value })}
              placeholder="nom complet"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
            <input
              type="password"
              value={nou.contrasenya}
              onChange={e => setNou({ ...nou, contrasenya: e.target.value })}
              placeholder="contrasenya"
              className="px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:border-navy"
            />
            <select
              value={nou.rol}
              onChange={e => setNou({ ...nou, rol: e.target.value })}
              className="px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:border-navy"
            >
              {ROLS.map(r => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <select
              value={nou.institucio_id}
              onChange={e => setNou({ ...nou, institucio_id: e.target.value })}
              className="px-3 py-2 border border-border rounded-lg text-sm bg-white focus:outline-none focus:border-navy"
              title="Institució de l'usuari"
            >
              {opcionsInst.map(o => (
                <option key={o.slug} value={o.slug}>
                  {o.nom} ({o.slug})
                </option>
              ))}
            </select>
            <button
              onClick={() => void handleCrear()}
              disabled={!nou.username.trim() || !nou.contrasenya}
              className="px-3 py-2 rounded-lg bg-navy text-white text-sm font-semibold hover:bg-navy/90 disabled:opacity-40"
            >
              Crear
            </button>
          </div>
        </div>

        {/* ─── Taula d'usuaris ──────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-border overflow-hidden mb-8">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-crema text-muted text-left">
                <th className="px-4 py-2.5 font-semibold">Usuari</th>
                <th className="px-4 py-2.5 font-semibold">Nom</th>
                <th className="px-4 py-2.5 font-semibold w-36">Rol</th>
                <th className="px-4 py-2.5 font-semibold w-32">Institució</th>
                <th className="px-4 py-2.5 font-semibold w-24">Actiu</th>
                <th className="px-4 py-2.5 font-semibold w-28">Últim accés</th>
                <th className="px-4 py-2.5 font-semibold w-28"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-muted">
                    <Loader2 className="animate-spin inline" size={18} /> Carregant…
                  </td>
                </tr>
              ) : (
                users.map(u => (
                  <tr key={u.username} className="border-t border-border hover:bg-crema/50">
                    <td className="px-4 py-2.5 font-medium text-dark">{u.username}</td>
                    <td className="px-4 py-2.5 text-muted">{u.nom ?? '—'}</td>
                    <td className="px-4 py-2.5">
                      <select
                        value={u.rol}
                        onChange={e => void handleCanviRol(u, e.target.value)}
                        className="px-2 py-1 border border-border rounded text-xs bg-white"
                      >
                        {ROLS.map(r => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2.5 text-muted text-xs font-mono">
                      {u.institucio_id ?? 'nou_patufet'}
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => void handleToggleActiu(u)}
                        className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                          u.actiu ? 'bg-green/15 text-green' : 'bg-red-100 text-red-600'
                        }`}
                      >
                        {u.actiu ? 'actiu' : 'inactiu'}
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-muted text-xs">
                      {u.ultim_acces ? new Date(u.ultim_acces).toLocaleString('ca') : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      <button
                        onClick={() => void handleReset(u)}
                        title="Restablir contrasenya"
                        className="text-muted hover:text-navy mr-3 text-xs underline"
                      >
                        clau
                      </button>
                      <button
                        onClick={() => void handleEsborrar(u)}
                        title="Esborrar"
                        className="text-muted hover:text-red-600"
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* ─── Auditoria forense ────────────────────────────────────────────── */}
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-navy flex items-center gap-1.5">
            <ScrollText size={16} /> Registre d'auditoria (forense)
          </h2>
          <input
            value={filtreAccio}
            onChange={e => setFiltreAccio(e.target.value)}
            placeholder="filtra per acció (login, chat, institucio_create…)"
            className="px-3 py-1.5 border border-border rounded-lg text-xs w-72 focus:outline-none focus:border-navy"
          />
        </div>
        <div className="bg-white rounded-xl border border-border overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-crema text-muted text-left">
                <th className="px-4 py-2 font-semibold w-40">Data</th>
                <th className="px-4 py-2 font-semibold w-32">Usuari</th>
                <th className="px-4 py-2 font-semibold w-24">Rol</th>
                <th className="px-4 py-2 font-semibold w-32">Acció</th>
                <th className="px-4 py-2 font-semibold">Detalls</th>
              </tr>
            </thead>
            <tbody>
              {auditFiltrat.slice(0, 100).map(a => (
                <tr key={a.id} className="border-t border-border">
                  <td className="px-4 py-1.5 text-muted">
                    {new Date(a.creat_el).toLocaleString('ca')}
                  </td>
                  <td className="px-4 py-1.5 text-dark">{a.usuari}</td>
                  <td className="px-4 py-1.5 text-muted">{a.rol}</td>
                  <td className="px-4 py-1.5">
                    <span className="px-1.5 py-0.5 rounded bg-navy/5 text-navy font-medium">
                      {a.accio}
                    </span>
                  </td>
                  <td className="px-4 py-1.5 text-muted truncate max-w-0">
                    {a.detalls ? JSON.stringify(a.detalls) : (a.agent ?? '')}
                  </td>
                </tr>
              ))}
              {!loading && auditFiltrat.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-muted">
                    Cap entrada.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
