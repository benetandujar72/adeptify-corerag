# SECURITY_LOG — Secure Agent Kernel (Adeptify) · F1

Bitácora append-only de la implementación del kernel seguro. Repo: `adeptify-corerag` (AGPL).
Sin dominio escolar, sin PII: solo datos sintéticos.

> Rama de trabajo: `feat/secure-kernel-f1`. **Nada se publica sin "sí" humano** (STOP gates).

---

## 2026-06-04 · F1.0 — Plan y decisiones de arquitectura

**Objetivo F1**: núcleo determinista + maquinaria de seguridad base (K1.1–K9.2).

### Ubicación y aislamiento
- El kernel vive en `adeptify-corerag/kernel/` como **paquete aislado** con su propia imagen
  (`python:3.12-slim`), `requirements.txt` mínimo (sin la pila ML del RAG), su propia BD Postgres
  con RLS y su `docker-compose.kernel.yml`. **No toca** `backend/` (el RAG existente sigue intacto).
- Motivo: superficie mínima, separación de responsabilidades, y la "frontera de proceso" del kernel.

### Decisiones de dependencias (ninguna dispara STOP-5)
| Necesidad | Elección | Motivo |
|---|---|---|
| Framework de agente | **Propio** (orquestador determinista) | Stack lo exige; cero frameworks externos |
| Motor de políticas | **Propio** (deny-by-default) | Evita OPA → cero infra/binarios externos |
| Capability tokens | **PyJWT** (ya en corerag) | Mínima superficie vs python-jose; ya vetado en el repo |
| Validación esquema | **pydantic v2** | Cero deps extra (la alternativa jsonschema sobra) |
| Firma allowlist | **python-gnupg** | Listado en el stack aprobado; `gpg` en la imagen |
| Parseo YAML | **strictyaml** | Listado en el stack aprobado; parseo seguro |
| BD / RLS | **Postgres 16 + RLS** (`psycopg`) | Listado; partición por tenant/sesión |

`python-gnupg` y `strictyaml` son nuevas **al kernel** pero figuran en el stack aprobado del rol →
no requieren STOP-5. Se documentan aquí por transparencia.

### Mapa de módulos (`kernel/app/`)
- `risk.py` — K2.3 taxonomía de riesgo (0..4).
- `session.py` — K1.3 contexto inmutable (SHA-256), K1.2 límites de pasos/budget, K1.4 timeout absoluto.
- `policy.py` — K2.1 motor allow/deny por rol+contexto, **deny-by-default**.
- `capabilities.py` — K2.2 capability tokens JWT de vida corta (TTL 60–300s).
- `allowlist.py` — K3.1 allowlist estática firmada GPG (sin descubrimiento dinámico) + K3.2 validación de esquema.
- `tools.py` — kernel de herramientas: **RBAC aquí, nunca en el LLM (INV-2)**; registro rechaza no-allowlisted.
- `models_router.py` — K5.1 router de modelos locales (rechaza URLs externas), K5.2 allowlist + hash de manifest.
- `audit.py` — K9.1 auditoría append-only con hash encadenado, K9.2 registro de decisiones (propuesto vs ejecutado).
- `db.py` — K8.1 partición por tenant/sesión con RLS.
- `orchestrator.py` — K1.1 plan→act→observe (sin bucle implícito).
- `main.py` — app FastAPI (health + endpoints mínimos).

### Banco de invariantes (Prompt V parcial)
Cada invariante se prueba en `tests/test_invariants.py` además de los tests por K. Estado en `INVARIANTS_REPORT.md`.

---

## 2026-06-04 · F1.1 — Ejecución

**Entorno de pruebas**: imagen `adeptify-kernel:f1` (`python:3.12-slim` + gnupg + deps
mínimas). BD `postgres:16-alpine` con RLS vía `docker-compose.kernel.yml`.

### Firma GPG del allowlist (K3.1)
- Clave RSA-3072 generada DENTRO de un contenedor efímero (`gpg --batch --gen-key`),
  clave privada NO persistida ni versionada. Firmado `tools.yaml` → `tools.yaml.sig`
  (detached, armored) + export `pubkey.asc`. Verificación: `gpg --verify` →
  `Good signature`. `.gitattributes` fija `-text` en los ficheros del allowlist para
  que CRLF no rompa la firma en checkout.

### Implementación (módulos `kernel/app/`)
risk · session (immutable+budget+deadline) · policy (deny-by-default) · capabilities
(PyJWT) · allowlist (GPG+strictyaml) · tools (RBAC+schema) · models_router · audit
(hash chain) · db (RLS) · orchestrator · main · vault (INV-5).

### Batería de tests
- Pura (en imagen, sin BD): `docker run --rm -v kernel:/app adeptify-kernel:f1 pytest`
  → **70 passed** (Python 3.12.13).
- Completa (compose, con BD RLS): `docker compose -f docker-compose.kernel.yml run --rm
  kernel pytest` → **74 passed** (incluye `test_rls.py`: aislamiento por tenant,
  insert cross-tenant bloqueado, auditoría append-only con UPDATE/DELETE rechazado).
- Cobertura de los 14 ítems + 5 invariantes + 7 pruebas obligatorias → ver
  `INVARIANTS_REPORT.md` (todas ✅, salvo INV-3 a nivel de RED, declarada como STOP-4).

### Decisión sobre INV-3 (zero egress)
- F1 garantiza la capa de **aplicación** (router rechaza endpoints no-LAN al arranque;
  `external_calls=0`) y el **aislamiento loopback** del compose (`127.0.0.1`).
- La **regla de red/firewall del host** es STOP-4 (toca egress del host) → requiere
  aprobación humana explícita en una fase de red dedicada. NO ejecutada.

### Estado de publicación
- Rama `feat/secure-kernel-f1`. **Push APROBADO por humano ("procede")** → publicado a
  `origin` (remoto privado) el 2026-06-04. No toca `master` ni la visibilidad.

---

## 2026-06-04 · F2 — "encerrar el poder del agente"

Plan: dos incrementos. (1) defensas anti prompt-injection + de datos (pure-Python, sin
STOP); (2) sandbox de ejecución efímero (K4.x) con seccomp/cgroups/`--network none`.

### Decisiones F2
- **K4.3 zero-egress**: a nivel de **namespace** del contenedor (`--network none` por
  invocación). NO se toca el firewall del host (eso sería STOP-4) → sin STOP.
- **K7.1 detector de injection**: **heurístico local** (sin descargar pesos de modelo)
  → evita el STOP de descarga de guardrails. Banco reproducible de ~200 injections +
  benignos; objetivo ≥95% detección, ≤5% FP, ≤20ms.
- **K8.3**: `detect-secrets` (stack aprobado) + regex de alta precisión (sk-, claves).
- Sin nuevos frameworks; deps nuevas al kernel: `detect-secrets` (del stack aprobado).

### Incremento 1 (este paso): módulos `kernel/app/`
guardrails.py (K5.4 system-prompt no eliminable · K7.1 detector · K7.2 <DATA> ·
K7.4 sanitización) · secrets_filter.py (K8.3) · provenance.py (K8.4) · mcp_pin.py (K3.3).

**Resultado incremento 1**: batería completa `92 passed` (compose, Python 3.12.13,
`detect-secrets` instalado + BD RLS). Banco de injection: ≥95% detección, ≤5% FP, ≤20ms
(200 inj / 120 benignos, reproducible). Hallazgo y corrección registrados:
- El test naíf de INV-1 (scan por substring) marcaba `guardrails.py` por contener la
  PALABRA `subprocess` dentro de un patrón de DETECCIÓN (no una llamada). Corregido:
  el test ahora detecta CRIDAS reales (regex con lookbehind), no menciones.
- `detect-secrets` con todos los plugins sobre-redactaba prosa (entropía/keyword).
  Corregido: solo plugins de alta precisión (AWS/JWT/PrivateKey/…); el core es regex.

### Incremento 2 (sandbox de ejecución K4.1–K4.5) — verificado en vivo

Imagen `adeptify-sandbox:f2` (python:3.12-slim SIN shell) + `seccomp.json` + `app/sandbox.py`
(`build_docker_args` puro + `run_sandboxed`). `subprocess` SOLO aquí (argv fijo, sin shell);
INV-1 test refinado en consecuencia. Verificación live (`docker run` directo):

- K4.5/INV-1 sin shell: `subprocess(["sh","-c",…])` → `FileNotFoundError` → `OK_no_shell`.
- K4.2 seccomp: `socket(AF_INET)` → `PermissionError` (EPERM) → `OK_seccomp_EPERM`.
- K4.3/INV-3 egress: `--network none`; AF_UNIX permitido, AF_INET bloqueado → `OK_no_inet`.
- K4.4 cgroups: `bytearray(400MB)` con `--memory 256m` (sin swap) → **exit 137 (OOM-killed)**;
  wall-clock por timeout del runner (kill verificado).
- K4.1 efímero: `--rm` → `docker ps -a` sin contenedor residual.

Batería: **92 non-RLS + 4 RLS** verde (py3.12). `--network none` es per-contenedor (namespace),
NO toca el firewall del host → sin STOP-4. La regla de red del host queda como belt adicional
(STOP-4, pendiente de aprobación).

---

## 2026-06-04 · F3 — "el humano en el bucle y el cumplimiento" (PLAN)

Maquinaria en `adeptify-corerag` (core); semántica de dominio (PII de menores) en
`adeptify-suiterag` (suite). Frontera de proceso mTLS + CORE_SERVICE_TOKEN.

### Incrementos previstos
1. **F3-CORE** (pure-Python, sin STOP): K6.1 propose→approve (acción riesgo ≥2 →
   PENDING_APPROVAL; sin token de aprobación NO ejecuta) · K6.2 diff/resumen NL (≤3
   frases: qué hace, qué datos toca, reversibilidad) · K6.4 anti-fatiga (>5 aprob/60s →
   cooldown + aviso admin) · K9.2 cierre (registro propuesto/ejecutado para todo ≥2).
2. **F3-SUITE** (PII): K2.4 políticas PII menores (deny salvo tutor/admin; opt-in
   dirección auditado) · K6.3 doble validación nivel 4 (dos roles distintos) · K6.5
   marcado art.50 irrenunciable · K7.3 DLP Presidio (regex fallback si no hay modelo) ·
   K7.5 clasificador contenido inapropiado local · K8.2 retención/purga + derecho al
   olvido · K9.3 export auditoría (art.14) + K9.4 alertas de anomalías.
3. **Frontera mTLS** Core↔Suite + test de contrato en CI (petición core sin mTLS no
   accede a datos del suite).

### STOP gates F3 (a respetar)
- Conectores reales (Alèxia/Workspace/banca): NUNCA producción/datos reales sin "sí";
  solo sandbox/sintético.
- Opt-in de PII con datos reales: exige EIPD/DPD validados.
- mTLS: generar/instalar certificados es infra; si toca red/host → mostrar y esperar "sí".

### Decisión de deps
- Presidio (stack aprobado) para K7.3, con DLP regex de respaldo (evita bloqueo por
  descarga de modelo spaCy). cryptography para mTLS (verificar si ya está; si no, STOP-5).

### Estado
Plan registrado. Implementación pendiente de reanudar tras `/compact` (estado completo
en git: rama feat/secure-kernel-f1 @ 7ba8b0e + este log + INVARIANTS_REPORT.md).

---

## 2026-06-04 · F3-CORE — Ejecución (incremento 1: la compuerta humana)

Maquinaria pure-Python en `adeptify-corerag` (sin STOP gate). Sin dependencias nuevas
(solo PyJWT/hashlib/secrets, ya en el stack). **Sin push** (F3 exige "sí" → STOP-2).

### Implementación (`kernel/app/`)
- **`approval.py`** (nuevo) — `ApprovalGate` (propose→approve→verify_token), `request_id`
  determinista = SHA-256(sesión+tenant+tool+args+riesgo), `resum_natural` (K6.2, 3 frases),
  `aprovacions_requerides` (≥2→1, nivel 4→2 distintos), anti-fatiga (K6.4).
- **`tools.py`** — `ToolKernel` gana `approval_gate`; `invoke()` aplica la compuerta DESPUÉS
  del RBAC (INV-2) y ANTES de capability/ejecución; `request_id_for()` para el orquestador.
- **`orchestrator.py`** — `run(..., approvals=)`; `ApprovalRequired` → `escalated=True`.
- **`errors.py`** — `ApprovalRequired` (escalado, lleva la request) / `ApprovalError` /
  `ApprovalRateLimited`. **`audit.py`** — estados `PENDING_APPROVAL` / `APPROVED`.
- **`config.py` / `.env.example`** — TTL/ventana/cooldown + `KERNEL_APPROVAL_SECRET`
  (secret separado del de capability; vive en el vault — INV-5).

### Batería (compose, Python 3.12.13, con BD RLS)
- `docker compose ... run --rm --build kernel pytest` → **128 passed** (124 non-RLS + 4 RLS).
- `test_approval.py`: 32 tests (26 K6.x + 6 regresiones del red-team).
- Criterios clave verificados con evidencia: acción nivel 2 sin aprobación ⇒ `ApprovalRequired`
  (`executed_count==0`); nivel 4 con una sola aprobación NO se ejecuta; token ligado a la
  acción exacta (anti confused-deputy); **INV-2**: viewer→write da `PolicyDenied` en la capa
  de herramientas, no `ApprovalRequired` (el RBAC va primero y la aprobación no lo elude).

### Red-team adversarial (workflow, 7 clases de ataque × verificación independiente)
Resultado: **3 confirmados (CRÍTICOS) · 0 refutados · 4 limpios**. Limpios (defensa
verificada): forja de token (alg=none/HS/secreto/aud), replay/confused-deputy, RBAC-bypass
vía aprobación, fuga de secretos/inyección en el resumen/auditoría. Confirmados y **CERRADOS**:

| # | Hallazgo | Causa | Corrección | Evidencia |
|---|---|---|---|---|
| 1 | `approval_gate=None` saltaba la compuerta para riesgo ≥2 (footgun de config) | gate opcional, default silencioso | **Fail-closed**: sin gate, riesgo ≥2 → `ApprovalError`; opt-out EXPLÍCITO `APPROVAL_DISABLED` (auditable) | `test_redteam1_*`; PoC original → `ATAC#1 BLOQUEJAT (executed=0)` |
| 2 | Variantes de mayúsc./espacios del `approver_id` falseaban "2 aprobadores distintos" (nivel 4) | sin normalizar el id | `_normalitza_aprovador` (strip+casefold, rechaza vacío/no-str); ventana anti-fatiga a `<=` | `test_redteam2_*`; PoC → `'Alice'/'alice'=1 sol aprovador → PENDING` |
| 3 | `Tool` mutable → sustituir `fn` tras la aprobación (INV-1/INV-4) | `@dataclass` sin frozen | `@dataclass(frozen=True)` + guardia anti-reescritura en `register()` | `test_redteam3_*`; PoC → `Tool immutable (FrozenInstanceError)` |

Verificación de cierre: reproducidos los 3 PoCs originales contra el código pegado → los 3
**bloqueados**. Batería completa sigue en **128 passed**.

### Secretos (DoD)
- gitleaks **git-mode: "no leaks found"** (9 commits + working tree trackeado).
- `.env` y `kernel/.env` están gitignored y **no trackeados** (`git ls-files` vacío); los
  únicos hits de `--no-git` son esos `.env` locales, nunca en git. Ficheros nuevos limpios.

### Estado de publicación
Rama `feat/secure-kernel-f1`, **push APROBADO ("procede")** → `ace2a4f` (remoto privado).

---

## 2026-06-05 · Red-team TOTAL i FINAL — troballes del CORE

Assalt complet (12 objectius CORE+SUITE; vegeu `adeptify-suiterag/SECURITY_LOG.md` per al
detall del SUITE). Veredicte de les 5 invariants: **INV-2/INV-3/INV-4/INV-5 HOLDS**;
**INV-1 AT-RISK** (vegeu obert, sota). Al CORE:

### Confirmat i TANCAT (aquest canvi)
| Sev | Troballa | Correcció | Evidència |
|---|---|---|---|
| medium (hardening INV-2) | `PolicyEngine` desava `_allow`/`_deny` en LLISTES mutables → codi in-process podia afegir regles i escalar el RBAC | `app/policy.py`: `tuple(...)` immutable | `test_policy.py::test_redteam_politica_immutable_no_mutable_in_process` (125 passed) |

NOTA: el bypass requereix execució de codi al procés del kernel (post-INV-1); l'autoritat de
decisió segueix al kernel. És defensa en profunditat (elimina una via de tampering).

### REFUTAT
- INV-4 «mutació d'eines en runtime»: el `_tools` és mutable però no hi ha cap via des de
  codi no fiable (xat/model/HTTP) per obtenir-ne referència; l'allowlist signada s'imposa al
  registre. Hardening possible (frozen mapping), no bypass.

### OBERT (declarat; requereix un increment dedicat)
- **[CRITIC · INV-1 camí viu] Guardrails anti-injection = codi mort**: `app/guardrails.py`
  (detect_injection, K5.4 system-prompt no eliminable, wrap_untrusted, sanitize_result) està
  definit i unit-testejat al KERNEL però NO s'invoca al punt real de delegació a l'LLM
  (`adeptify-corerag/backend/app/api/routes_servei.py`), que concatena instruccions+evidència
  en cru i usa GUARDRAIL_HUMANISME (no el system-prompt no eliminable). El kernel no fa
  eval/exec (cap RCE), però la injecció indirecta cap a l'LLM NO està mitigada al camí viu.
  Pendent: cablejar els guardrails a `routes_servei.py` (anteposar SECURITY_SYSTEM_PROMPT,
  `wrap_untrusted` a l'evidència, `detect_injection` fail-closed, `sanitize_result` a la sortida).
