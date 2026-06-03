# Security Policy · Política de seguretat · Política de seguridad

> **Project:** `adeptify-corerag` — Adeptify · «IA que protegeix»
> **Contact:** bandujar@xtec.cat · (English · Català · Castellano below)

`adeptify-corerag` handles education settings where data sovereignty and the protection of minors' data are core requirements. Please read this policy before reporting.

---

## English

### Reporting a vulnerability
- **Do not open a public issue** for security problems.
- Use **GitHub Security Advisories** ("Report a vulnerability") on this repository, or email **bandujar@xtec.cat** with the subject `SECURITY: <short summary>`.
- Please include: affected version/commit, environment, reproduction steps, impact, and (if possible) a proof of concept. PGP key available on request.
- We aim to acknowledge within **5 working days** and to agree a remediation timeline with you. We follow **coordinated disclosure**: please give us a reasonable window before publishing.
- Acting in good faith under this policy, we will not pursue legal action; do not access third-party data, degrade service, or run automated mass scans against production.

### Scope
- **In scope:** the source code of `adeptify-corerag` (RAG/CAG engine, API, base auth/RBAC/audit, ingestion, gateway).
- **Out of scope:** third-party deployments you do not control, social engineering, and the private `adeptify-suiterag` modules (report those privately to the same contact).

### Security & compliance principles
- **Zero egress.** Inference and data are 100% local (Ollama/vLLM); no third-party commercial API on the critical path.
- **Human oversight (EU AI Act, Art. 14).** The AI proposes drafts; a person validates and executes.
- **Data sovereignty (GDPR).** No real minors' PII in this repository or its history; validation uses **synthetic data** only.
- **No secrets in git.** No `.env`, keys, tokens or credentials are committed; secret scanning and a pre-commit hook are expected.
- **Traceability.** Access is logged with its legal basis.

### Supported versions
The latest released minor version receives security fixes. Older versions are best-effort.

### Hardening reminders for operators
Before production: change `JWT_SECRET` and all seed passwords, enable MFA for admin/management roles, restrict remote access (`ACCES_REMOT_ADMIN_ONLY`), serve over HTTPS behind a trusted reverse proxy, and run the built-in production check.

---

## Català

### Com reportar una vulnerabilitat
- **No obris cap issue pública** per a problemes de seguretat.
- Fes servir els **GitHub Security Advisories** («Report a vulnerability») d'aquest repositori, o escriu a **bandujar@xtec.cat** amb l'assumpte `SECURITY: <resum breu>`.
- Indica: versió/commit afectat, entorn, passos de reproducció, impacte i, si pots, una prova de concepte. Clau PGP disponible si la demanes.
- Acusarem recepció en **5 dies laborables** i acordarem amb tu un calendari de correcció. Seguim la **divulgació coordinada**: dona'ns un marge raonable abans de publicar.
- Si actues de bona fe segons aquesta política, no emprendrem accions legals; no accedeixis a dades de tercers, no degradis el servei ni facis escanejos massius automatitzats contra producció.

### Abast
- **Dins l'abast:** el codi font d'`adeptify-corerag` (motor RAG/CAG, API, auth/RBAC/auditoria base, ingesta, passarel·la).
- **Fora d'abast:** desplegaments de tercers que no controles, enginyeria social i els mòduls privats d'`adeptify-suiterag` (reporta'ls de manera privada al mateix contacte).

### Principis de seguretat i compliment
- **Zero egress.** Inferència i dades 100% locals (Ollama/vLLM); cap API comercial de tercers al camí crític.
- **Supervisió humana (AI Act, art. 14).** La IA proposa esborranys; una persona valida i executa.
- **Sobirania de dades (RGPD).** Cap PII real de menors en aquest repositori ni al seu historial; la validació usa només **dades sintètiques**.
- **Sense secrets a git.** No es versionen `.env`, claus, tokens ni credencials; s'espera secret scanning i un pre-commit hook.
- **Traçabilitat.** Els accessos es registren amb la seva base legal.

### Versions suportades
La darrera versió menor publicada rep correccions de seguretat. Les versions anteriors, segons disponibilitat.

### Recordatoris d'enduriment per a operadors
Abans de producció: canvia `JWT_SECRET` i totes les contrasenyes de seed, activa MFA per als rols d'administració/gestió, restringeix l'accés remot (`ACCES_REMOT_ADMIN_ONLY`), serveix per HTTPS darrere un reverse proxy de confiança i executa la verificació de producció integrada.

---

## Castellano

### Cómo reportar una vulnerabilidad
- **No abras una issue pública** para problemas de seguridad.
- Usa los **GitHub Security Advisories** («Report a vulnerability») de este repositorio, o escribe a **bandujar@xtec.cat** con el asunto `SECURITY: <resumen breve>`.
- Indica: versión/commit afectado, entorno, pasos de reproducción, impacto y, si puedes, una prueba de concepto. Clave PGP disponible si la pides.
- Acusaremos recibo en **5 días laborables** y acordaremos contigo un calendario de corrección. Seguimos la **divulgación coordinada**: danos un margen razonable antes de publicar.
- Si actúas de buena fe según esta política, no emprenderemos acciones legales; no accedas a datos de terceros, no degrades el servicio ni hagas escaneos masivos automatizados contra producción.

### Alcance
- **En alcance:** el código fuente de `adeptify-corerag` (motor RAG/CAG, API, auth/RBAC/auditoría base, ingesta, pasarela).
- **Fuera de alcance:** despliegues de terceros que no controlas, ingeniería social y los módulos privados de `adeptify-suiterag` (repórtalos de forma privada al mismo contacto).

### Principios de seguridad y cumplimiento
- **Zero egress.** Inferencia y datos 100% locales (Ollama/vLLM); ninguna API comercial de terceros en el camino crítico.
- **Supervisión humana (AI Act, art. 14).** La IA propone borradores; una persona valida y ejecuta.
- **Soberanía de datos (RGPD).** Ninguna PII real de menores en este repositorio ni en su historial; la validación usa solo **datos sintéticos**.
- **Sin secretos en git.** No se versionan `.env`, claves, tokens ni credenciales; se espera secret scanning y un pre-commit hook.
- **Trazabilidad.** Los accesos se registran con su base legal.

### Versiones soportadas
La última versión menor publicada recibe correcciones de seguridad. Las versiones anteriores, según disponibilidad.

### Recordatorios de endurecimiento para operadores
Antes de producción: cambia `JWT_SECRET` y todas las contraseñas de seed, activa MFA para los roles de administración/gestión, restringe el acceso remoto (`ACCES_REMOT_ADMIN_ONLY`), sirve por HTTPS tras un reverse proxy de confianza y ejecuta la verificación de producción integrada.
