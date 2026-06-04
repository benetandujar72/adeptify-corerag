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
- Rama local `feat/secure-kernel-f1`. **STOP**: no se ha hecho `git push` ni se ha
  creado/modificado ningún remoto (esperando "sí" humano).
