// ─── Client API centralitzat (API_CONTRACT.md) ───────────────────────────────
// Llegeix la base URL de VITE_API_BASE_URL (variable d'entorn Vite).
// Tota petició autenticada inclou el token de localStorage.

import type {
  Agent,
  AlertaAbsentisme,
  AlumneDomini,
  AuditEntry,
  AuthResponse,
  Avaluacio,
  Butlleti,
  CalendarEvent,
  CatalegSkills,
  CompartirCataleg,
  CompartirResultat,
  MetricaSkill,
  PlantillaSkill,
  ChecklistItem,
  Competencia,
  Conversa,
  CopilotContingut,
  CopilotEvidencia,
  Criteri,
  DocumentEstat,
  DriveFile,
  EsborranySkill,
  EstatButlleti,
  EstatRegistre,
  Font,
  GmailMessage,
  GmailThread,
  GoogleIntegracio,
  GrupClasse,
  ImportReport,
  Institucio,
  InstitucioPublica,
  IntegracioTestResult,
  Justificant,
  LmsIntegracio,
  LmsMaterial,
  MapeigCompetencial,
  MeResponse,
  MfaSetup,
  Missatge,
  MoodleBackupBlueprint,
  Notificacio,
  OnboardingAdminItem,
  OnboardingStatus,
  Qualificacio,
  Quota,
  Recurs,
  RecursSuggerit,
  RegistreAssistencia,
  ResumAssistencia,
  Rubrica,
  Skill,
  SollicitudMatricula,
  Tasca,
  Trimestre,
  SystemStatus,
  User,
} from '../types'

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api'

function getToken(): string | null {
  return localStorage.getItem('patufet_token')
}

function authHeaders(): HeadersInit {
  const token = getToken()
  return token
    ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
    : { 'Content-Type': 'application/json' }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `Error HTTP ${res.status}`
    try {
      const body = await res.json()
      msg = body?.error?.missatge ?? msg
    } catch {
      // ignora errors de parse
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export async function login(
  usuari: string,
  contrasenya: string,
  institucio?: string,
  codiMfa?: string,
): Promise<AuthResponse> {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      usuari, contrasenya,
      institucio: institucio || undefined,
      codi_mfa: codiMfa || undefined,
    }),
  })
  return handleResponse<AuthResponse>(res)
}

// ─── MFA / 2FA (l'usuari gestiona el seu propi segon factor) ──────────────────

export async function fetchMfaEstat(): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/auth/mfa/estat`, { headers: authHeaders() })
  const d = await handleResponse<{ actiu: boolean }>(res)
  return d.actiu
}

export async function setupMfa(): Promise<MfaSetup> {
  const res = await fetch(`${BASE_URL}/auth/mfa/setup`, { method: 'POST', headers: authHeaders() })
  return handleResponse<MfaSetup>(res)
}

export async function activarMfa(codi: string): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/auth/mfa/activar`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify({ codi }),
  })
  const d = await handleResponse<{ actiu: boolean }>(res)
  return d.actiu
}

export async function desactivarMfa(): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/auth/mfa/desactivar`, { method: 'POST', headers: authHeaders() })
  const d = await handleResponse<{ actiu: boolean }>(res)
  return d.actiu
}

/** Llista MÍNIMA d'institucions actives per a la pantalla de selecció (pre-login, públic). */
export async function fetchInstitucionsPubliques(): Promise<InstitucioPublica[]> {
  const res = await fetch(`${BASE_URL}/auth/institucions`)
  const d = await handleResponse<{ institucions: InstitucioPublica[] }>(res)
  return d.institucions
}

// ─── Usuaris per institució (admin de centre = direcció; scoped) ──────────────

export async function fetchInstitucioUsers(): Promise<User[]> {
  const res = await fetch(`${BASE_URL}/institucio/users`, { headers: authHeaders() })
  const d = await handleResponse<{ users: User[] }>(res)
  return d.users
}

export async function createInstitucioUser(input: {
  username: string
  contrasenya: string
  rol: string
  nom?: string
  email?: string
}): Promise<User> {
  const res = await fetch(`${BASE_URL}/institucio/users`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<User>(res)
}

export async function updateInstitucioUser(
  username: string,
  canvis: { rol?: string; nom?: string; email?: string; actiu?: boolean; contrasenya?: string },
): Promise<User> {
  const res = await fetch(`${BASE_URL}/institucio/users/${encodeURIComponent(username)}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<User>(res)
}

export async function deleteInstitucioUser(username: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/institucio/users/${encodeURIComponent(username)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
}

// ─── Administració (superadmin) ───────────────────────────────────────────────

export async function fetchUsers(): Promise<User[]> {
  const res = await fetch(`${BASE_URL}/admin/users`, { headers: authHeaders() })
  const data = await handleResponse<{ users: User[] }>(res)
  return data.users
}

export async function createUser(u: {
  username: string
  contrasenya: string
  rol: string
  nom?: string
  email?: string
  actiu?: boolean
  institucio_id?: string
}): Promise<User> {
  const res = await fetch(`${BASE_URL}/admin/users`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(u),
  })
  return handleResponse<User>(res)
}

export async function updateUser(
  username: string,
  canvis: { rol?: string; nom?: string; email?: string; actiu?: boolean; contrasenya?: string },
  institucio?: string,
): Promise<User> {
  const q = institucio ? `?institucio=${encodeURIComponent(institucio)}` : ''
  const res = await fetch(`${BASE_URL}/admin/users/${encodeURIComponent(username)}${q}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<User>(res)
}

export async function deleteUser(username: string, institucio?: string): Promise<void> {
  const q = institucio ? `?institucio=${encodeURIComponent(institucio)}` : ''
  const res = await fetch(`${BASE_URL}/admin/users/${encodeURIComponent(username)}${q}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
}

export async function fetchAudit(
  params: { limit?: number; usuari?: string; accio?: string } = {},
): Promise<{ entrades: AuditEntry[]; total: number }> {
  const q = new URLSearchParams()
  if (params.limit) q.set('limit', String(params.limit))
  if (params.usuari) q.set('usuari', params.usuari)
  if (params.accio) q.set('accio', params.accio)
  const res = await fetch(`${BASE_URL}/admin/audit?${q.toString()}`, { headers: authHeaders() })
  return handleResponse(res)
}

export async function fetchMe(): Promise<MeResponse> {
  const res = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() })
  return handleResponse<MeResponse>(res)
}

export async function patchIdioma(idioma: string): Promise<MeResponse> {
  const res = await fetch(`${BASE_URL}/auth/idioma`, {
    method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ idioma }),
  })
  return handleResponse<MeResponse>(res)
}

// ─── Institucions (multi-tenant) ──────────────────────────────────────────────

/** Institució de l'usuari autenticat (branding + config). Accessible a tots els rols. */
export async function fetchMyInstitucio(): Promise<Institucio> {
  const res = await fetch(`${BASE_URL}/institucio/actual`, { headers: authHeaders() })
  return handleResponse<Institucio>(res)
}

/** Llista totes les institucions (NOMÉS superadmin). */
export async function fetchInstitucions(): Promise<Institucio[]> {
  const res = await fetch(`${BASE_URL}/admin/institucions`, { headers: authHeaders() })
  const data = await handleResponse<{ institucions: Institucio[] }>(res)
  return data.institucions
}

export async function createInstitucio(i: {
  slug: string
  nom: string
  config?: Institucio['config']
  branding?: Institucio['branding']
}): Promise<Institucio> {
  const res = await fetch(`${BASE_URL}/admin/institucions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(i),
  })
  return handleResponse<Institucio>(res)
}

export async function updateInstitucio(
  slug: string,
  canvis: {
    nom?: string
    actiu?: boolean
    config?: Institucio['config']
    branding?: Institucio['branding']
  },
): Promise<Institucio> {
  const res = await fetch(`${BASE_URL}/admin/institucions/${encodeURIComponent(slug)}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Institucio>(res)
}

export async function deleteInstitucio(slug: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/admin/institucions/${encodeURIComponent(slug)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok && res.status !== 204) {
    let msg = `No s'ha pogut esborrar (HTTP ${res.status})`
    try {
      const body = await res.json()
      msg = body?.detail ?? body?.error?.missatge ?? msg
    } catch {
      // ignora
    }
    throw new Error(msg)
  }
}

// ─── Agents i sistema ─────────────────────────────────────────────────────────

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${BASE_URL}/agents`, { headers: authHeaders() })
  const data = await handleResponse<{ agents: Agent[] }>(res)
  return data.agents
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${BASE_URL}/system/status`, { headers: authHeaders() })
  return handleResponse<SystemStatus>(res)
}

// ─── Estudi d'Skills (agents personalitzats · direcció) ───────────────────────

export interface SkillInput {
  nom: string
  system_prompt: string
  descripcio?: string
  color?: string
  paraules_clau?: string[]
  rols_permesos?: string[]
  tools?: string[]
  coneixement?: string[]
  actiu?: boolean
}

export async function fetchSkillsCataleg(): Promise<CatalegSkills> {
  const res = await fetch(`${BASE_URL}/institucio/skills/cataleg`, { headers: authHeaders() })
  return handleResponse<CatalegSkills>(res)
}

export async function fetchSkills(): Promise<Skill[]> {
  const res = await fetch(`${BASE_URL}/institucio/skills`, { headers: authHeaders() })
  const d = await handleResponse<{ skills: Skill[] }>(res)
  return d.skills
}

/** Generació autònoma de l'esborrany (NL → prompt). NO desa res. */
export async function generaEsborranySkill(input: {
  descripcio: string
  rols_permesos?: string[]
  tools?: string[]
  usa_batch?: boolean
}): Promise<EsborranySkill> {
  const res = await fetch(`${BASE_URL}/institucio/skills/genera-esborrany`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<EsborranySkill>(res)
}

/** Prova un esborrany ABANS d'activar-lo (P3). Resposta efímera; no desa res. */
export async function provaSkill(input: {
  message: string
  system_prompt: string
  nom?: string
  rols_permesos?: string[]
  tools?: string[]
  coneixement?: string[]
}): Promise<{ resposta: string; fonts: Font[] }> {
  const res = await fetch(`${BASE_URL}/institucio/skills/prova`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<{ resposta: string; fonts: Font[] }>(res)
}

export async function createSkill(input: SkillInput): Promise<Skill> {
  const res = await fetch(`${BASE_URL}/institucio/skills`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Skill>(res)
}

export async function updateSkill(id: string, canvis: Partial<SkillInput>): Promise<Skill> {
  const res = await fetch(`${BASE_URL}/institucio/skills/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Skill>(res)
}

export async function deleteSkill(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/institucio/skills/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
}

// ─── Estudi d'Skills · P4 (plantilles, mètriques, compartició) ───────────────

export async function fetchSkillPlantilles(): Promise<PlantillaSkill[]> {
  const res = await fetch(`${BASE_URL}/institucio/skills/plantilles`, { headers: authHeaders() })
  const d = await handleResponse<{ plantilles: PlantillaSkill[] }>(res)
  return d.plantilles
}

export async function fetchSkillMetriques(): Promise<MetricaSkill[]> {
  const res = await fetch(`${BASE_URL}/institucio/skills/metriques`, { headers: authHeaders() })
  const d = await handleResponse<{ metriques: MetricaSkill[] }>(res)
  return d.metriques
}

/** Catàleg de compartició (NOMÉS superadmin): tots els skills + centres destí. */
export async function fetchCompartirCataleg(): Promise<CompartirCataleg> {
  const res = await fetch(`${BASE_URL}/institucio/skills/compartir/cataleg`, { headers: authHeaders() })
  return handleResponse<CompartirCataleg>(res)
}

/** Copia un skill a un o més centres (NOMÉS superadmin). Retorna el resultat per destí. */
export async function comparteixSkill(
  id: string,
  destinacions: string[],
): Promise<CompartirResultat[]> {
  const res = await fetch(`${BASE_URL}/institucio/skills/${encodeURIComponent(id)}/comparteix`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ destinacions }),
  })
  const d = await handleResponse<{ resultats: CompartirResultat[] }>(res)
  return d.resultats
}

// ─── Registre de recursos de documentació (F2 · direcció) ─────────────────────

export interface RecursInput {
  titol: string
  descripcio?: string
  tipus?: string // url | document
  url?: string | null
  doc_id?: string | null
  etiquetes?: string[]
  versio?: string
  font_oficial?: string
  vigent?: boolean
}

export async function fetchRecursos(): Promise<Recurs[]> {
  const res = await fetch(`${BASE_URL}/institucio/recursos`, { headers: authHeaders() })
  const d = await handleResponse<{ recursos: Recurs[] }>(res)
  return d.recursos
}

export async function createRecurs(input: RecursInput): Promise<Recurs> {
  const res = await fetch(`${BASE_URL}/institucio/recursos`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Recurs>(res)
}

export async function updateRecurs(id: string, canvis: Partial<RecursInput>): Promise<Recurs> {
  const res = await fetch(`${BASE_URL}/institucio/recursos/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Recurs>(res)
}

export async function deleteRecurs(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/institucio/recursos/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
}

// ─── Documents i ingesta ──────────────────────────────────────────────────────

export async function deleteDocument(doc_id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/documents/${encodeURIComponent(doc_id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok && res.status !== 204) {
    throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
  }
}

export async function fetchDocuments(): Promise<DocumentEstat[]> {
  const res = await fetch(`${BASE_URL}/documents`, { headers: authHeaders() })
  const data = await handleResponse<{ documents: DocumentEstat[] }>(res)
  return data.documents
}

/** Obre el fitxer ORIGINAL d'una font citada (F1). Es baixa amb el token a la
 *  capçalera (mai a la URL) i s'obre en una pestanya nova com a blob. */
export async function obreFontDocument(doc_id: string): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}/documents/${encodeURIComponent(doc_id)}/descarrega`, {
    headers,
  })
  if (!res.ok) {
    let msg = `No s'ha pogut obrir el document (HTTP ${res.status})`
    try {
      const b = await res.json()
      msg = b?.detail ?? b?.error?.missatge ?? msg
    } catch {
      /* ignora */
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** Descarrega el butlletí com a PDF (blob amb el token al header; mai a la URL).
 *  Força la baixada amb una àncora `download` (millor que obrir pestanya per a un fitxer). */
export async function descarregaButlletiPdf(butlleti_id: string, filename = 'butlleti.pdf'): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}/avaluacio/butlletins/${encodeURIComponent(butlleti_id)}/pdf`, { headers })
  if (!res.ok) {
    let msg = `No s'ha pogut descarregar el PDF (HTTP ${res.status})`
    try {
      const b = await res.json()
      msg = b?.detail ?? b?.error?.missatge ?? msg
    } catch {
      /* ignora */
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export interface IngestResult {
  job_id: string
  estat: string
}

/** Puja un fitxer i l'ingereix (multipart). No s'hi posa Content-Type: el
 *  navegador hi afegeix el boundary automàticament. */
export async function uploadDocument(file: File): Promise<IngestResult> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const fd = new FormData()
  fd.append('fitxer', file)

  const res = await fetch(`${BASE_URL}/ingest`, {
    method: 'POST',
    headers,
    body: fd,
  })
  return handleResponse<IngestResult>(res)
}

// ─── Converses ────────────────────────────────────────────────────────────────

export async function fetchConversations(): Promise<Conversa[]> {
  const res = await fetch(`${BASE_URL}/conversations`, { headers: authHeaders() })
  const data = await handleResponse<{ conversations: Conversa[] }>(res)
  return data.conversations
}

export async function fetchConversation(
  id: string,
): Promise<{ conversation: Conversa; messages: Missatge[] }> {
  const res = await fetch(`${BASE_URL}/conversations/${id}`, { headers: authHeaders() })
  return handleResponse(res)
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`${BASE_URL}/conversations/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
}

// ─── Feedback ─────────────────────────────────────────────────────────────────

export async function postFeedback(
  message_id: string,
  valor: 'util' | 'millorar',
  comentari?: string,
): Promise<void> {
  await fetch(`${BASE_URL}/feedback`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message_id, valor, comentari }),
  })
}

// ─── Veu: transcripció (STT local) ───────────────────────────────────────────

export async function transcribeAudio(blob: Blob): Promise<string> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const fd = new FormData()
  fd.append('fitxer', blob, 'dictat.webm')
  const res = await fetch(`${BASE_URL}/transcribe`, { method: 'POST', headers, body: fd })
  const data = await handleResponse<{ text: string }>(res)
  return data.text
}

// ─── Matrícula (Fase 3 — tràmit) ──────────────────────────────────────────────

export interface SollicitudInput {
  alumne_nom: string
  alumne_cognoms: string
  data_naixement?: string
  tutor_nom: string
  tutor_email?: string
  tutor_telefon?: string
  nivell_sollicitat: string
  curs_academic?: string
  germans_al_centre?: boolean
  observacions?: string
  consentiment_dades: boolean
  presentar?: boolean
}

export async function createSollicitud(input: SollicitudInput): Promise<SollicitudMatricula> {
  const res = await fetch(`${BASE_URL}/matricula/sollicituds`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<SollicitudMatricula>(res)
}

export async function fetchSollicituds(): Promise<SollicitudMatricula[]> {
  const res = await fetch(`${BASE_URL}/matricula/sollicituds`, { headers: authHeaders() })
  const data = await handleResponse<{ sollicituds: SollicitudMatricula[] }>(res)
  return data.sollicituds
}

export async function patchSollicitud(
  id: string,
  canvis: Partial<SollicitudInput> & { estat?: string; motiu?: string },
): Promise<SollicitudMatricula> {
  const res = await fetch(`${BASE_URL}/matricula/sollicituds/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<SollicitudMatricula>(res)
}

export async function fetchChecklist(): Promise<ChecklistItem[]> {
  const res = await fetch(`${BASE_URL}/matricula/checklist`, { headers: authHeaders() })
  const data = await handleResponse<{ items: ChecklistItem[] }>(res)
  return data.items
}

// ─── Integracions externes (Fase 4 — Google) ─────────────────────────────────

export async function fetchGoogleIntegracio(): Promise<GoogleIntegracio> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/google`, { headers: authHeaders() })
  return handleResponse<GoogleIntegracio>(res)
}

export interface GoogleIntegracioInput {
  actiu?: boolean
  auth_mode?: string
  project_id?: string
  workspace_domain?: string
  sa_subject?: string
  client_id?: string
  redirect_uri?: string
  scopes?: string[]
  drive_folders?: string[]
  calendar_ids?: string[]
  gmail_sender?: string
  gmail_comptes?: string[]
  sa_json?: string
  client_secret?: string
}

export interface LmsIntegracioInput {
  actiu?: boolean
  moodle_actiu?: boolean
  moodle_base_url?: string
  moodle_course_ids?: string[]
  moodle_token?: string
  classroom_actiu?: boolean
  classroom_course_ids?: string[]
  ingesta_entregues?: boolean
}

export async function updateGoogleIntegracio(
  canvis: GoogleIntegracioInput,
): Promise<GoogleIntegracio> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/google`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<GoogleIntegracio>(res)
}

export async function testGoogleIntegracio(): Promise<IntegracioTestResult> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/google/test`, {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<IntegracioTestResult>(res)
}

export async function fetchLmsIntegracio(): Promise<LmsIntegracio> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/lms`, { headers: authHeaders() })
  return handleResponse<LmsIntegracio>(res)
}

export async function updateLmsIntegracio(canvis: LmsIntegracioInput): Promise<LmsIntegracio> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/lms`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<LmsIntegracio>(res)
}

export async function testLmsIntegracio(): Promise<IntegracioTestResult> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/lms/test`, {
    method: 'POST',
    headers: authHeaders(),
  })
  return handleResponse<IntegracioTestResult>(res)
}

export async function fetchLmsMaterials(connector: 'moodle' | 'classroom', courseId: string): Promise<LmsMaterial[]> {
  const res = await fetch(
    `${BASE_URL}/institucio/integracions/lms/materials?connector=${encodeURIComponent(connector)}&course_id=${encodeURIComponent(courseId)}`,
    { headers: authHeaders() },
  )
  const d = await handleResponse<{ materials: LmsMaterial[] }>(res)
  return d.materials
}

export async function ingestLmsMaterial(input: {
  connector: 'moodle' | 'classroom'
  course_id: string
  material_id: string
}): Promise<{ filename: string; chunks: number; documents: number }> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/lms/ingest`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse(res)
}

export async function analyzeMoodleBackup(file: File): Promise<MoodleBackupBlueprint> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const fd = new FormData()
  fd.append('fitxer', file)
  const res = await fetch(`${BASE_URL}/moodle/backup/analyze`, {
    method: 'POST',
    headers,
    body: fd,
  })
  const data = await handleResponse<{ blueprint: MoodleBackupBlueprint }>(res)
  return data.blueprint
}

export async function suggestMoodleCoursePlan(file: File, brief: string): Promise<{
  blueprint: MoodleBackupBlueprint
  plan: Record<string, unknown>
}> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const fd = new FormData()
  fd.append('fitxer', file)
  fd.append('brief', brief)
  const res = await fetch(`${BASE_URL}/moodle/backup/suggest-plan`, {
    method: 'POST',
    headers,
    body: fd,
  })
  return handleResponse(res)
}

export async function buildMoodleBackup(file: File, plan: Record<string, unknown>): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const fd = new FormData()
  fd.append('fitxer', file)
  fd.append('plan_json', JSON.stringify(plan))
  const res = await fetch(`${BASE_URL}/moodle/backup/build`, {
    method: 'POST',
    headers,
    body: fd,
  })
  if (!res.ok) {
    let msg = `No s'ha pogut generar el curs Moodle (HTTP ${res.status})`
    try {
      const body = await res.json()
      msg = body?.error?.missatge ?? body?.detail ?? msg
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') ?? ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] ?? 'moodle-course.mbz'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export async function ingestMoodleBackupToRag(file: File): Promise<{
  ok: boolean
  filename: string
  documents: number
  chunks: number
  blueprint: MoodleBackupBlueprint
}> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const fd = new FormData()
  fd.append('fitxer', file)
  const res = await fetch(`${BASE_URL}/moodle/backup/ingest`, {
    method: 'POST',
    headers,
    body: fd,
  })
  return handleResponse(res)
}

// ─── Onboarding dinàmic ─────────────────────────────────────────────────────

export async function fetchOnboardingMe(perfil?: string): Promise<OnboardingStatus> {
  const suffix = perfil ? `?perfil=${encodeURIComponent(perfil)}` : ''
  const res = await fetch(`${BASE_URL}/onboarding/me${suffix}`, { headers: authHeaders() })
  return handleResponse<OnboardingStatus>(res)
}

export async function startOnboarding(input?: {
  perfil?: string
  reinicia?: boolean
}): Promise<OnboardingStatus> {
  const res = await fetch(`${BASE_URL}/onboarding/start`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input ?? {}),
  })
  return handleResponse<OnboardingStatus>(res)
}

export async function answerOnboarding(input: {
  sessio_id: string
  step_id: string
  resposta: Record<string, unknown>
  docs_revisats?: string[]
}): Promise<OnboardingStatus> {
  const res = await fetch(`${BASE_URL}/onboarding/answer`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<OnboardingStatus>(res)
}

export async function fetchOnboardingAdmin(): Promise<OnboardingAdminItem[]> {
  const res = await fetch(`${BASE_URL}/onboarding/admin/sessions`, { headers: authHeaders() })
  const data = await handleResponse<{ sessions: OnboardingAdminItem[] }>(res)
  return data.sessions
}

export async function fetchDriveFiles(folderId: string): Promise<DriveFile[]> {
  const res = await fetch(
    `${BASE_URL}/institucio/integracions/google/drive/files?folder_id=${encodeURIComponent(folderId)}`,
    { headers: authHeaders() },
  )
  const d = await handleResponse<{ fitxers: DriveFile[] }>(res)
  return d.fitxers
}

export async function ingestDriveFile(
  fileId: string,
  folderId: string,
): Promise<{ filename: string; chunks: number; documents: number }> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/google/drive/ingest`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ file_id: fileId, folder_id: folderId }),
  })
  return handleResponse(res)
}

export async function fetchGmailThreads(compte: string, max = 15): Promise<GmailThread[]> {
  const res = await fetch(
    `${BASE_URL}/institucio/integracions/google/gmail/threads?compte=${encodeURIComponent(compte)}&max=${max}`,
    { headers: authHeaders() },
  )
  const d = await handleResponse<{ fils: GmailThread[] }>(res)
  return d.fils
}

export async function fetchGmailMessage(messageId: string, compte: string): Promise<GmailMessage> {
  const res = await fetch(
    `${BASE_URL}/institucio/integracions/google/gmail/messages/${encodeURIComponent(messageId)}?compte=${encodeURIComponent(compte)}`,
    { headers: authHeaders() },
  )
  return handleResponse<GmailMessage>(res)
}

export async function createGmailDraft(input: {
  to: string
  subject: string
  body: string
  compte?: string
}): Promise<{ ok: boolean; draft_id: string }> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/google/gmail/draft`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse(res)
}

export async function fetchCalendarEvents(calendarId: string, dies = 30): Promise<CalendarEvent[]> {
  const res = await fetch(
    `${BASE_URL}/institucio/integracions/google/calendar/events?calendar_id=${encodeURIComponent(calendarId)}&dies=${dies}`,
    { headers: authHeaders() },
  )
  const d = await handleResponse<{ esdeveniments: CalendarEvent[] }>(res)
  return d.esdeveniments
}

export async function createCalendarEvent(input: {
  calendar_id: string
  titol: string
  inici: string
  fi: string
  descripcio?: string
}): Promise<{ ok: boolean; event_id: string }> {
  const res = await fetch(`${BASE_URL}/institucio/integracions/google/calendar/events`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse(res)
}

// ─── Assistència (Fase 3.3) ───────────────────────────────────────────────────

export async function fetchGrups(): Promise<GrupClasse[]> {
  const res = await fetch(`${BASE_URL}/assistencia/grups`, { headers: authHeaders() })
  const data = await handleResponse<{ grups: GrupClasse[] }>(res)
  return data.grups
}

export async function fetchMeusAlumnes(): Promise<AlumneDomini[]> {
  const res = await fetch(`${BASE_URL}/assistencia/alumnes`, { headers: authHeaders() })
  const data = await handleResponse<{ alumnes: AlumneDomini[] }>(res)
  return data.alumnes
}

export async function fetchAlumnesGrup(grupId: string): Promise<AlumneDomini[]> {
  const res = await fetch(`${BASE_URL}/assistencia/grups/${encodeURIComponent(grupId)}/alumnes`, {
    headers: authHeaders(),
  })
  const data = await handleResponse<{ alumnes: AlumneDomini[] }>(res)
  return data.alumnes
}

export async function patchAlumneNee(
  alumneId: string,
  cos: { nee?: boolean; pla_individualitzat?: boolean; observacions_nee?: string | null },
): Promise<AlumneDomini> {
  const res = await fetch(
    `${BASE_URL}/assistencia/alumnes/${encodeURIComponent(alumneId)}/nee`,
    { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(cos) },
  )
  return handleResponse<AlumneDomini>(res)
}

export async function savePassaLlista(input: {
  grup_id: string
  data: string
  franja: string
  registres: { alumne_id: string; estat: EstatRegistre }[]
}): Promise<RegistreAssistencia[]> {
  const res = await fetch(`${BASE_URL}/assistencia/registres`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  const data = await handleResponse<{ registres: RegistreAssistencia[] }>(res)
  return data.registres
}

export async function fetchRegistres(
  grupId: string,
  data: string,
  franja?: string,
): Promise<RegistreAssistencia[]> {
  const q = new URLSearchParams({ grup_id: grupId, data })
  if (franja) q.set('franja', franja)
  const res = await fetch(`${BASE_URL}/assistencia/registres?${q.toString()}`, {
    headers: authHeaders(),
  })
  const d = await handleResponse<{ registres: RegistreAssistencia[] }>(res)
  return d.registres
}

export async function fetchAlertesAbsentisme(): Promise<AlertaAbsentisme[]> {
  const res = await fetch(`${BASE_URL}/assistencia/alertes`, { headers: authHeaders() })
  const d = await handleResponse<{ alertes: AlertaAbsentisme[] }>(res)
  return d.alertes
}

export async function fetchResumAssistencia(alumneId: string): Promise<ResumAssistencia> {
  const res = await fetch(`${BASE_URL}/assistencia/alumne/${encodeURIComponent(alumneId)}/resum`, {
    headers: authHeaders(),
  })
  return handleResponse<ResumAssistencia>(res)
}

export async function createJustificant(input: {
  alumne_id: string
  data_inici: string
  data_fi?: string
  motiu: string
  descripcio?: string
}): Promise<Justificant> {
  const res = await fetch(`${BASE_URL}/assistencia/justificants`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Justificant>(res)
}

export async function fetchJustificants(estat?: string): Promise<Justificant[]> {
  const q = estat ? `?estat=${encodeURIComponent(estat)}` : ''
  const res = await fetch(`${BASE_URL}/assistencia/justificants${q}`, { headers: authHeaders() })
  const d = await handleResponse<{ justificants: Justificant[] }>(res)
  return d.justificants
}

export async function patchJustificant(
  id: string,
  estat: 'acceptat' | 'rebutjat',
  motiu?: string,
): Promise<Justificant> {
  const res = await fetch(`${BASE_URL}/assistencia/justificants/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ estat, motiu }),
  })
  return handleResponse<Justificant>(res)
}

// ─── Pagaments / quotes ───────────────────────────────────────────────────────

export interface QuotaInput {
  alumne_id?: string
  concepte?: string
  quantitat?: number
  venciment?: string
  descripcio?: string
  estat?: string
}

export async function fetchPagaments(): Promise<Quota[]> {
  const res = await fetch(`${BASE_URL}/pagaments`, { headers: authHeaders() })
  const d = await handleResponse<{ quotes: Quota[] }>(res)
  return d.quotes
}

export async function createQuota(input: QuotaInput): Promise<Quota> {
  const res = await fetch(`${BASE_URL}/pagaments`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Quota>(res)
}

export async function patchQuota(id: string, canvis: QuotaInput): Promise<Quota> {
  const res = await fetch(`${BASE_URL}/pagaments/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Quota>(res)
}

export async function deleteQuota(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/pagaments/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
}

// ─── Avaluacions LOMLOE (Fase 3.2) ────────────────────────────────────────────

export async function fetchCompetencies(
  nivell?: string,
  area?: string,
): Promise<{ competencies: Competencia[]; criteris: Criteri[] }> {
  const params = new URLSearchParams()
  if (nivell) params.set('nivell', nivell)
  if (area) params.set('area', area)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE_URL}/avaluacio/competencies${qs}`, { headers: authHeaders() })
  return handleResponse<{ competencies: Competencia[]; criteris: Criteri[] }>(res)
}

export async function fetchRubriques(): Promise<Rubrica[]> {
  const res = await fetch(`${BASE_URL}/avaluacio/rubriques`, { headers: authHeaders() })
  const d = await handleResponse<{ rubriques: Rubrica[] }>(res)
  return d.rubriques
}

export async function createRubrica(input: {
  titol: string
  criteri_id?: string | null
  nivells_assoliment?: Record<string, string> | null
  assistit_per_ia?: boolean
}): Promise<Rubrica> {
  const res = await fetch(`${BASE_URL}/avaluacio/rubriques`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Rubrica>(res)
}

/** Demana a l'IA un esborrany de rúbrica per a un criteri (el docent el revisa i el desa). */
export async function suggereixRubrica(criteri_id: string): Promise<{
  titol: string
  nivells_assoliment: Record<string, string>
  criteri_id: string
  assistit_per_ia: boolean
}> {
  const res = await fetch(`${BASE_URL}/avaluacio/rubriques/suggereix`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ criteri_id }),
  })
  return handleResponse(res)
}

// ─── Notificacions / recordatoris (§3) ────────────────────────────────────────

export async function fetchNotificacions(): Promise<Notificacio[]> {
  const res = await fetch(`${BASE_URL}/notificacions`, { headers: authHeaders() })
  const d = await handleResponse<{ notificacions: Notificacio[] }>(res)
  return d.notificacions
}

export async function fetchAvaluacions(
  alumneId?: string,
  trimestre?: string,
): Promise<Avaluacio[]> {
  const p = new URLSearchParams()
  if (alumneId) p.set('alumne_id', alumneId)
  if (trimestre) p.set('trimestre', trimestre)
  const qs = p.toString() ? `?${p.toString()}` : ''
  const res = await fetch(`${BASE_URL}/avaluacio/avaluacions${qs}`, { headers: authHeaders() })
  const d = await handleResponse<{ avaluacions: Avaluacio[] }>(res)
  return d.avaluacions
}

export async function createAvaluacio(input: {
  alumne_id: string
  criteri_id?: string | null
  rubrica_id?: string | null
  qualificacio: Qualificacio
  evidencies?: string[] | null
  comentari_docent?: string | null
  trimestre: Trimestre
  curs_academic?: string | null
  validada?: boolean
}): Promise<Avaluacio> {
  const res = await fetch(`${BASE_URL}/avaluacio/avaluacions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Avaluacio>(res)
}

export async function patchAvaluacio(
  id: string,
  canvis: {
    qualificacio?: Qualificacio
    comentari_docent?: string | null
    evidencies?: string[] | null
    validada?: boolean
  },
): Promise<Avaluacio> {
  const res = await fetch(`${BASE_URL}/avaluacio/avaluacions/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Avaluacio>(res)
}

export async function fetchButlletins(
  alumneId?: string,
  trimestre?: string,
): Promise<Butlleti[]> {
  const p = new URLSearchParams()
  if (alumneId) p.set('alumne_id', alumneId)
  if (trimestre) p.set('trimestre', trimestre)
  const qs = p.toString() ? `?${p.toString()}` : ''
  const res = await fetch(`${BASE_URL}/avaluacio/butlletins${qs}`, { headers: authHeaders() })
  const d = await handleResponse<{ butlletins: Butlleti[] }>(res)
  return d.butlletins
}

export async function generarButlleti(input: {
  alumne_id: string
  trimestre: Trimestre
  curs_academic?: string | null
}): Promise<Butlleti> {
  const res = await fetch(`${BASE_URL}/avaluacio/butlletins/generar`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Butlleti>(res)
}

export async function patchButlleti(
  id: string,
  canvis: { estat?: EstatButlleti; contingut?: Record<string, unknown>; assistit_per_ia?: boolean },
): Promise<Butlleti> {
  const res = await fetch(`${BASE_URL}/avaluacio/butlletins/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Butlleti>(res)
}

/** Demana a l'IA un esborrany del comentari global (el docent el revisa i el desa). */
export async function suggereixComentariButlleti(
  id: string,
): Promise<{ comentari: string; assistit_per_ia: boolean }> {
  const res = await fetch(
    `${BASE_URL}/avaluacio/butlletins/${encodeURIComponent(id)}/suggereix-comentari`,
    { method: 'POST', headers: authHeaders() },
  )
  return handleResponse<{ comentari: string; assistit_per_ia: boolean }>(res)
}

export async function fetchMapeigCompetencial(
  grupId: string,
  trimestre?: string,
): Promise<MapeigCompetencial> {
  const p = new URLSearchParams({ grup_id: grupId })
  if (trimestre) p.set('trimestre', trimestre)
  const res = await fetch(`${BASE_URL}/avaluacio/mapeig-competencial?${p.toString()}`, {
    headers: authHeaders(),
  })
  return handleResponse<MapeigCompetencial>(res)
}

export interface PuntEvolucio {
  trimestre: string
  curs_academic?: string | null
  valor_ordinal: number
  valor_qualitatiu: string
  n: number
}
export interface SerieCompetencial {
  competencia_codi: string
  competencia_nom?: string | null
  punts: PuntEvolucio[]
}
export interface EvolucioCompetencial {
  alumne_id: string
  alumne_nom?: string | null
  series: SerieCompetencial[]
  trimestres: string[]
  llegenda: Record<string, string>
}

export async function fetchEvolucioCompetencial(
  alumneId: string,
  cursAcademic?: string,
): Promise<EvolucioCompetencial> {
  const p = new URLSearchParams({ alumne_id: alumneId })
  if (cursAcademic) p.set('curs_academic', cursAcademic)
  const res = await fetch(`${BASE_URL}/avaluacio/evolucio-competencial?${p.toString()}`, {
    headers: authHeaders(),
  })
  return handleResponse<EvolucioCompetencial>(res)
}

// ─── Importació massiva (CSV/JSON) ────────────────────────────────────────────

export async function fetchImportPlantilles(): Promise<Record<string, string[]>> {
  const res = await fetch(`${BASE_URL}/importacio/plantilles`, { headers: authHeaders() })
  const d = await handleResponse<{ columnes: Record<string, string[]> }>(res)
  return d.columnes
}

export async function importaDades(input: {
  tipus: string
  format: string
  contingut: string
  institucio?: string
}): Promise<ImportReport> {
  const res = await fetch(`${BASE_URL}/importacio`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<ImportReport>(res)
}

// ─── Tasques (gestió interna) ─────────────────────────────────────────────────

export interface TascaInput {
  titol: string
  descripcio?: string
  assignat_a?: string
  prioritat?: string
  venciment?: string
  estat?: string
}

export async function fetchTasques(estat?: string): Promise<Tasca[]> {
  const q = estat ? `?estat=${encodeURIComponent(estat)}` : ''
  const res = await fetch(`${BASE_URL}/tasques${q}`, { headers: authHeaders() })
  const d = await handleResponse<{ tasques: Tasca[] }>(res)
  return d.tasques
}

export async function createTasca(input: TascaInput): Promise<Tasca> {
  const res = await fetch(`${BASE_URL}/tasques`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<Tasca>(res)
}

export async function patchTasca(id: string, canvis: Partial<TascaInput>): Promise<Tasca> {
  const res = await fetch(`${BASE_URL}/tasques/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(canvis),
  })
  return handleResponse<Tasca>(res)
}

export async function deleteTasca(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/tasques/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`No s'ha pogut esborrar (HTTP ${res.status})`)
}

// ─── Xat amb SSE (stream=true) ────────────────────────────────────────────────

export interface ChatSSECallbacks {
  onToken: (delta: string) => void
  onSources: (fonts: Font[]) => void
  onRecursos?: (recursos: RecursSuggerit[]) => void
  onDone: (message: Missatge, conversationId?: string) => void
  onError: (err: string) => void
}

export async function streamChat(
  agent_id: string,
  message: string,
  conversation_id: string | null,
  callbacks: ChatSSECallbacks,
): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  let response: Response
  try {
    response = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ agent_id, conversation_id, message, stream: true }),
    })
  } catch {
    callbacks.onError('No s\'ha pogut connectar amb el servidor. Comprova que el backend està en marxa.')
    return
  }

  if (!response.ok) {
    callbacks.onError(`Error del servidor: ${response.status}`)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    callbacks.onError('El servidor no admet streaming.')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = '' // event SSE actual (token | sources | done | error)

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const rawLine of lines) {
      const line = rawLine.replace(/\r$/, '')
      if (line === '') {
        currentEvent = '' // final d'un esdeveniment SSE
        continue
      }
      if (line.startsWith(':')) continue // comentari (p. ex. ': ping')
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim()
        continue
      }
      if (!line.startsWith('data:')) continue

      // Valor després de 'data:'; SSE elimina un sol espai inicial. NO fem trim:
      // els tokens poden portar espais significatius (p. ex. " equival").
      let dataVal = line.slice(5)
      if (dataVal.startsWith(' ')) dataVal = dataVal.slice(1)

      if (currentEvent === 'token') {
        callbacks.onToken(dataVal)
      } else if (currentEvent === 'sources') {
        try {
          callbacks.onSources(JSON.parse(dataVal) as Font[])
        } catch {
          /* fonts malformades */
        }
      } else if (currentEvent === 'recursos') {
        try {
          callbacks.onRecursos?.(JSON.parse(dataVal) as RecursSuggerit[])
        } catch {
          /* recursos malformats */
        }
      } else if (currentEvent === 'done') {
        try {
          const d = JSON.parse(dataVal) as { message: Missatge; conversation_id?: string }
          callbacks.onDone(d.message, d.conversation_id)
        } catch {
          /* done malformat */
        }
      } else if (currentEvent === 'error') {
        try {
          const d = JSON.parse(dataVal) as { missatge?: string }
          callbacks.onError(d.missatge ?? 'Error del servidor.')
        } catch {
          callbacks.onError('Error del servidor.')
        }
      }
    }
  }
}

// ─── Administració: registre E/S, certificats, circulars, panell PAS ────────

export interface RegistreES {
  id: string
  numero: number
  any: number
  tipus: 'entrada' | 'sortida'
  data: string
  interlocutor: string
  assumpte: string
  canal: string
  estat: string
  observacions?: string | null
  alumne_id?: string | null
  registrat_per: string
  creat_el?: string | null
}

export async function fetchRegistresES(params?: { tipus?: string; any?: number; estat?: string }): Promise<RegistreES[]> {
  const p = new URLSearchParams()
  if (params?.tipus) p.set('tipus', params.tipus)
  if (params?.any) p.set('any', String(params.any))
  if (params?.estat) p.set('estat', params.estat)
  const res = await fetch(`${BASE_URL}/registre?${p.toString()}`, { headers: authHeaders() })
  const d = await handleResponse<{ registres: RegistreES[] }>(res)
  return d.registres
}

export async function createRegistreES(cos: {
  tipus: string; data: string; interlocutor: string; assumpte: string
  canal?: string; observacions?: string; alumne_id?: string
}): Promise<RegistreES> {
  const res = await fetch(`${BASE_URL}/registre`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(cos),
  })
  return handleResponse<RegistreES>(res)
}

export async function patchRegistreES(id: string, canvis: { estat?: string; assumpte?: string; observacions?: string }): Promise<RegistreES> {
  const res = await fetch(`${BASE_URL}/registre/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: authHeaders(), body: JSON.stringify(canvis),
  })
  return handleResponse<RegistreES>(res)
}

export async function fetchSeguentNumero(tipus: string): Promise<{ tipus: string; any: number; seguent: number }> {
  const res = await fetch(`${BASE_URL}/registre/seguent-numero?tipus=${encodeURIComponent(tipus)}`, { headers: authHeaders() })
  return handleResponse(res)
}

export interface Certificat {
  id: string
  numero: number
  any: number
  tipus: string
  alumne_id?: string | null
  destinatari: string
  contingut?: Record<string, unknown> | null
  emes_per: string
  creat_el?: string | null
}

export async function fetchCertificats(): Promise<Certificat[]> {
  const res = await fetch(`${BASE_URL}/certificats`, { headers: authHeaders() })
  const d = await handleResponse<{ certificats: Certificat[] }>(res)
  return d.certificats
}

export async function emetCertificat(cos: {
  tipus: string; alumne_id?: string; destinatari?: string; contingut?: Record<string, unknown>
}): Promise<Certificat> {
  const res = await fetch(`${BASE_URL}/certificats`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(cos),
  })
  return handleResponse<Certificat>(res)
}

export async function descarregaCertificatPdf(id: string): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/certificats/${encodeURIComponent(id)}/pdf`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Error ${res.status} descarregant el certificat`)
  return res.blob()
}

export interface Circular {
  id: string
  titol: string
  cos: string
  abast: string
  destinatari_ref?: string | null
  estat: string
  es_plantilla: boolean
  assistit_per_ia: boolean
  creat_per: string
  creat_el?: string | null
  actualitzat_el?: string | null
}

export async function fetchCirculars(plantilla?: boolean): Promise<Circular[]> {
  const p = plantilla !== undefined ? `?plantilla=${plantilla}` : ''
  const res = await fetch(`${BASE_URL}/comunicacions${p}`, { headers: authHeaders() })
  const d = await handleResponse<{ circulars: Circular[] }>(res)
  return d.circulars
}

export async function createCircular(cos: {
  titol: string; cos?: string; abast?: string; destinatari_ref?: string; es_plantilla?: boolean; assistit_per_ia?: boolean
}): Promise<Circular> {
  const res = await fetch(`${BASE_URL}/comunicacions`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(cos),
  })
  return handleResponse<Circular>(res)
}

export async function patchCircular(id: string, canvis: Partial<{ titol: string; cos: string; abast: string; estat: string; es_plantilla: boolean }>): Promise<Circular> {
  const res = await fetch(`${BASE_URL}/comunicacions/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: authHeaders(), body: JSON.stringify(canvis),
  })
  return handleResponse<Circular>(res)
}

export async function deleteCircular(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/comunicacions/${encodeURIComponent(id)}`, {
    method: 'DELETE', headers: authHeaders(),
  })
  await handleResponse(res)
}

export interface Esdeveniment {
  id: string
  titol: string
  descripcio?: string | null
  data: string
  data_fi?: string | null
  tipus: string
  ambit: string
  recordatori_dies: number
  estat: string
  origen?: string | null
  creat_per: string
  creat_el?: string | null
}

export async function fetchAgenda(params?: { tipus?: string; des?: string; fins?: string }): Promise<Esdeveniment[]> {
  const p = new URLSearchParams()
  if (params?.tipus) p.set('tipus', params.tipus)
  if (params?.des) p.set('des', params.des)
  if (params?.fins) p.set('fins', params.fins)
  const res = await fetch(`${BASE_URL}/agenda?${p.toString()}`, { headers: authHeaders() })
  const d = await handleResponse<{ esdeveniments: Esdeveniment[] }>(res)
  return d.esdeveniments
}

export async function createEsdeveniment(cos: {
  titol: string; descripcio?: string; data: string; data_fi?: string
  tipus?: string; ambit?: string; recordatori_dies?: number
}): Promise<Esdeveniment> {
  const res = await fetch(`${BASE_URL}/agenda`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(cos),
  })
  return handleResponse<Esdeveniment>(res)
}

export async function patchEsdeveniment(id: string, canvis: Partial<{ estat: string; titol: string; data: string; tipus: string }>): Promise<Esdeveniment> {
  const res = await fetch(`${BASE_URL}/agenda/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: authHeaders(), body: JSON.stringify(canvis),
  })
  return handleResponse<Esdeveniment>(res)
}

export async function deleteEsdeveniment(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/agenda/${encodeURIComponent(id)}`, {
    method: 'DELETE', headers: authHeaders(),
  })
  await handleResponse(res)
}

export async function carregaCursAgenda(curs_academic: string): Promise<Esdeveniment[]> {
  const res = await fetch(`${BASE_URL}/agenda/carrega-curs`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify({ curs_academic }),
  })
  const d = await handleResponse<{ esdeveniments: Esdeveniment[] }>(res)
  return d.esdeveniments
}

export interface PanellPas {
  data: string
  blocs: {
    tasques: { pendents: number; vencen_aviat: { id: string; titol: string; venciment: string; prioritat: string; vencuda: boolean }[]; feature: boolean }
    pagaments: { pendents: number; import_pendent: number; feature: boolean }
    justificants: { pendents: number; feature: boolean }
    matricula: { en_tramit: number; feature: boolean }
    registre: { en_tramit: number; feature: boolean }
    comunicacions: { esborranys: number; feature: boolean }
  }
}

export async function fetchPanellPas(): Promise<PanellPas> {
  const res = await fetch(`${BASE_URL}/panell-pas`, { headers: authHeaders() })
  return handleResponse<PanellPas>(res)
}

// ─── Llicència i features (capa comercial) ──────────────────────────────────

export interface Llicencia {
  pla: string
  pla_nom: string
  estat: 'activa' | 'prova' | 'suspesa' | 'caducada'
  features: string[]
  totes_les_features: Record<string, string>
  limits: Record<string, number>
  us_actual: Record<string, number>
  data_inici?: string | null
  data_caducitat?: string | null
  dies_fins_caducitat?: number | null
}

export async function fetchLlicencia(): Promise<Llicencia> {
  const res = await fetch(`${BASE_URL}/institucio/llicencia`, { headers: authHeaders() })
  return handleResponse<Llicencia>(res)
}

export interface CentreFlota {
  slug: string
  nom: string
  actiu: boolean
  pla: string
  pla_nom: string
  estat_llicencia: string
  data_caducitat?: string | null
  dies_fins_caducitat?: number | null
  limits: Record<string, number>
  us: Record<string, number>
  n_features: number
}

export async function fetchFlota(): Promise<CentreFlota[]> {
  const res = await fetch(`${BASE_URL}/admin/flota`, { headers: authHeaders() })
  const d = await handleResponse<{ centres: CentreFlota[] }>(res)
  return d.centres
}

export interface PlaComercial {
  id: string
  nom: string
  descripcio: string
  features: string[]
  limits: Record<string, number>
}

export async function fetchPlans(): Promise<{ plans: PlaComercial[]; features: Record<string, string> }> {
  const res = await fetch(`${BASE_URL}/admin/plans`, { headers: authHeaders() })
  return handleResponse(res)
}

export async function putLlicencia(
  slug: string,
  cos: { pla?: string; features?: string[]; limits?: Record<string, number>; data_inici?: string; data_caducitat?: string; estat?: string },
): Promise<{ slug: string; llicencia: Llicencia }> {
  const res = await fetch(`${BASE_URL}/admin/institucions/${encodeURIComponent(slug)}/llicencia`, {
    method: 'PUT', headers: authHeaders(), body: JSON.stringify(cos),
  })
  return handleResponse(res)
}

// ─── Estat de producció ────────────────────────────────────────────────────

export interface ProduccioControl {
  clau: string
  titol: string
  severitat: 'ok' | 'info' | 'avis' | 'critic'
  detall: string
  recomanacio?: string | null
}

export interface ProduccioReport {
  ts: string
  host: string
  entorn: string
  versio: string
  server_host: string
  severitat_global: 'ok' | 'info' | 'avis' | 'critic'
  controls: ProduccioControl[]
  puntuacio: number
}

export async function fetchProduccioEstat(): Promise<ProduccioReport> {
  const res = await fetch(`${BASE_URL}/system/produccio`, { headers: authHeaders() })
  return handleResponse<ProduccioReport>(res)
}

// ─── Seguretat de xarxa per institució ──────────────────────────────────────

export interface AccesXarxa {
  actiu: boolean
  cidrs_lan: string[]
  ips_permeses: string[]
  actualitzat_el?: string | null
  actualitzat_per?: string | null
  ip_actual?: string | null
  ip_actual_permesa: boolean
}

export interface AccesXarxaUpdate {
  actiu?: boolean
  cidrs_lan?: string[]
  ips_permeses?: string[]
}

export interface DeteccioXarxa {
  ip_actual?: string | null
  es_local: boolean
  cidr_suggerit?: string | null
  missatge: string
}

export async function fetchAccesXarxa(): Promise<AccesXarxa> {
  const res = await fetch(`${BASE_URL}/institucio/seguretat/xarxa`, { headers: authHeaders() })
  return handleResponse<AccesXarxa>(res)
}

export async function putAccesXarxa(cos: AccesXarxaUpdate): Promise<AccesXarxa> {
  const res = await fetch(`${BASE_URL}/institucio/seguretat/xarxa`, {
    method: 'PUT', headers: authHeaders(), body: JSON.stringify(cos),
  })
  return handleResponse<AccesXarxa>(res)
}

export async function detectaXarxa(): Promise<DeteccioXarxa> {
  const res = await fetch(`${BASE_URL}/institucio/seguretat/xarxa/detecta`, { headers: authHeaders() })
  return handleResponse<DeteccioXarxa>(res)
}

// ─── Xat sense stream (fallback) ─────────────────────────────────────────────

export async function sendChat(
  agent_id: string,
  message: string,
  conversation_id: string | null,
): Promise<{ conversation_id: string; message: Missatge; agent_utilitzat: string }> {
  const res = await fetch(`${BASE_URL}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ agent_id, conversation_id, message, stream: false }),
  })
  return handleResponse(res)
}

// ─── Copilot didàctic ───────────────────────────────────────────────────────

export async function fetchCopilotContinguts(): Promise<CopilotContingut[]> {
  const res = await fetch(`${BASE_URL}/copilot/continguts`, { headers: authHeaders() })
  const d = await handleResponse<{ continguts: CopilotContingut[] }>(res)
  return d.continguts
}

export async function createCopilotContingut(input: {
  titol: string
  tipus: string
  contingut: string
  metadades?: Record<string, unknown> | null
  conversation_id?: string | null
}): Promise<CopilotContingut> {
  const res = await fetch(`${BASE_URL}/copilot/continguts`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<CopilotContingut>(res)
}

export type CopilotExportFormat = 'pdf' | 'docx' | 'md' | 'txt'

export async function exportCopilotContingut(id: string, format: CopilotExportFormat): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(
    `${BASE_URL}/copilot/continguts/${encodeURIComponent(id)}/export?format=${format}`,
    { headers },
  )
  if (!res.ok) throw new Error(`No s'ha pogut exportar (HTTP ${res.status})`)
  const blob = await res.blob()
  const cd = res.headers.get('content-disposition') ?? ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] ?? `copilot.${format}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export async function fetchCopilotEvidencies(params?: {
  alumne_id?: string
  pendents?: boolean
}): Promise<CopilotEvidencia[]> {
  const qs = new URLSearchParams()
  if (params?.alumne_id) qs.set('alumne_id', params.alumne_id)
  if (params?.pendents !== undefined) qs.set('pendents', String(params.pendents))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${BASE_URL}/copilot/evidencies${suffix}`, { headers: authHeaders() })
  const d = await handleResponse<{ evidencies: CopilotEvidencia[] }>(res)
  return d.evidencies
}

export async function createCopilotEvidencia(input: {
  alumne_id: string
  resposta: string
  tipus?: string
  feedback_ia?: string | null
  conversation_id?: string | null
  contingut_id?: string | null
  competencies?: string[] | null
  sabers?: string[] | null
  indicadors?: string[] | null
  criteris_ids?: string[] | null
  valoracio_proposada?: string | null
}): Promise<CopilotEvidencia> {
  const res = await fetch(`${BASE_URL}/copilot/evidencies`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<CopilotEvidencia>(res)
}

export async function validateCopilotEvidencia(
  id: string,
  input: {
    validada: boolean
    valoracio_validada?: 'NA' | 'AS' | 'AN' | 'AE' | null
    comentari_docent?: string | null
    criteri_id?: string | null
    rubrica_id?: string | null
    trimestre?: string
    curs_academic?: string | null
  },
): Promise<CopilotEvidencia> {
  const res = await fetch(`${BASE_URL}/copilot/evidencies/${encodeURIComponent(id)}/validacio`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(input),
  })
  return handleResponse<CopilotEvidencia>(res)
}
