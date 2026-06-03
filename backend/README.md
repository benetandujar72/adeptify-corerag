# Backend — IA Nou Patufet (RAG self-hosted multi-agent)

Backend en **Python 3.11 + FastAPI** que implementa el contracte
[`../API_CONTRACT.md`](../API_CONTRACT.md): orquestrador LangGraph, 4 agents
especialitzats, RAG (pgvector + rerank), capa MCP, RBAC i auditoria.

> **Principi rector:** tota inferència LLM passa per un client
> **OpenAI-compatible** apuntant a `OPENAI_BASE_URL` (Ollama en dev, vLLM en
> GPU). **Mai** es criden OpenAI/Anthropic/Gemini reals. El comptador
> `crides_externes` de `/api/system/status` ha de ser sempre `0`.

## Estructura

```
backend/
├── app/
│   ├── core/          · config, seguretat (JWT/RBAC), auditoria, telemetria privadesa
│   ├── db/            · sessió SQLAlchemy + models ORM (pgvector)
│   ├── ingest/        · loaders (PDF/DOCX/MD/HTML) + chunking semàntic + pipeline
│   ├── rag/           · client LLM, embeddings bge-m3, reranker bge, retriever
│   ├── agents/        · registre dels 4 agents (persona, prompt CA, rols, tools)
│   ├── mcp/           · servidor MCP intern + tools (drive, calendari, NOFC/PEC…)
│   ├── orchestrator/  · graf LangGraph (routing→RBAC→RAG→genera) + memòria
│   ├── api/           · esquemes Pydantic + routers FastAPI + errors
│   └── main.py        · aplicació FastAPI (factory crea_app)
├── db/init/01_schema.sql   · esquema Postgres+pgvector (executat per docker-entrypoint)
├── scripts/seed.py         · ingesta de sample_data + usuaris demo per rol
├── tests/                  · pytest (sense GPU ni models descarregats)
├── Dockerfile              · python:3.11-slim, uvicorn :8000
└── requirements.txt
```

## Com s'executa

### Amb Docker Compose (recomanat)

Des de l'arrel del repo, amb el perfil `dev` (Ollama, sense GPU):

```bash
cp .env.example .env
docker compose --profile dev up --build
# API i docs: http://localhost:8000/docs
```

El servei `db` crea l'esquema automàticament des de `backend/db/init/01_schema.sql`.
Per al model de dev cal tenir el model descarregat a Ollama, p. ex.:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

### Seed (ingesta + usuaris demo)

```bash
docker compose exec backend python -m scripts.seed
```

Ingesta tots els documents de `/app/sample_data` (muntada read-only) i imprimeix
un token JWT demo per a cada rol (docent, alumne, familia, direccio).

### Local sense Docker

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
# Cal una DATABASE_URL a un Postgres+pgvector i un OPENAI_BASE_URL viu (Ollama).
uvicorn app.main:app --reload --port 8000
```

## Com es corren els tests

Els tests **no** requereixen GPU, Postgres ni descàrrega de models: usen SQLite
en memòria i **dobles** per al client LLM, els embeddings i el reranker.

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate
# N'hi ha prou amb les dependències lleugeres (sense FlagEmbedding/torch):
pip install fastapi "uvicorn[standard]" python-multipart sse-starlette \
    pydantic pydantic-settings SQLAlchemy pgvector openai langgraph PyJWT \
    pypdf python-docx beautifulsoup4 markdown-it-py pytest httpx
pytest
```

> **Nota d'instal·lació:** `FlagEmbedding` i `sentence-transformers` (amb
> `torch`) són dependències pesades necessàries **en runtime** per als
> embeddings i el reranker reals, però **no** per als tests (s'embeliquen amb
> `app.rag.embeddings.set_embedder`, `set_reranker` i `app.rag.llm.set_llm_client`).
> Si la instal·lació de `torch` falla al teu entorn, els tests segueixen passant
> amb el subconjunt lleuger de dependències de dalt.

Cobertura dels tests (38 casos): routing de l'orquestrador, detecció de llengua
CA/ES, RBAC (agents per rol, 403/404), contracte d'endpoints (TestClient),
format de resposta de `/api/chat` (no-stream i SSE), ingesta/chunking, capa MCP
i garantia de privadesa (bloqueig de dominis de tercers + `crides_externes=0`).

## Com es corre l'avaluació (eval)

El runner `eval/run_eval.py` executa l'eval set
[`../docs/eval/eval_set_ca.jsonl`](../docs/eval/eval_set_ca.jsonl) pel **mateix
camí intern** que `POST /api/chat` (orquestrador → routing → RAG → genera),
**sense aixecar cap servidor HTTP**. Per a cada pregunta mesura tres dimensions:

- **Routing accuracy:** l'agent triat per l'orquestrador == `agent_esperat`.
- **Groundedness / contains:** la resposta conté els strings de
  `resposta_esperada_conté` (comparació normalitzada: minúscules, sense accents,
  espais col·lapsats).
- **Retrieval hit:** el `document_font` esperat apareix entre les `fonts`
  recuperades.

Imprimeix un informe per pregunta + un resum agregat, i opcionalment l'exporta a
JSON amb `--out`.

### Mode mock (offline, per a CI sense GPU)

Usa els **mateixos dobles** que els tests (`app/testing/fakes.py`: LLM,
embeddings i reranker deterministes) i una BD SQLite en memòria. No descarrega
models ni fa cap crida de xarxa, així que corre a qualsevol CI:

```bash
cd backend
python -m eval.run_eval --mock
# amb llindar de routing que trenca el build si baixa (exit code != 0):
python -m eval.run_eval --mock --min-routing 0.8 --out informe.json
```

> En mode mock el **routing** es valida de debò (és determinista), però el
> retrieval i el `contains` són parcials: el reranker fals ordena per solapament
> de paraules i l'embedder fals no fa cerca semàntica, de manera que el document
> esperat no sempre queda entre el top-N. És esperat — el mode mock serveix per
> validar que l'arnès corre, no per mesurar la qualitat semàntica.

### Mode real (pilot GCP / vLLM)

Contra els components reals (embeddings bge-m3, reranker bge i el LLM via
`OPENAI_BASE_URL`). Requereix una `DATABASE_URL` viva (Postgres+pgvector) i un
`OPENAI_BASE_URL` actiu (Ollama en dev, vLLM en GPU):

```bash
cd backend
python -m eval.run_eval                       # mode real
python -m eval.run_eval --min-routing 0.9 --out informe_real.json
```

### Opcions

| Opció | Per defecte | Descripció |
| --- | --- | --- |
| `--eval-file` | `docs/eval/eval_set_ca.jsonl` | Ruta a l'eval set JSONL. |
| `--mock` | (desactivat) | Mode offline amb els dobles de test. |
| `--min-routing` | `0.0` | Llindar mínim de routing accuracy; per sota → exit code 1. |
| `--contains-llindar` | `1.0` | Fracció dels strings esperats que cal trobar per comptar com a "contains OK". |
| `--out` | (cap) | Exporta l'informe complet a un fitxer JSON. |

## Decisions tècniques rellevants

- **Abstracció de model (portabilitat):** un únic `OpenAICompatibleClient`
  (`app/rag/llm.py`) per a tota inferència. Canviar de dev (Ollama) a GPU (vLLM)
  o de cloud a on-prem = canviar `OPENAI_BASE_URL`/`LLM_MODEL`, sense tocar codi.
  El client **rebutja** qualsevol `OPENAI_BASE_URL` que apunti a un proveïdor
  comercial (OpenAI/Anthropic/Gemini…) i ho registra a la telemetria de privadesa.
- **Embeddings i reranker mandrosos i injectables:** `bge-m3` i
  `bge-reranker-v2-m3` es carreguen via FlagEmbedding **només** al primer ús, i
  s'embeliquen amb dobles en test (cap descàrrega de HuggingFace a la CI).
- **Vector store portable:** columna `Embedding` (`TypeDecorator`) que usa
  `vector(1024)` real a Postgres (operadors de distància nadius) i es degrada a
  JSON a SQLite per als tests. El retriever fa top-k per `cosine_distance` quan
  pgvector hi és, i rerank top-n sempre.
- **Orquestrador LangGraph amb degradació:** graf
  `classifica → RBAC → recupera → genera`. Si LangGraph no està instal·lat, hi
  ha una execució seqüencial equivalent (mateixos nodes) perquè res es trenqui.
  El routing per paraules clau és **determinista** (testejable) i pot reencaminar
  l'agent suggerit pel frontend.
- **Streaming SSE:** `POST /api/chat` amb `stream=true` emet `sources` (fonts),
  `token` (deltes), `done` (Message final) i `error`, via `sse-starlette`.
- **Auditoria append-only:** cada `/api/chat` es registra a la taula `audit_log`
  (BD) i a un fitxer JSON-lines (`AUDIT_LOG_PATH`). Els privilegis UPDATE/DELETE
  sobre `audit_log` es revoquen al schema.
- **RBAC:** el rol viatja dins el JWT; `/api/agents` i el routing filtren agents
  per rol. Cada usuari només veu les seves converses.

## Com afegir un agent o una tool MCP

- **Agent nou:** afegeix una `AgentDef` a `app/agents/registry.py` (id, persona,
  `rols_permesos`, `tools`, `paraules_clau`). L'API i l'orquestrador el
  descobreixen automàticament.
- **Tool MCP nova:** defineix l'executor i el seu `input_schema` a
  `app/mcp/tools.py`, afegeix-lo a `construeix_tools`, i declara'n el nom al
  camp `tools` de l'agent. Cap altre canvi.

## Notes per a frontend / infra

- **Base URL:** `/api`. Auth: `Authorization: Bearer <token>` (token de
  `POST /api/auth/login`).
- **Reencaminament:** `agent_utilitzat` de la resposta pot diferir de l'`agent_id`
  enviat (l'orquestrador pot reencaminar). El frontend ha de mostrar
  `agent_utilitzat`.
- **SSE:** consumir `text/event-stream`; el `done` porta el `Message` complet
  amb `fonts[]` i `confianca` (no cal recompondre'l a partir dels `token`).
- **Models en runtime:** el contenidor del backend necessita `FlagEmbedding` i
  `torch` (ja a `requirements.txt`); la primera petició descarregarà bge-m3 i el
  reranker (uns ~2,5 GB combinats). Considerar precarregar-los a la imatge o
  muntar una cache de HuggingFace en producció.
- **Postgres:** imatge `pgvector/pgvector:pg16`; el schema l'aplica
  `db/init/01_schema.sql`. `main.py` també fa `create_all` best-effort a
  l'arrencada.
```
