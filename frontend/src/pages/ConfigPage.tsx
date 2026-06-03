// ─── Pàgina Configuració: estat del sistema, model i privadesa ───────────────

import { useEffect, useState } from 'react'
import { Server, Cpu, ShieldCheck, Database, Lock, CheckCircle2, XCircle, Languages, Loader2 } from 'lucide-react'
import { useAppStore } from '../store/appStore'
import { fetchSystemStatus, patchIdioma } from '../api/client'
import { MfaPanel } from '../components/config/MfaPanel'
import { useT, type Idioma } from '../i18n'
import { IDIOMES_ADMESOS, NOM_IDIOMA } from '../i18n/catalogs'

function Card({
  title,
  icon,
  children,
}: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-xl border border-border p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sage">{icon}</span>
        <h2 className="font-bold text-navy text-sm uppercase tracking-wide">{title}</h2>
      </div>
      <div className="space-y-2 text-sm">{children}</div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span className="text-dark font-medium text-right">{value}</span>
    </div>
  )
}

export function ConfigPage() {
  const { state, dispatch } = useAppStore()
  const s = state.systemStatus

  useEffect(() => {
    if (!s) {
      void fetchSystemStatus()
        .then(st => dispatch({ type: 'SET_SYSTEM_STATUS', payload: st }))
        .catch(() => undefined)
    }
  }, [s, dispatch])

  return (
    <div className="flex-1 overflow-y-auto bg-fons">
      <div className="max-w-4xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-navy mb-1">Configuració i estat del sistema</h1>
        <p className="text-sm text-muted mb-6">
          Tot s'executa en local. Cap dada surt del centre.
        </p>

        {!s ? (
          <p className="text-muted text-sm">Carregant estat…</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card title="Servidor" icon={<Server size={16} />}>
              <Row
                label="Estat"
                value={
                  s.servidor.actiu ? (
                    <span className="text-green inline-flex items-center gap-1">
                      <CheckCircle2 size={14} /> Actiu
                    </span>
                  ) : (
                    <span className="text-red-600 inline-flex items-center gap-1">
                      <XCircle size={14} /> Inactiu
                    </span>
                  )
                }
              />
              <Row label="Host" value={s.servidor.host} />
              <Row label="Entorn" value={s.servidor.entorn} />
              <Row label="Versió" value={s.versio} />
            </Card>

            <Card title="Model d'IA" icon={<Cpu size={16} />}>
              <Row label="Model" value={s.model.nom} />
              <Row label="Backend" value={s.model.backend} />
              <Row label="Model català" value={s.model.catala} />
            </Card>

            <Card title="Indexació (RAG)" icon={<Database size={16} />}>
              <Row label="Documents indexats" value={s.indexacio.documents} />
              <Row
                label="Al dia"
                value={s.indexacio.al_dia ? 'Sí' : 'No'}
              />
              <Row label="Última indexació" value={s.indexacio.ultima ?? '—'} />
            </Card>

            <Card title="Privadesa" icon={<ShieldCheck size={16} />}>
              <Row
                label="Processament local"
                value={
                  s.privadesa.processament_local ? (
                    <span className="text-green inline-flex items-center gap-1">
                      <Lock size={13} /> Sí
                    </span>
                  ) : (
                    'No'
                  )
                }
              />
              <Row
                label="Crides externes"
                value={
                  <span className={s.privadesa.crides_externes === 0 ? 'text-green' : 'text-red-600'}>
                    {s.privadesa.crides_externes}
                  </span>
                }
              />
              <Row label="Xifratge" value={s.privadesa.xifratge} />
              <Row label="Auditat el" value={s.privadesa.auditat_el} />
            </Card>
          </div>
        )}

        <IdiomaPanel />

        <MfaPanel />

        <div className="mt-6 flex items-center gap-2 bg-navy text-white rounded-xl px-5 py-4">
          <ShieldCheck size={20} className="text-sage shrink-0" />
          <p className="text-sm">
            <strong>IA que protegeix.</strong> Dades al centre · zero crides a APIs externes ·
            sobirania de dades per disseny.
          </p>
        </div>
      </div>
    </div>
  )
}

// Panell de selecció d'idioma. Sincronitza amb el backend (PATCH /api/auth/idioma)
// perquè quan l'usuari torni a entrar trobi la mateixa preferència.
function IdiomaPanel() {
  const { t, idioma, setIdioma } = useT()
  const [desant, setDesant] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  async function tria(nou: Idioma) {
    setIdioma(nou)  // canvi immediat a la UI
    setDesant(true); setMsg(null)
    try {
      await patchIdioma(nou)
      setMsg(t('config.idioma_desat'))
    } catch (e) {
      // No bloquegem la UI: el canvi local persisteix; només avisem si el backend falla.
      setMsg((e as Error).message)
    } finally {
      setDesant(false)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-border p-5 mt-6">
      <div className="flex items-center gap-2 mb-2">
        <Languages size={16} className="text-terra" />
        <h2 className="font-bold text-navy text-sm uppercase tracking-wide">
          {t('config.idioma_titol')}
        </h2>
      </div>
      <p className="text-xs text-muted mb-3">{t('config.idioma_desc')}</p>
      <div className="flex flex-wrap gap-2">
        {IDIOMES_ADMESOS.map(i => (
          <button
            key={i}
            onClick={() => void tria(i as Idioma)}
            disabled={desant}
            aria-pressed={i === idioma}
            className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              i === idioma
                ? 'bg-navy text-white border-navy'
                : 'bg-white text-dark border-border hover:bg-crema'
            }`}
          >
            {NOM_IDIOMA[i as Idioma]} <span className="text-xs opacity-70">({i.toUpperCase()})</span>
          </button>
        ))}
        {desant && <Loader2 size={14} className="animate-spin text-muted ml-2 self-center" />}
        {msg && <span className="text-xs text-muted self-center ml-2">{msg}</span>}
      </div>
    </div>
  )
}
