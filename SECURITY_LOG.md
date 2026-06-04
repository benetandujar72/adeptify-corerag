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
