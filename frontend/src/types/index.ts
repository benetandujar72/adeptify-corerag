// ─── Models de dades (API_CONTRACT.md) ───────────────────────────────────────

export interface Agent {
  id: string          // tutor_mates | secretaria | families | documental
  nom: string
  descripcio: string
  color: string       // hex per a la UI
  rols_permesos: Rol[]
}

export type Rol = 'docent' | 'alumne' | 'familia' | 'direccio' | 'pas' | 'superadmin'

export interface User {
  username: string
  rol: Rol
  nom?: string | null
  email?: string | null
  actiu: boolean
  institucio_id?: string
  creat_el?: string | null
  ultim_acces?: string | null
}

// ─── Institucions (multi-tenant / creador de RAGs) ───────────────────────────

export interface InstitucioBranding {
  logo_url?: string       // URL del logo (si buit, s'usa el text)
  logo_text?: string      // inicials per al badge (p. ex. "NP")
  color_primari?: string  // hex; mapeja a la variable de marca "navy"
  color_secundari?: string // hex; mapeja a "terra" (accent)
  lema?: string           // subtítol opcional
}

export interface InstitucioConfig {
  llm_model?: string       // model per defecte d'aquesta institució
  agents_actius?: string[] // ids d'agents habilitats (buit = tots)
  rag_top_k?: number
  reranker_actiu?: boolean
}

export interface Institucio {
  slug: string
  nom: string
  actiu: boolean
  config?: InstitucioConfig | null
  branding?: InstitucioBranding | null
  creat_el?: string | null
}

/** Info mínima d'una institució per a la pantalla de selecció (pre-login). */
export interface InstitucioPublica {
  slug: string
  nom: string
  branding?: InstitucioBranding | null
}

export interface AuditEntry {
  id: string
  usuari: string
  rol: string
  accio: string
  agent?: string | null
  conversation_id?: string | null
  detalls?: Record<string, unknown> | null
  creat_el: string
}

export interface Font {
  doc_id: string
  filename: string
  tipus: 'pdf' | 'docx' | 'xlsx' | 'md' | 'html' | 'image'
  pagina?: number
  fragments: number
  score: number       // 0..1
  verificat_el: string
  snippet?: string
}

/** Proposta d'acció d'escriptura preparada per l'assistent agèntic (tool-calling).
 *  No s'executa fins que la persona la confirma (art. 14 AI Act). */
export interface PropostaAccio {
  proposta: boolean
  accio: string // p. ex. 'crea_tasca'
  args: Record<string, unknown>
  instruccio?: string
}

export interface Missatge {
  id: string
  rol: 'user' | 'assistant'
  contingut: string
  agent_id?: string
  fonts?: Font[]
  confianca?: number
  creat_el: string
  proposta?: PropostaAccio | null
}

export interface Conversa {
  id: string
  titol: string
  agent_id: string
  etiqueta: string
  actualitzat_el: string
  n_missatges: number
}

export interface SystemStatus {
  servidor: {
    actiu: boolean
    host: string
    entorn: string
  }
  indexacio: {
    al_dia: boolean
    documents: number
    ultima: string
  }
  privadesa: {
    processament_local: boolean
    crides_externes: number
    xifratge: string
    auditat_el: string
  }
  model: {
    nom: string
    backend: string
    catala: string
  }
  versio: string
}

export interface AuthResponse {
  token: string
  rol: Rol
  mfa_required?: boolean
}

/** Dades de l'inici d'enrolment MFA (secret per a entrada manual + URI per al QR). */
export interface MfaSetup {
  secret: string
  otpauth_uri: string
}

export interface MeResponse {
  usuari: string
  rol: Rol
  idioma?: string  // ca | es | eu (per defecte 'ca')
}

export interface ApiError {
  error: {
    codi: 'FORBIDDEN' | 'NOT_FOUND' | 'RATE_LIMIT' | 'INTERNAL'
    missatge: string
  }
}

// ─── Estat intern de la UI ───────────────────────────────────────────────────

export interface MissatgeUI extends Missatge {
  streaming?: boolean   // s'està rebent per SSE
  streamBuffer?: string // text acumulat durant l'stream
}

export interface UserSession {
  usuari: string
  rol: Rol
  token: string
}

// ─── Navegació (vistes del menú superior) ────────────────────────────────────

export type Vista =
  | 'inici'
  | 'tutoria'
  | 'secretaria'
  | 'families'
  | 'avaluacions'
  | 'avaluacio'
  | 'matricula'
  | 'assistencia'
  | 'gestio'
  | 'correu'
  | 'tasques'
  | 'importacio'
  | 'expedients'
  | 'pagaments'
  | 'documents'
  | 'moodle_cursos'
  | 'onboarding'
  | 'config'
  | 'admin'
  | 'usuaris'
  | 'skills'
  | 'recursos'
  | 'seguretat'
  | 'registre'
  | 'certificats'
  | 'comunicacions'
  | 'panell_pas'
  | 'agenda'
  | 'ajuda'

// ─── Matrícula (Fase 3 — tràmit) ─────────────────────────────────────────────

export type EstatTramit =
  | 'esborrany'
  | 'presentada'
  | 'en_revisio'
  | 'acceptada'
  | 'denegada'
  | 'llista_espera'

export interface TramitHistoric {
  estat_anterior?: string | null
  estat_nou: string
  usuari_canvi: string
  motiu?: string | null
  creat_el: string
}

export interface SollicitudMatricula {
  id: string
  alumne_nom: string
  alumne_cognoms: string
  data_naixement?: string | null
  tutor_nom: string
  tutor_email?: string | null
  tutor_telefon?: string | null
  nivell_sollicitat: string
  curs_academic?: string | null
  germans_al_centre: boolean
  estat: EstatTramit
  observacions?: string | null
  consentiment_dades: boolean
  creat_per: string
  creat_el?: string | null
  actualitzat_el?: string | null
  historic: TramitHistoric[]
}

export interface ChecklistItem {
  clau: string
  etiqueta: string
  obligatori: boolean
}

// ─── Integracions externes (Fase 4 — Google) ────────────────────────────────

export interface GoogleIntegracio {
  actiu: boolean
  auth_mode: string // service_account | oauth
  project_id: string
  workspace_domain: string
  sa_subject: string
  client_id: string
  redirect_uri: string
  scopes: string[]
  drive_folders: string[]
  calendar_ids: string[]
  gmail_sender: string
  gmail_comptes: string[]
  sa_json_set: boolean
  client_secret_set: boolean
}

export interface LmsIntegracio {
  actiu: boolean
  moodle_actiu: boolean
  moodle_base_url: string
  moodle_course_ids: string[]
  moodle_token_set: boolean
  classroom_actiu: boolean
  classroom_course_ids: string[]
  ingesta_entregues: boolean
}

export interface LmsMaterial {
  id: string
  titol: string
  tipus: string
  descripcio: string
  url?: string | null
  mime?: string | null
  filename?: string | null
}

export interface MoodleBackupActivity {
  id: string
  tipus: string
  titol: string
  intro: string
  contingut: string
  url: string
  directori: string
  xml_principal: string
}

export interface MoodleBackupSection {
  id: string
  numero: number
  nom: string
  resum: string
  directori: string
  activities: MoodleBackupActivity[]
}

export interface MoodleBackupBlueprint {
  fullname: string
  shortname: string
  summary: string
  category: string
  archive_kind: string
  sections: MoodleBackupSection[]
  stats: Record<string, number>
}

export interface OnboardingDoc {
  id: string
  titol: string
  descripcio: string
  tipus: string
  url?: string | null
  doc_id?: string | null
  etiquetes: string[]
  origen: string
}

export interface OnboardingStep {
  id: string
  titol: string
  pregunta: string
  tipus: 'ack' | 'single' | 'multi' | 'text'
  opcions: Array<{ value: string; label: string }>
  ajuda: string
  documents: OnboardingDoc[]
}

export interface OnboardingResposta {
  step_id: string
  pregunta: string
  resposta: Record<string, unknown>
  docs_revisats: string[]
  creat_el?: string | null
}

export interface OnboardingProfile {
  id: string
  titol: string
  descripcio: string
  rols: string[]
}

export interface OnboardingStatus {
  sessio_id?: string | null
  perfil: string
  perfil_titol: string
  estat: string
  validat: boolean
  validat_el?: string | null
  pas_actual?: string | null
  progress: { resposts: number; total: number; percent: number }
  current_step?: OnboardingStep | null
  respostes: OnboardingResposta[]
  perfils_disponibles: OnboardingProfile[]
}

export interface OnboardingAdminItem {
  sessio_id: string
  usuari: string
  rol: string
  perfil: string
  perfil_titol: string
  estat: string
  validat: boolean
  validat_el?: string | null
  progress: { resposts: number; total: number; percent: number }
  actualitzat_el?: string | null
}

export interface CalendarEvent {
  id: string
  titol: string
  inici?: string | null
  descripcio?: string | null
}

export interface GmailThread {
  id: string
  thread_id?: string | null
  from?: string | null
  subject?: string | null
  date?: string | null
  snippet?: string | null
}

export interface GmailMessage {
  id: string
  from?: string | null
  to?: string | null
  subject?: string | null
  date?: string | null
  cos?: string | null
}

// ─── Tasques (gestió interna) ────────────────────────────────────────────────

export type EstatTasca = 'pendent' | 'en_curs' | 'feta'
export type Prioritat = 'baixa' | 'normal' | 'alta'

export interface Tasca {
  id: string
  titol: string
  descripcio?: string | null
  assignat_a?: string | null
  creat_per: string
  estat: EstatTasca
  prioritat: Prioritat
  venciment?: string | null
  creat_el?: string | null
  actualitzat_el?: string | null
}

// ─── Pagaments / quotes ──────────────────────────────────────────────────────

export type EstatQuota = 'pendent' | 'pagat' | 'exempt'

export interface Quota {
  id: string
  alumne_id: string
  alumne_nom?: string | null
  concepte: string
  quantitat: number
  estat: EstatQuota
  venciment?: string | null
  descripcio?: string | null
  creat_per: string
  creat_el?: string | null
}

// ─── Avaluacions LOMLOE (Fase 3.2) ───────────────────────────────────────────

export type Qualificacio = 'NA' | 'AS' | 'AN' | 'AE'
export type Trimestre = '1' | '2' | '3'
export type EstatButlleti = 'esborrany' | 'validat' | 'publicat'

export interface Competencia {
  id: string
  codi: string
  nom: string
  etapa?: string | null
  descripcio?: string | null
}

export interface Criteri {
  id: string
  area: string
  nivell: string
  codi: string
  enunciat: string
  competencia_id?: string | null
  competencia_codi?: string | null
}

export interface Rubrica {
  id: string
  titol: string
  criteri_id?: string | null
  docent_id: string
  nivells_assoliment?: Record<string, string> | null
  assistit_per_ia: boolean
  creat_el?: string | null
}

export interface CopilotContingut {
  id: string
  titol: string
  tipus: string
  contingut: string
  metadades?: Record<string, unknown> | null
  conversation_id?: string | null
  creat_per: string
  assistit_per_ia: boolean
  estat: string
  creat_el?: string | null
  actualitzat_el?: string | null
}

export interface CopilotEvidencia {
  id: string
  alumne_id: string
  tipus: string
  resposta: string
  feedback_ia?: string | null
  conversation_id?: string | null
  contingut_id?: string | null
  competencies?: string[] | null
  sabers?: string[] | null
  indicadors?: string[] | null
  criteris_ids?: string[] | null
  valoracio_proposada?: string | null
  valoracio_validada?: string | null
  comentari_docent?: string | null
  docent_id?: string | null
  validada: boolean
  avaluacio_id?: string | null
  creat_per: string
  creat_el?: string | null
  actualitzat_el?: string | null
}

export interface Avaluacio {
  id: string
  alumne_id: string
  alumne_nom?: string | null
  criteri_id?: string | null
  criteri_codi?: string | null
  rubrica_id?: string | null
  docent_id: string
  qualificacio: Qualificacio
  evidencies?: string[] | null
  comentari_docent?: string | null
  trimestre: string
  curs_academic?: string | null
  validada: boolean
  creat_el?: string | null
}

export interface Butlleti {
  id: string
  alumne_id: string
  alumne_nom?: string | null
  trimestre: string
  curs_academic?: string | null
  estat: EstatButlleti
  contingut?: Record<string, unknown> | null
  generat_per: string
  validat_per?: string | null
  assistit_per_ia: boolean
  publicat_el?: string | null
  creat_el?: string | null
}

export interface MapeigAlumne {
  alumne_id: string
  alumne_nom: string
  per_competencia: Record<string, string>
}

export interface MapeigCompetencial {
  grup_id: string
  competencies: string[]
  alumnes: MapeigAlumne[]
}

// ─── Importació massiva ──────────────────────────────────────────────────────

export interface ImportReport {
  tipus: string
  total: number
  creats: number
  omesos: number
  errors: { fila: number; missatge: string }[]
}

export interface IntegracioTestResult {
  ok: boolean
  estat: string
  detall: string
}

export interface DriveFile {
  id: string
  name: string
  mimeType: string
  modifiedTime?: string
  size?: string
}

// ─── Assistència (Fase 3.3) ──────────────────────────────────────────────────

export type EstatRegistre = 'present' | 'absent' | 'retard' | 'justificat'

export interface GrupClasse {
  id: string
  nom: string
  nivell?: string | null
  curs_academic?: string | null
  n_alumnes: number
}

export interface AlumneDomini {
  id: string
  nom: string
  cognoms: string
  grup_id?: string | null
  // Avís pedagògic NEE/pla individualitzat. Només arriba al frontend a personal
  // autoritzat del centre (docent/PAS/direcció/superadmin); la família no ho rep.
  nee?: boolean | null
  pla_individualitzat?: boolean | null
  observacions_nee?: string | null
}

export interface RegistreAssistencia {
  alumne_id: string
  estat: EstatRegistre
  data: string
  franja: string
}

export interface ResumAssistencia {
  alumne_id: string
  present: number
  absent: number
  retard: number
  justificat: number
  total: number
  percentatge_faltes_injustificades: number
  alerta?: string | null
}

export interface AlertaAbsentisme {
  alumne_id: string
  nom: string
  cognoms: string
  grup_id?: string | null
  total: number
  absent: number
  percentatge_faltes_injustificades: number
  alerta: string
}

export interface Justificant {
  id: string
  alumne_id: string
  alumne_nom?: string | null
  data_inici: string
  data_fi?: string | null
  motiu: string
  descripcio?: string | null
  estat: string
  presentat_per: string
  revisat_per?: string | null
  creat_el?: string | null
}

// ─── Estudi d'Skills (agents personalitzats, docs/19) ────────────────────────

/** Agent personalitzat creat per la direcció (config, no codi). */
export interface Skill {
  id: string
  institucio_id: string
  nom: string
  descripcio: string
  color: string
  system_prompt: string
  paraules_clau: string[]
  rols_permesos: string[]
  tools: string[]
  coneixement: string[] // doc_ids del centre que limiten el RAG de l'agent (P3)
  actiu: boolean
  assistit_per_ia: boolean
  creat_per: string
  creat_el?: string | null
}

/** Recurs de documentació verificat que el sistema suggereix a la resposta (F2). */
export interface RecursSuggerit {
  id: string
  titol: string
  descripcio: string
  tipus: string // url | document
  url?: string | null
  doc_id?: string | null
  versio: string
  font_oficial: string
}

/** Recurs del registre curat (gestió per direcció, F2). */
export interface Recurs {
  id: string
  institucio_id: string
  titol: string
  descripcio: string
  tipus: string // url | document
  url?: string | null
  doc_id?: string | null
  etiquetes: string[]
  versio: string
  font_oficial: string
  vigent: boolean
  creat_per: string
  creat_el?: string | null
}

export interface ToolInfo {
  clau: string
  etiqueta: string
  descripcio: string
}

export interface RolInfo {
  clau: string
  etiqueta: string
}

/** Building blocks segurs per al wizard (amb etiquetes humanes). */
export interface CatalegSkills {
  tools: string[]
  rols: string[]
  tools_info: ToolInfo[]
  rols_info: RolInfo[]
}

/** Esborrany proposat per l'IA (per revisar/editar abans de desar). */
export interface EsborranySkill {
  nom: string
  descripcio: string
  system_prompt: string
  paraules_clau: string[]
  color: string
  rols_permesos: string[]
  tools: string[]
  normes_auto: string // guardrails que s'afegiran SEMPRE (transparència)
}

/** Plantilla curada d'assistent (P4): llesta per instanciar i ajustar. */
export interface PlantillaSkill {
  id: string
  titol: string
  categoria: string
  icona: string
  descripcio: string
  descripcio_generadora: string
  rols: string[]
  tools: string[]
  paraules_clau: string[]
  system_prompt: string
  color: string
}

/** Ús agregat d'un skill (P4): converses, missatges i últim ús (determinista). */
export interface MetricaSkill {
  skill_id: string
  converses: number
  missatges: number
  darrer_us: string | null
}

export interface InstitucioBreu {
  slug: string
  nom: string
}

/** Skill amb el nom del centre propietari (catàleg de compartició, superadmin). */
export interface SkillAmbInstitucio extends Skill {
  institucio_nom: string
}

export interface CompartirCataleg {
  skills: SkillAmbInstitucio[]
  institucions: InstitucioBreu[]
}

export interface CompartirResultat {
  institucio: string
  estat: 'creat' | 'omes'
  skill_id: string | null
}

/** Notificació calculada (recordatori de tasca o alerta d'absentisme). */
export interface Notificacio {
  id: string
  tipus: 'tasca' | 'absentisme'
  severitat: 'alta' | 'mitjana' | 'baixa'
  titol: string
  detall: string
  vista: string
  data: string | null
}

// ─── Documents indexats (GET /api/documents) ─────────────────────────────────

export interface DocumentEstat {
  doc_id: string
  filename: string
  tipus: 'pdf' | 'docx' | 'xlsx' | 'md' | 'html' | 'image'
  fragments: number
  verificat_el: string | null
  estat: string
  origen: string
  canal_rag: string
  sensibilitat: string
  exportable_ia: boolean
  metadades?: Record<string, unknown> | null
}
