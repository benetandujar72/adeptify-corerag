// ─── Pàgina d'Ajuda ──────────────────────────────────────────────────────────
// Guies operatives: sobirania física (instància dedicada, Fase 8) i integració
// amb Google Workspace (Fase 4: camps necessaris + passos a Google Cloud).

import type { ReactNode } from 'react'
import { HelpCircle, Server, Cloud, KeyRound, ShieldAlert, Terminal, ListChecks } from 'lucide-react'

function Bloc({ children }: { children: string }) {
  return (
    <pre className="bg-navy/5 text-dark font-mono text-xs leading-relaxed overflow-x-auto p-3 rounded-lg border border-border whitespace-pre">
      {children}
    </pre>
  )
}

function Seccio({
  icon,
  titol,
  subtitol,
  children,
}: {
  icon: ReactNode
  titol: string
  subtitol?: string
  children: ReactNode
}) {
  return (
    <section className="bg-white rounded-xl border border-border p-6 mb-6">
      <h2 className="text-lg font-bold text-navy flex items-center gap-2">
        {icon} {titol}
      </h2>
      {subtitol && <p className="text-sm text-muted mt-1 mb-4">{subtitol}</p>}
      <div className="text-sm text-dark space-y-3 mt-3">{children}</div>
    </section>
  )
}

export function AjudaPage() {
  return (
    <div className="flex-1 overflow-y-auto bg-fons">
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-navy flex items-center gap-2">
            <HelpCircle size={22} className="text-terra" /> Ajuda
          </h1>
          <p className="text-sm text-muted mt-1">
            Guies operatives del sistema. Les seccions tècniques estan pensades per a
            l'equip d'administració/TIC del centre.
          </p>
        </div>

        {/* Índex */}
        <div className="bg-white rounded-xl border border-border p-4 mb-6 text-sm">
          <div className="font-semibold text-navy mb-2">Continguts</div>
          <ul className="list-disc list-inside text-muted space-y-1">
            <li><a href="#sobirania" className="text-navy hover:underline">Sobirania física: instància dedicada per a un centre (Fase 8)</a></li>
            <li><a href="#google" className="text-navy hover:underline">Integració amb Google Workspace (Fase 4): camps i passos</a></li>
          </ul>
        </div>

        {/* ─── Fase 8: sobirania física ─────────────────────────────────────── */}
        <div id="sobirania" />
        <Seccio
          icon={<Server size={18} className="text-terra" />}
          titol="Sobirania física: instància dedicada (Fase 8)"
          subtitol="Per a un centre que vulgui el seu propi desplegament aïllat: base de dades, secret i ports PROPIS, sense compartir res amb altres institucions."
        >
          <p>
            El sistema és <strong>multi-tenant</strong>: per defecte, diverses institucions
            conviuen al mateix desplegament, amb les dades aïllades per institució. Si un
            centre vol <strong>sobirania física</strong> (el seu maquinari i la seva base de
            dades), s'exporta a una <strong>instància dedicada autònoma</strong>.
          </p>

          <p className="font-semibold text-navy">1) Generar l'export (al desplegament compartit)</p>
          <Bloc>{`docker compose -f docker-compose.yml -f docker-compose.override.yml \\
  exec -T backend python -m scripts.export_institucio <slug> --port-base 9000

# Extreure la carpeta generada cap a l'amfitrió:
docker compose -f docker-compose.yml -f docker-compose.override.yml \\
  cp backend:/app/data/exports/<slug> ./exports/<slug>`}</Bloc>
          <p className="text-muted text-xs">
            Genera <code>exports/&lt;slug&gt;/</code> amb <code>.env</code> (ports únics +
            <code> JWT_SECRET</code> nou + credencials de BD pròpies), <code>docker-compose.yml</code>
            (stack aïllat), <code>bundle.json</code> (NOMÉS les dades d'aquell centre: institució,
            usuaris amb la contrasenya, documents <em>amb els seus embeddings</em>, grups/alumnes,
            matrícula i assistència) i un <code>README.md</code>.
          </p>

          <p className="font-semibold text-navy">2) Desplegar al servidor del centre</p>
          <Bloc>{`# Copia tot el repositori al servidor i situa l'export a exports/<slug>/
cd exports/<slug>
docker compose up -d --build

# Quan la BD estigui sana, importa les dades del centre:
docker compose exec -T backend python -m scripts.import_bundle /data/bundle.json`}</Bloc>
          <p>
            Obre el dashboard a <code>http://localhost:&lt;FRONTEND_PORT&gt;</code> (per defecte
            9001). Els usuaris <strong>mantenen la seva contrasenya</strong> (s'exporta el hash, mai
            en clar); com que el <code>JWT_SECRET</code> és nou, cal tornar a iniciar sessió.
          </p>

          <p className="font-semibold text-navy">Notes</p>
          <ul className="list-disc list-inside text-muted space-y-1">
            <li><strong>Inferència local</strong>: el servidor ha de tenir Ollama en marxa (cap crida a APIs comercials).</li>
            <li><strong>Sense GPU</strong>: treu el bloc <code>deploy:</code> del servei <code>backend</code> i posa <code>EMBEDDER_DEVICE=cpu</code> i <code>RERANKER_DEVICE=cpu</code> al <code>.env</code>.</li>
            <li>Els documents s'exporten <strong>amb els embeddings</strong> → no cal re-indexar.</li>
            <li>No s'exporten converses ni auditoria (logs operatius): la instància comença neta.</li>
          </ul>
        </Seccio>

        {/* ─── Fase 4: integració Google ────────────────────────────────────── */}
        <div id="google" />
        <Seccio
          icon={<Cloud size={18} className="text-terra" />}
          titol="Integració amb Google Workspace (Fase 4)"
          subtitol="Lectura de carpetes de Drive aprovades, esborranys de Gmail i calendaris del centre, passant SEMPRE per la passarel·la de privacitat. La inferència segueix sent local."
        >
          <div className="flex items-start gap-2 bg-terra/10 border border-terra/30 rounded-lg p-3 text-xs text-dark">
            <ShieldAlert size={16} className="text-terra shrink-0 mt-0.5" />
            <span>
              <strong>Abans d'activar res</strong>: cal CET (contracte d'encàrrec) centre↔Adeptify,
              actualitzar el RAT i l'EIPD, i verificar la <strong>residència UE</strong> del tenant.
              Vegeu la nota legal del projecte (<code>docs/11_FASE4_NOTA_LEGAL.md</code>). La
              passarel·la de privadesa i el connector de <strong>Drive (només lectura)</strong> ja estan
              implementats; només cal posar-hi credencials reals del centre. Gmail (esborranys) i Calendar resten pendents.
            </span>
          </div>

          <p className="font-semibold text-navy flex items-center gap-1.5">
            <KeyRound size={15} /> Camps necessaris (al <code>.env</code> / secret muntat)
          </p>
          <p className="text-xs text-muted">
            Recomanat per a un backend auto-allotjat: <strong>compte de servei (service account)
            amb delegació a tot el domini</strong> (server-to-server). S'inclou també l'alternativa
            OAuth.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border border-border rounded-lg">
              <thead>
                <tr className="bg-crema text-muted text-left">
                  <th className="px-3 py-2 font-semibold">Camp (.env)</th>
                  <th className="px-3 py-2 font-semibold">Descripció</th>
                  <th className="px-3 py-2 font-semibold">On s'obté</th>
                </tr>
              </thead>
              <tbody className="text-dark">
                {[
                  ['GOOGLE_AUTH_MODE', "service_account (recomanat) o oauth", 'Decisió de disseny'],
                  ['GOOGLE_PROJECT_ID', 'ID del projecte de Google Cloud', 'Google Cloud Console'],
                  ['GOOGLE_WORKSPACE_DOMAIN', 'Domini del centre (ex. escola.cat)', 'El vostre domini'],
                  ['GOOGLE_SA_JSON_PATH', 'Ruta al fitxer de clau JSON del compte de servei (muntat com a secret)', 'En crear la clau del SA'],
                  ['GOOGLE_SA_SUBJECT', "Usuari del domini a impersonar (delegació)", 'Admin de Workspace'],
                  ['GOOGLE_CLIENT_ID', '(alternativa OAuth) ID de client OAuth 2.0', 'Credencials OAuth'],
                  ['GOOGLE_CLIENT_SECRET', '(alternativa OAuth) secret de client', 'Credencials OAuth'],
                  ['GOOGLE_REDIRECT_URI', '(OAuth) URI de retorn del flux', 'El definiu vosaltres'],
                  ['GOOGLE_SCOPES', 'Àmbits mínims (vegeu sota)', 'Fixos'],
                  ['GOOGLE_DRIVE_FOLDERS', 'IDs de carpetes aprovades (allow-list, separats per comes)', "De la URL de Drive"],
                  ['GOOGLE_CALENDAR_IDS', 'IDs de calendaris aprovats', 'Configuració de Calendar'],
                  ['GOOGLE_GMAIL_SENDER', 'Adreça remitent dels esborranys', 'Bústia del centre'],
                ].map(([c, d, o]) => (
                  <tr key={c} className="border-t border-border">
                    <td className="px-3 py-1.5 font-mono text-navy whitespace-nowrap">{c}</td>
                    <td className="px-3 py-1.5">{d}</td>
                    <td className="px-3 py-1.5 text-muted">{o}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="font-semibold text-navy">Àmbits (scopes) mínims</p>
          <Bloc>{`https://www.googleapis.com/auth/drive.readonly      # només lectura de Drive
https://www.googleapis.com/auth/gmail.compose       # només crear esborranys (mai enviar)
https://www.googleapis.com/auth/calendar            # calendaris del centre`}</Bloc>

          <p className="font-semibold text-navy flex items-center gap-1.5">
            <ListChecks size={15} /> Passos a Google Cloud Console
          </p>
          <ol className="list-decimal list-inside text-sm space-y-1.5">
            <li>A <code>console.cloud.google.com</code>, crea o selecciona un <strong>projecte</strong> i anota'n el <strong>Project ID</strong>.</li>
            <li><strong>APIs i serveis → Biblioteca</strong>: habilita <strong>Google Drive API</strong>, <strong>Gmail API</strong> i <strong>Google Calendar API</strong>.</li>
            <li><strong>Pantalla de consentiment OAuth</strong>: tipus <strong>Intern</strong> (només usuaris del domini del centre).</li>
            <li>
              <strong>Credencials</strong>:
              <ul className="list-disc list-inside ml-5 mt-1 text-muted">
                <li><strong>Compte de servei</strong> (recomanat): crea'l → pestanya <em>Claus</em> → <em>Afegeix clau → JSON</em> → desa el fitxer com a <strong>secret</strong> (mai al repositori).</li>
                <li><strong>OAuth</strong> (alternativa): crea un <em>ID de client OAuth</em> (aplicació web), afegeix el <em>Redirect URI</em> i anota <code>client_id</code> + <code>client_secret</code>.</li>
              </ul>
            </li>
            <li>
              <strong>Delegació a tot el domini</strong> (per al compte de servei, per accedir a
              Gmail/Drive del domini): activa-la al SA i anota'n el <strong>Client ID</strong> (numèric).
            </li>
            <li>
              A <strong>admin.google.com</strong> (Admin de Workspace) → <strong>Seguretat → Controls
              d'API → Delegació a tot el domini</strong> → <em>Afegeix nou</em>: posa el <strong>Client
              ID</strong> del SA i els <strong>scopes</strong> (separats per comes).
            </li>
            <li>Comparteix <strong>les carpetes concretes</strong> de Drive amb el compte de servei (o l'usuari impersonat), <strong>només lectura</strong>. Anota'n els IDs (a la URL de la carpeta).</li>
            <li>Posa tots els valors al <code>.env</code> / secret muntat i defineix l'<strong>allow-list</strong> (<code>GOOGLE_DRIVE_FOLDERS</code>, <code>GOOGLE_CALENDAR_IDS</code>).</li>
            <li>Activa el connector: tota crida passa per la <strong>passarel·la de privacitat</strong> (allow-list + RBAC + auditoria). Verifica a <strong>Configuració</strong> que <code>crides_externes</code> (a LLM) segueix sent <strong>0</strong>; les crides a Google es comptabilitzen a part.</li>
          </ol>

          <div className="flex items-start gap-2 bg-navy/5 border border-border rounded-lg p-3 text-xs text-muted">
            <Terminal size={15} className="text-navy shrink-0 mt-0.5" />
            <span>
              <strong>Operacions permeses</strong>: Drive = només lectura de carpetes aprovades ·
              Gmail = només crear esborranys (l'enviament és sempre humà) · Calendar = lectura +
              creació en calendaris del centre. Qualsevol altra operació queda bloquejada per la
              passarel·la.
            </span>
          </div>
        </Seccio>
      </div>
    </div>
  )
}
