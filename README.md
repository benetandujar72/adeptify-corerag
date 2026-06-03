# adeptify-corerag

> **«IA que protegeix».** A sovereign Retrieval-Augmented / Cache-Augmented Generation (RAG/CAG) engine for schools and education centres — where the AI runs **inside** the institution and **no student data ever leaves it**.

`adeptify-corerag` is the **open core** of the Adeptify platform. It is fully self-hostable, runs **100% local models** (Ollama / vLLM) and is built for **GDPR** and the **EU AI Act** by design. The commercial school-management modules live in a separate private repository (`adeptify-suiterag`) that talks to this core over a local API.

**License:** GNU AGPL-3.0-or-later (see `LICENSE`). The core is also available under a separate **commercial license** (dual licensing) — contact bandujar@xtec.cat.

---

## Why

| The typical EdTech SaaS | adeptify-corerag |
|---|---|
| Minors' data lives in the vendor's cloud | **Data stays in the centre** (self-hosted) |
| Depends on third-party APIs (OpenAI…) | **Self-hosted models, zero egress** |
| Black box | **Forensic audit** + transparency (AI Act Art. 50) |
| Opaque automated decisions | **Human validation always** (AI Act Art. 14) |

## Core principles (non-negotiable)

- **Zero egress** — inference and data are 100% local; no third-party commercial API on the critical path.
- **Human oversight (Art. 14)** — the AI proposes drafts; a person validates and executes.
- **Data sovereignty (GDPR)** — no real minors' PII in this repository or its history; validation uses **synthetic data** only.
- **Traceability** — every answer cites its sources; every interaction is audited.
- **No lock-in** — everything runs in containers; switching the LLM is one environment variable.

## What's in the core

RAG/CAG pipeline (ingestion, semantic chunking, embeddings, hybrid retrieval + reranking), an OpenAI-compatible serving layer, base agents, an MCP server, the chat dashboard, base RBAC and audit, and a privacy gateway. School-management features (enrolment, attendance, assessment, payments, records, integrations) are **not** here — they are commercial modules in `adeptify-suiterag`.

## Quick start

```bash
git clone <this-repo> adeptify-corerag && cd adeptify-corerag
cp .env.example .env          # core-only keys; fill in locally, never commit
# make sure Ollama is running and a local model is pulled (e.g. qwen2.5:7b)
docker compose up -d          # db (pgvector) + backend + frontend
```

Then open the dashboard, upload a few documents and ask a question — the answer cites its sources, and `crides_externes` (external LLM calls) stays at **0**.

> Requirements and on-prem/cloud notes: see `docs/`. Hardening before production: change `JWT_SECRET` and seed passwords, enable MFA, restrict remote access, serve over HTTPS, run the production check.

## Architecture (open-core boundary)

```
Frontend ─▶ adeptify-corerag  (PUBLIC · AGPL)  ◀──API──▶  adeptify-suiterag (PRIVATE · commercial)
            RAG/CAG · retrieval · chat · API · RBAC base       school management · integrations
```

The two engines are **separate processes/containers** that communicate over a **local, authenticated API**. This process boundary is also the licence boundary: the commercial modules are independent programs that consume the core, not derivative works of it.

## Contributing

Contributions are welcome — see `CONTRIBUTING.md`. By contributing you agree your work is licensed under **AGPL-3.0-or-later**. A formal contribution agreement for the dual-licensing model is being finalised with legal counsel and will be published before external contributions are accepted.

## Security

Please report vulnerabilities privately — see `SECURITY.md` (do not open public issues for security problems).

## Compliance

Designed for the EU AI Act (human oversight, transparency, auditability) and GDPR (data sovereignty, no real minors' data in the open repo). A model card, record of processing activities and DPIA accompany production deployments.

---

### Català (resum)

`adeptify-corerag` és el **nucli obert** d'Adeptify: un motor RAG/CAG **sobirà** per a centres educatius que s'executa **dins** del centre, amb **models 100% locals** i **zero egress**, sota **AGPL-3.0** (amb llicència comercial disponible per a dual licensing). Els mòduls de gestió escolar són privats (`adeptify-suiterag`) i parlen amb el nucli per una **API local**. Per contribuir, vegeu `CONTRIBUTING.md`.

### Castellano (resumen)

`adeptify-corerag` es el **núcleo abierto** de Adeptify: un motor RAG/CAG **soberano** para centros educativos que se ejecuta **dentro** del centro, con **modelos 100% locales** y **zero egress**, bajo **AGPL-3.0** (con licencia comercial disponible para dual licensing). Los módulos de gestión escolar son privados (`adeptify-suiterag`) y hablan con el núcleo por una **API local**. Para contribuir, véase `CONTRIBUTING.md`.

---

*Adeptify · Benet Andújar · bandujar@xtec.cat — «IA que protegeix» · AGPL-3.0-or-later*
