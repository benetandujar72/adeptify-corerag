# INVARIANTS_REPORT — Secure Agent Kernel · F1

Leyenda: ✅ pasa · ❌ falla · ⏳ pendiente · ⚠️ parcial

**Evidencia global**: batería completa en `python:3.12.13` vía
`docker compose -f kernel/docker-compose.kernel.yml run --rm kernel pytest` →
**74 passed** (2026-06-04). Detalle por fichero en cada fila.

## Las 5 invariantes inviolables

| INV | Enunciado | Estado | Evidencia |
|---|---|---|---|
| INV-1 | El kernel nunca ejecuta código arbitrario (chat/doc/resultado) | ✅ | `test_inv1_cap_execucio_de_codi_arbitrari` (escaneo `app/*.py`: sin `eval(`/`exec(`/`os.system(`/`shell=True`/`__import__(`/`pickle.load`; `subprocess` solo en `sandbox.py`, argv fijo sin shell) + `test_inv1_eina_no_callable_rebutjada`. **Ejecución**: sandbox sin shell → `subprocess(["sh"])` da `FileNotFoundError` (verificado en vivo). Tools = callables pre-registrados. |
| INV-2 | RBAC en el kernel de herramientas, nunca en el LLM | ✅ | `test_invariants.py::test_inv2_rbac_al_kernel` + `test_tools.py::test_inv2_rbac_al_kernel_viewer_no_escriu`: `ToolKernel.invoke` llama `policy.enforce` ANTES de ejecutar; `executed_count==0` tras denegar. |
| INV-3 | Zero egress absoluto (regla de red, no de app) | ✅ (namespace+app) | App: `test_inv3_zero_egress_rebutja_extern` (`api.openai.com`→error; `external_calls()==0`). **Namespace** (verificado en vivo): sandbox `--network none`; `socket(AF_INET)`→`PermissionError` por seccomp; AF_UNIX permitido. Compose: loopback `127.0.0.1`. **Belt restante (STOP-4)**: regla nftables/iptables del host como capa extra → fase de red con aprobación. |
| INV-4 | Ningún agente crea/modifica/borra agentes en runtime sin definición firmada | ✅ | `test_invariants.py::test_inv4_sense_eines_dinamiques` (registrar tool fuera de allowlist → `AllowlistError`) + `test_allowlist.py::test_allowlist_manipulada_es_rebutjada` (firma GPG inválida → `AllowlistError`). Sin descubrimiento dinámico. |
| INV-5 | Secretos en vault de proceso; nunca en el contexto del modelo | ✅ | `test_invariants.py::test_inv5_cap_secret_al_context_del_model`: `assert_no_secrets(context, vault)` pasa para contexto limpio y lanza si un valor del vault aparece. El prompt builder no recibe el vault. |

## Criterios de aceptación F1 (14 ítems)

| # | Subfuncionalidad | Estado | Evidencia (test) |
|---|---|---|---|
| K1.1 | Orquestador determinista plan→act→observe | ✅ | `test_orchestrator.py` (5 tests); sin bucle implícito (ejecuta un Plan finito). |
| K1.2 | Límite pasos (10/25) + token_budget; BUDGET_EXCEEDED→humano | ✅ | `test_session.py::test_step_limit_atura_al_pas_4_amb_limit_3`, `::test_max_steps_acotat_al_sostre`, `::test_token_budget_escala`; `test_orchestrator.py::test_loop_limit_3_atura_al_pas_4`. |
| K1.3 | Contexto de sesión inmutable (SHA-256; mutación→excepción) | ✅ | `test_session.py::test_digest_estable_i_verificable`, `::test_mutacio_atribut_llanca`, `::test_data_es_read_only`. |
| K1.4 | Timeout absoluto externo, no cancelable desde dentro | ✅ | `test_session.py::test_deadline_expira_i_no_extensible`; `test_orchestrator.py::test_timeout_absolut_escala`. |
| K2.1 | Motor de políticas deny-by-default por rol+contexto | ✅ | `test_policy.py` (17 tests, matriz rol×riesgo); deny-by-default + deny explícito + requires_context. |
| K2.2 | Capability tokens JWT corta vida (TTL 60–300s; claims) | ✅ | `test_capabilities.py` (7 tests): TTL acotado, expirado/tool_id/session/firma → `CapabilityError`. |
| K2.3 | Taxonomía de riesgo (0..4) | ✅ | `test_risk.py` (9 tests). |
| K3.1 | Allowlist estática firmada GPG; sin descubrimiento dinámico | ✅ | `test_allowlist.py` (3); firma GPG real verificada (`pubkey.asc`/`tools.yaml.sig`); manipulación → error; `test_tools.py::test_registrar_eina_fora_allowlist_llanca`. |
| K3.2 | Validación de esquema de args y resultados | ✅ | `test_tools.py::test_k32_args_invalids_rebutjats`; validación pydantic de args (antes) y resultado (después) en `ToolKernel.invoke`. |
| K5.1 | Router de modelos locales; rechaza URLs externas | ✅ | `test_models_router.py::test_endpoint_openai_rebutjat_a_arrencada`, `::test_endpoint_local_acceptat`, `::test_external_calls_zero`. |
| K5.2 | Allowlist de modelos + verificación de hash del manifest | ✅ | `test_models_router.py::test_model_allowlist`, `::test_manifest_hash`. |
| K8.1 | Partición de memoria por tenant/sesión con RLS | ✅ | `test_rls.py::test_tenant_isolation`, `::test_cross_tenant_insert_blocked` (kernel_app no-superusuario, RLS FORCE). |
| K9.1 | Auditoría append-only con hash encadenado | ✅ | `test_audit.py` (chain + 1000<1s) + `test_rls.py::test_audit_append_only_i_cadena`, `::test_audit_update_delete_rebutjat` (trigger + REVOKE). |
| K9.2 | Registro de decisión y aprobación (propuesto vs ejecutado) | ✅ | `test_audit.py::test_decisio_propost_vs_executat` (PROPOSED/EXECUTED). |

### Pruebas obligatorias del backlog
| Prueba | Estado | Evidencia |
|---|---|---|
| Plan vacío ⇒ 0 tools; loop límite 3 se detiene en paso 4 | ✅ | `test_orchestrator.py::test_pla_buit_no_executa_cap_eina`, `::test_loop_limit_3_atura_al_pas_4` (executed_count==3). |
| `viewer` no ejecuta tools de escritura aunque lo pida | ✅ | `test_tools.py::test_inv2_rbac_al_kernel_viewer_no_escriu` (matriz de políticas en `test_policy.py`). |
| Token expirado / tool_id incorrecto rechazado por la tool | ✅ | `test_capabilities.py::test_token_caducat_rebutjat`, `::test_tool_id_incorrecte_rebutjat`. |
| Tool fuera de allowlist ⇒ excepción al inicio; firma GPG validada | ✅ | `test_tools.py::test_registrar_eina_fora_allowlist_llanca`; `test_allowlist.py` (firma GPG). |
| `api.openai.com` rechazado al arranque; `external_calls=0` | ✅ | `test_models_router.py::test_endpoint_openai_rebutjat_a_arrencada` + `::test_external_calls_zero`. |
| tenant A no ve datos de tenant B (RLS, usuario sin privilegios) | ✅ | `test_rls.py::test_tenant_isolation` (conexión como `kernel_app`). |
| UPDATE/DELETE en auditoría rechazado; cadena verificable <1s/1000 | ✅ | `test_rls.py::test_audit_update_delete_rebutjat`; `test_audit.py::test_verificacio_1000_entrades_sota_1s`. |

## F2 — defensas anti-injection + de datos (incremento 1)

Evidencia: batería completa `92 passed` (compose, Python 3.12.13, con `detect-secrets` + BD RLS), 2026-06-04.

| # | Subfuncionalidad | Estado | Evidencia (test) |
|---|---|---|---|
| K5.4 | Inyección del system prompt de seguridad (no eliminable) | ✅ | `test_guardrails.py::test_security_prompt_sempre_primer`, `::test_security_prompt_no_eliminable_ni_falsejable` |
| K7.1 | Detector de prompt injection (heurístico local) | ✅ | `test_guardrails.py::test_banc_injection_metriques`: **≥95% detección, ≤5% FP, ≤20ms** (banco 200 inj / 120 benignos, reproducible) |
| K7.2 | Separación instrucción vs dato (`<DATA>` no ejecutable) | ✅ | `test_guardrails.py::test_wrap_untrusted_neutralitza_breakout` (anti-breakout del delimitador) |
| K7.4 | Sanitización de resultados (truncado, control chars, NFC, zero-width) | ✅ | `test_guardrails.py::test_sanitize_*` |
| K8.3 | Filtro de secretos antes del contexto (detect-secrets) | ✅ | `test_secrets_filter.py`: redacta `sk-…`/clave privada/asignaciones; registra tipo; sin sobre-redactar prosa |
| K8.4 | Procedencia anti-envenenamiento del RAG (hash por chunk) | ✅ | `test_provenance.py`: descarta chunk con hash alterado o sin procedencia |
| K3.3 | Pin/firma SHA-256 de servidores MCP locales | ✅ | `test_mcp_pin.py`: rechaza sin pin conocido o con descriptor modificado |

**Refuerzo de invariantes**: INV-1 ahora también con guardrails de injection (contenido `<DATA>` nunca se ejecuta); INV-5 reforzada con el filtro de secretos antes del contexto (`test_inv5_*` + `test_secrets_filter`).

### F2 incremento 2 — sandbox de ejecución (verificado en vivo)

Config unit-testada (`test_sandbox_config.py`) + verificación live con `docker run` (evidencia en SECURITY_LOG):

| # | Subfuncionalidad | Estado | Evidencia |
|---|---|---|---|
| K4.1 | Contenedor efímero por invocación riesgo ≥2 (destruido al terminar) | ✅ | `--rm` + `requereix_sandbox(risk≥2)`; live: `docker ps -a` sin residual |
| K4.2 | seccomp restrictivo + capabilities mínimas | ✅ | `seccomp.json` (deny ptrace/mount/…; `socket(AF_INET)`→EPERM) + `--cap-drop ALL` + `no-new-privileges`; live: `PermissionError` |
| K4.3 | Egress denegado por namespace (solo loopback/Unix) | ✅ | `--network none`; live: AF_INET bloqueado, AF_UNIX permitido |
| K4.4 | cgroups v2 (CPU 0.5 / mem 256MB / 30s / 32 PIDs) | ✅ | flags `--cpus/--memory(=swap)/--pids-limit`; live: alloc >256MB → **exit 137 (OOM)**; wall-clock por timeout del runner |
| K4.5 | Sin shell de host en la imagen del sandbox | ✅ | Dockerfile elimina `sh/bash/dash`; live: `subprocess(["sh"])` → `FileNotFoundError` |

## F3-CORE — el humano en el bucle (incremento 1)

Evidencia: batería completa **128 passed** (124 non-RLS + 4 RLS, Python 3.12.13, compose con BD RLS), 2026-06-04. `test_approval.py`: 32 tests.

| # | Subfuncionalidad | Estado | Evidencia (test) |
|---|---|---|---|
| K6.1 | propose→approve: riesgo ≥2 sin token → PENDING_APPROVAL; no ejecuta | ✅ | `test_accio_risc_2_sense_aprovacio_es_pending` (`executed_count==0`), `test_accio_risc_2_amb_token_s_executa` |
| K6.1 | Token ligado a la acción exacta (anti confused-deputy/replay) | ✅ | `test_token_d_altra_accio_no_executa`, `test_token_no_lliga_amb_altra_accio`, `test_request_id_determinista_i_sensible_als_args` |
| K6.1 | Doble validación nivel 4 (2 aprobadores distintos) | ✅ | `test_nivell_4_necessita_dos_aprovadors_distints`, `test_nivell_4_una_aprovacio_no_executa` |
| K6.2 | Resumen NL ≤3 frases (qué hace / qué datos / reversibilidad), sin valores | ✅ | `test_resum_natural_tres_frases_i_reversibilitat`, `test_resum_no_filtra_valors_dels_args` |
| K6.4 | Anti-fatiga: >5 aprob/60s → cooldown + alerta admin | ✅ | `test_anti_fatiga_bloqueja_la_sisena_en_60s`, `::_finestra_lliscant`, `::_cooldown_caduca` |
| K9.2 | Cierre: PENDING_APPROVAL → APPROVED → EXECUTED; cadena verificable | ✅ | `test_cierre_auditoria_k92` |
| — | Token de aprobación ≠ capability (secreto y audiencia separados) | ✅ | `test_capability_token_no_serveix_com_aprovacio`, `test_token_falsificat_rebutjat`, `test_token_caducat_rebutjat` |

**Verificación clave del backlog F3** (INV-2 en la capa de herramientas, no en el modelo):
`test_inv2_rbac_abans_que_aprovacio` — un `viewer` que pide una escritura recibe `PolicyDenied`
en el kernel de herramientas (RBAC primero), **no** `ApprovalRequired`: la aprobación nunca
elude el RBAC. (`executed_count==0`.)

### Red-team adversarial F3-CORE (3 confirmados → CERRADOS, 0 refutados, 4 limpios)

| Refuerzo | Antes | Ahora | Evidencia |
|---|---|---|---|
| INV-2/F3 fail-closed | `gate=None` saltaba la compuerta ≥2 | sin gate ⇒ `ApprovalError` (fail-closed); opt-out `APPROVAL_DISABLED` auditable | `test_redteam1_fail_closed_sense_gate`, `::_opt_out_explicit_executa` |
| K6.3 distinción de aprobadores | `approver_id` sin normalizar | `_normalitza_aprovador` (strip+casefold, rechaza vacío) | `test_redteam2_aprovador_normalitzat_no_falseja_distincio`, `::_buit_o_invalid_rebutjat` |
| INV-1/INV-4 inmutabilidad eina | `Tool` mutable (swap de `fn`) | `@dataclass(frozen=True)` + guardia anti-reescritura en `register()` | `test_redteam3_tool_es_immutable`, `::_no_reescriptura_eina_registrada` |

Limpios (defensa verificada por el verificador independiente): forja de token (alg=none/HS/
secreto/audiencia), replay/confused-deputy, RBAC-bypass vía aprobación, fuga de secretos o
inyección en el resumen/auditoría. Cierre confirmado reproduciendo los 3 PoCs originales →
los 3 **bloqueados**.

### Impacto en las 5 invariantes
- **INV-1** reforzada: `Tool` inmutable (no swap de `fn` tras aprobación); `approval.py` sin
  eval/exec/subprocess (cubierto por `test_inv1_cap_execucio_de_codi_arbitrari`).
- **INV-2** confirmada: RBAC se evalúa antes que la compuerta; la aprobación es capa adicional,
  nunca sustituto del rol (red-team RBAC-bypass = limpio).
- **INV-4** reforzada: `register()` rechaza reescritura de una herramienta ya registrada.
- **INV-3 / INV-5** sin cambios de superficie; el secreto de aprobación vive en el vault y no
  entra en el contexto del modelo (resumen NL sin secretos ni valores).

## Notas / pendientes declarados
- **INV-3 a nivel de RED**: en F1 está garantizada la capa de aplicación (rechazo de endpoints no-LAN + `external_calls=0`) y el aislamiento loopback del compose. La **regla de red/firewall del host** (egress) es una acción de la lista STOP-4 → fase de red dedicada, con aprobación humana.
- **mTLS Core↔Suite** (CORE_SERVICE_TOKEN): fuera del alcance de F1 (kernel solo); fase posterior.
