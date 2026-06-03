// ─── Catàlegs de traducció (CA · ES · EU) ───────────────────────────────────
// Sistema lleuger sense dependència externa. Per defecte CA (institució catalana).
// Estructura plana de claus: cada idioma té el mateix conjunt; si una clau falta
// en una llengua, hi retorna el text del català (fallback) i la pròpia clau si tampoc.

export type Idioma = 'ca' | 'es' | 'eu'

export const IDIOMES_ADMESOS: Idioma[] = ['ca', 'es', 'eu']

export const NOM_IDIOMA: Record<Idioma, string> = {
  ca: 'Català',
  es: 'Castellano',
  eu: 'Euskara',
}

// Catàleg complet. Estructura: { clau: { ca, es, eu } }
// Tradueix només el que és visible per a l'usuari a les pantalles d'entrada
// (login, top-bar, configuració, missatges genèrics). La resta segueix en català
// fins que s'amplii — aquest framework permet anar afegint claus sense canvis.
const CATALEG: Record<string, Record<Idioma, string>> = {
  // ── App
  'app.titol': {
    ca: 'IA Nou Patufet',
    es: 'IA Nou Patufet',
    eu: 'IA Nou Patufet',
  },
  'app.lema': {
    ca: 'IA que protegeix',
    es: 'IA que protege',
    eu: 'Babesten duen AAa',
  },

  // ── Login
  'login.titol': { ca: "Accés a l'aplicatiu", es: 'Acceso a la aplicación', eu: 'Aplikaziorako sarbidea' },
  'login.centre': { ca: 'Centre', es: 'Centro', eu: 'Ikastetxea' },
  'login.usuari': { ca: 'Usuari', es: 'Usuario', eu: 'Erabiltzailea' },
  'login.contrasenya': { ca: 'Contrasenya', es: 'Contraseña', eu: 'Pasahitza' },
  'login.boto': { ca: 'Entra', es: 'Entrar', eu: 'Sartu' },
  'login.codi_mfa': { ca: 'Codi de verificació (MFA)', es: 'Código de verificación (MFA)', eu: 'Egiaztapen-kodea (MFA)' },
  'login.idioma': { ca: 'Idioma', es: 'Idioma', eu: 'Hizkuntza' },
  'login.error_credencials': {
    ca: 'Usuari o contrasenya incorrectes.',
    es: 'Usuario o contraseña incorrectos.',
    eu: 'Erabiltzaile edo pasahitz okerra.',
  },
  'login.carregant': { ca: 'Validant…', es: 'Validando…', eu: 'Egiaztatzen…' },

  // ── TopBar
  'menu.inici': { ca: 'Inici', es: 'Inicio', eu: 'Hasiera' },
  'menu.agents': { ca: 'Agents', es: 'Agentes', eu: 'Agenteak' },
  'menu.gestio': { ca: 'Gestió', es: 'Gestión', eu: 'Kudeaketa' },
  'menu.sistema': { ca: 'Sistema', es: 'Sistema', eu: 'Sistema' },
  'menu.documents': { ca: 'Documents', es: 'Documentos', eu: 'Dokumentuak' },
  'menu.configuracio': { ca: 'Configuració', es: 'Configuración', eu: 'Konfigurazioa' },
  'menu.administracio': { ca: 'Administració', es: 'Administración', eu: 'Administrazioa' },
  'menu.usuaris_centre': { ca: 'Usuaris del centre', es: 'Usuarios del centro', eu: 'Ikastetxeko erabiltzaileak' },
  'menu.estudi_skills': { ca: "Estudi d'Skills", es: 'Estudio de Skills', eu: 'Skill Estudioa' },
  'menu.documentacio_recursos': { ca: 'Documentació i recursos', es: 'Documentación y recursos', eu: 'Dokumentazioa eta baliabideak' },
  'menu.seguretat_xarxa': { ca: 'Seguretat de xarxa', es: 'Seguridad de red', eu: 'Sareko segurtasuna' },
  'menu.matricula': { ca: 'Matrícula', es: 'Matrícula', eu: 'Matrikula' },
  'menu.assistencia': { ca: 'Assistència', es: 'Asistencia', eu: 'Asistentzia' },
  'menu.tasques': { ca: 'Tasques', es: 'Tareas', eu: 'Eginbeharrak' },
  'menu.pagaments': { ca: 'Pagaments', es: 'Pagos', eu: 'Ordainketak' },
  'menu.expedients': { ca: 'Expedients', es: 'Expedientes', eu: 'Espedienteak' },
  'menu.importacio': { ca: 'Importació', es: 'Importación', eu: 'Inportazioa' },
  'menu.correu': { ca: 'Correu', es: 'Correo', eu: 'Posta' },
  'menu.avaluacio': { ca: 'Avaluació LOMLOE', es: 'Evaluación LOMLOE', eu: 'LOMLOE Ebaluazioa' },
  'menu.panell_pas': { ca: 'El meu dia', es: 'Mi día', eu: 'Nire eguna' },
  'menu.agenda': { ca: 'Agenda', es: 'Agenda', eu: 'Agenda' },
  'menu.registre': { ca: 'Registre E/S', es: 'Registro E/S', eu: 'S/I Erregistroa' },
  'menu.certificats': { ca: 'Certificats', es: 'Certificados', eu: 'Ziurtagiriak' },
  'menu.comunicacions': { ca: 'Circulars', es: 'Circulares', eu: 'Zirkularrak' },
  'menu.tanca_sessio': { ca: 'Tanca sessió', es: 'Cerrar sesión', eu: 'Itxi saioa' },

  // ── Configuració
  'config.titol': { ca: 'Configuració', es: 'Configuración', eu: 'Konfigurazioa' },
  'config.idioma_titol': { ca: 'Idioma de la interfície', es: 'Idioma de la interfaz', eu: 'Interfazearen hizkuntza' },
  'config.idioma_desc': {
    ca: "L'idioma de l'aplicació. Els missatges automàtics i els documents oficials continuen sortint en català per defecte (configuració del centre).",
    es: 'El idioma de la aplicación. Los mensajes automáticos y los documentos oficiales siguen saliendo en catalán por defecto (configuración del centro).',
    eu: 'Aplikazioaren hizkuntza. Mezu automatikoak eta dokumentu ofizialak katalanez ateratzen jarraitzen dute lehenespenez (ikastetxearen konfigurazioa).',
  },
  'config.idioma_desat': { ca: 'Idioma desat.', es: 'Idioma guardado.', eu: 'Hizkuntza gordeta.' },

  // ── Comuns
  'comu.desa': { ca: 'Desa', es: 'Guardar', eu: 'Gorde' },
  'comu.cancella': { ca: 'Cancel·la', es: 'Cancelar', eu: 'Utzi' },
  'comu.carregant': { ca: 'Carregant…', es: 'Cargando…', eu: 'Kargatzen…' },
  'comu.error': { ca: 'Error', es: 'Error', eu: 'Errorea' },
  'comu.cerca': { ca: 'Cerca…', es: 'Buscar…', eu: 'Bilatu…' },
  'comu.tanca': { ca: 'Tanca', es: 'Cerrar', eu: 'Itxi' },
  'comu.refresca': { ca: 'Refresca', es: 'Actualizar', eu: 'Eguneratu' },

  // ── Inici (vista de xat)
  'inici.benvinguda': {
    ca: 'Benvingut/da. Tria un agent per començar.',
    es: 'Bienvenido/a. Elige un agente para empezar.',
    eu: 'Ongi etorri. Aukeratu agente bat hasteko.',
  },
}

export function tradueix(clau: string, idioma: Idioma): string {
  const fila = CATALEG[clau]
  if (!fila) return clau
  return fila[idioma] || fila.ca || clau
}
