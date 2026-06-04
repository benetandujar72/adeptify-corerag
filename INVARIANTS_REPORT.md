# INVARIANTS_REPORT — Secure Agent Kernel · F1

Leyenda: ✅ pasa · ❌ falla · ⏳ pendiente · ⚠️ parcial

**Evidencia global**: batería completa en `python:3.12.13` vía
`docker compose -f kernel/docker-compose.kernel.yml run --rm kernel pytest` →
**74 passed** (2026-06-04). Detalle por fichero en cada fila.

## Las 5 invariantes inviolables

| INV | Enunciado | Estado | Evidencia |
|---|---|---|---|
| INV-1 | El kernel nunca ejecuta código arbitrario (chat/doc/resultado) | ✅ | `test_invariants.py::test_inv1_cap_execucio_de_codi_arbitrari` (escaneo de `app/*.py`: sin `eval(`/`exec(`/`subprocess`/`os.system(`/`__import__(`/`pickle.load`) + `test_inv1_eina_no_callable_rebutjada` (registrar fn no-callable → `ArbitraryCodeError`). Las tools son callables pre-registrados. |
| INV-2 | RBAC en el kernel de herramientas, nunca en el LLM | ✅ | `test_invariants.py::test_inv2_rbac_al_kernel` + `test_tools.py::test_inv2_rbac_al_kernel_viewer_no_escriu`: `ToolKernel.invoke` llama `policy.enforce` ANTES de ejecutar; `executed_count==0` tras denegar. |
| INV-3 | Zero egress (regla de red, no de app) | ⚠️ (capa app) | `test_invariants.py::test_inv3_zero_egress_rebutja_extern`: `ModelRouter(base_url=api.openai.com)` → `ExternalEndpointError`; `external_calls()==0`. **Pendiente fase de red** (firewall/egress a nivel host) → ver SECURITY_LOG. Compose: BD/kernel solo en `127.0.0.1`. |
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

**Pendiente F2 (incremento 2)**: sandbox de ejecución K4.1–K4.5 (contenedor efímero, seccomp, cgroups v2, `--network none`, sin shell). Cierra INV-1 (execve bloqueado) e INV-3 (egress por namespace) a nivel de ejecución.

## Notas / pendientes declarados
- **INV-3 a nivel de RED**: en F1 está garantizada la capa de aplicación (rechazo de endpoints no-LAN + `external_calls=0`) y el aislamiento loopback del compose. La **regla de red/firewall del host** (egress) es una acción de la lista STOP-4 → fase de red dedicada, con aprobación humana.
- **mTLS Core↔Suite** (CORE_SERVICE_TOKEN): fuera del alcance de F1 (kernel solo); fase posterior.
