import { notificaEntrada } from '../auth/cookieSession'
// ─── Pàgina de login: selecció d'institució + usuari/contrasenya ─────────────
// Pas 1: selecciona el centre (auto si n'hi ha un de sol; selector si n'hi ha més).
//        Així queda EXPLÍCIT a quina institució et valides (multi-tenant).
// Pas 2: usuari + contrasenya → s'autentica DINS d'aquella institució.

import { useEffect, useState, FormEvent } from 'react'
import { Building2, ChevronLeft, Languages } from 'lucide-react'
import { login, fetchInstitucionsPubliques } from '../api/client'
import { useAppStore } from '../store/appStore'
import { useT, type Idioma } from '../i18n'
import { IDIOMES_ADMESOS, NOM_IDIOMA } from '../i18n/catalogs'
import type { InstitucioPublica } from '../types'

const inicials = (s: string) =>
  s.split(/\s+/).map(w => w[0]?.toUpperCase() ?? '').slice(0, 2).join('') || 'NP'

export function LoginPage() {
  const { dispatch } = useAppStore()
  const { t, idioma, setIdioma } = useT()
  const [institucions, setInstitucions] = useState<InstitucioPublica[]>([])
  const [institucioSel, setInstitucioSel] = useState<string | null>(null)
  const [carregant, setCarregant] = useState(true)
  const [usuari, setUsuari] = useState('')
  const [contrasenya, setContrasenya] = useState('')
  const [codiMfa, setCodiMfa] = useState('')
  const [mfaPendent, setMfaPendent] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Pas 1: carrega les institucions actives. Auto-selecció si n'hi ha una de sola.
  useEffect(() => {
    let viu = true
    fetchInstitucionsPubliques()
      .then(items => {
        if (!viu) return
        setInstitucions(items)
        if (items.length === 1) setInstitucioSel(items[0].slug)
        else if (items.length === 0) setInstitucioSel('') // BD sense institucions → login sense filtre
      })
      .catch(() => {
        if (viu) setInstitucioSel('') // si falla, permet login sense selecció (compat)
      })
      .finally(() => viu && setCarregant(false))
    return () => {
      viu = false
    }
  }, [])

  const inst = institucions.find(i => i.slug === institucioSel) ?? null
  const nom = inst?.nom ?? 'Nou Patufet · IA Assistent'
  const logoText = inst?.branding?.logo_text || (inst?.nom ? inicials(inst.nom) : 'NP')
  const logoUrl = inst?.branding?.logo_url
  const potCanviar = institucions.length > 1

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!usuari.trim() || !contrasenya) return
    setLoading(true)
    setError(null)
    try {
      const resp = await login(
        usuari.trim(), contrasenya, institucioSel || undefined,
        mfaPendent ? codiMfa.trim() : undefined,
      )
      if (resp.mfa_required) {
        // Credencials correctes: cal el segon factor. Mostra el camp de codi.
        setMfaPendent(true)
        setLoading(false)
        return
      }



      notificaEntrada()
      dispatch({
        type: 'SET_SESSION',
        payload: { usuari: usuari.trim(), rol: resp.rol },
      })
    } catch (err) {
      setError((err as Error).message || 'Usuari o contrasenya incorrectes.')
    } finally {
      setLoading(false)
    }
  }

  // ── Pas 1: selector d'institució (només si n'hi ha més d'una) ──────────────
  const mostraSelector = !carregant && institucioSel === null && institucions.length > 1

  return (
    <div className="min-h-screen bg-fons flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-navy mb-4 overflow-hidden">
            {logoUrl && !mostraSelector ? (
              <img src={logoUrl} alt={nom} className="w-full h-full object-cover" />
            ) : (
              <span className="text-white font-bold text-2xl">{mostraSelector ? <Building2 size={28} /> : logoText}</span>
            )}
          </div>
          <h1 className="text-2xl font-bold text-navy">
            {mostraSelector ? t('login.centre') : nom}
          </h1>
          <p className="text-muted text-sm mt-1">Sistema self-hosted · 100% local</p>

          {/* Selector d'idioma (ca/es/eu) — accessible des de la pantalla de login */}
          <div className="mt-3 inline-flex items-center gap-2 text-xs text-muted">
            <Languages size={12} />
            <span>{t('login.idioma')}:</span>
            {IDIOMES_ADMESOS.map(i => (
              <button
                key={i}
                onClick={() => setIdioma(i as Idioma)}
                className={`px-2 py-0.5 rounded ${i === idioma ? 'bg-navy text-white' : 'text-muted hover:text-navy'}`}
                aria-pressed={i === idioma}
                aria-label={NOM_IDIOMA[i as Idioma]}
              >
                {i.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border border-border p-8">
          {carregant ? (
            <div className="flex items-center justify-center py-8 text-muted text-sm gap-2">
              <span className="w-4 h-4 border-2 border-navy border-t-transparent rounded-full animate-spin" />
              Carregant…
            </div>
          ) : mostraSelector ? (
            // ── Pas 1: tria d'institució ──
            <>
              <h2 className="text-lg font-bold text-navy mb-1">{t('login.centre')}</h2>
              <p className="text-sm text-muted mb-5">{t('login.titol')}</p>
              <div className="space-y-2">
                {institucions.map(i => (
                  <button
                    key={i.slug}
                    onClick={() => { setInstitucioSel(i.slug); setError(null) }}
                    className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border border-border hover:border-navy hover:bg-crema text-left transition-colors"
                  >
                    <span className="w-9 h-9 rounded-full bg-navy flex items-center justify-center shrink-0 overflow-hidden">
                      {i.branding?.logo_url
                        ? <img src={i.branding.logo_url} alt={i.nom} className="w-full h-full object-cover" />
                        : <span className="text-white font-bold text-xs">{i.branding?.logo_text || inicials(i.nom)}</span>}
                    </span>
                    <span className="text-sm font-semibold text-dark">{i.nom}</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            // ── Pas 2: usuari + contrasenya (dins de la institució seleccionada) ──
            <>
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-bold text-navy">{t('login.titol')}</h2>
                {potCanviar && !mfaPendent && (
                  <button
                    onClick={() => { setInstitucioSel(null); setError(null); setMfaPendent(false); setCodiMfa('') }}
                    className="flex items-center gap-1 text-xs text-muted hover:text-navy transition-colors"
                  >
                    <ChevronLeft size={14} /> {t('login.centre')}
                  </button>
                )}
              </div>

              {error && (
                <div className="mb-4 px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-5">
                {mfaPendent ? (
                  // Segon factor: codi de l'app d'autenticació.
                  <div>
                    <label className="block text-sm font-medium text-dark mb-1.5">{t('login.codi_mfa')}</label>
                    <input
                      type="text"
                      value={codiMfa}
                      onChange={e => setCodiMfa(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      placeholder="123456"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      autoFocus
                      className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-dark tracking-[0.4em] text-center font-mono placeholder:text-muted focus:outline-none focus:border-navy focus:ring-1 focus:ring-navy/20 transition-colors"
                    />
                    <p className="text-xs text-muted mt-1.5">Introdueix el codi de 6 xifres de la teva app d'autenticació.</p>
                  </div>
                ) : (
                  <>
                    <div>
                      <label className="block text-sm font-medium text-dark mb-1.5">{t('login.usuari')}</label>
                      <input
                        type="text"
                        value={usuari}
                        onChange={e => setUsuari(e.target.value)}
                        placeholder="Ex: marta"
                        autoComplete="username"
                        required
                        className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-dark placeholder:text-muted focus:outline-none focus:border-navy focus:ring-1 focus:ring-navy/20 transition-colors"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-dark mb-1.5">{t('login.contrasenya')}</label>
                      <input
                        type="password"
                        value={contrasenya}
                        onChange={e => setContrasenya(e.target.value)}
                        placeholder="••••••••"
                        autoComplete="current-password"
                        required
                        className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-dark placeholder:text-muted focus:outline-none focus:border-navy focus:ring-1 focus:ring-navy/20 transition-colors"
                      />
                    </div>
                  </>
                )}

                <button
                  type="submit"
                  disabled={loading || (mfaPendent ? codiMfa.length < 6 : (!usuari.trim() || !contrasenya))}
                  className="w-full py-3 bg-navy text-white rounded-lg font-semibold text-sm hover:bg-navy/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      {t('login.carregant')}
                    </span>
                  ) : (
                    t('login.boto')
                  )}
                </button>

                {mfaPendent && (
                  <button
                    type="button"
                    onClick={() => { setMfaPendent(false); setCodiMfa(''); setError(null) }}
                    className="w-full text-xs text-muted hover:text-navy transition-colors"
                  >
                    Tornar
                  </button>
                )}
              </form>

              <div className="mt-6 pt-4 border-t border-border">
                <div className="flex items-center gap-2 text-xs text-muted">
                  <span className="w-2 h-2 rounded-full bg-green shrink-0" />
                  Tot el processament és local. Les teves dades no surten del centre.
                </div>
              </div>
            </>
          )}
        </div>

        <p className="text-center text-xs text-muted mt-4">
          Adeptify · MVP · «IA que protegeix»
        </p>
      </div>
    </div>
  )
}
