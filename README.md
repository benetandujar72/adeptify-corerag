# Adeptify Core RAG

![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Local-first](https://img.shields.io/badge/local--first-zero%20egress-0f766e)
![Status](https://img.shields.io/badge/status-active%20MVP-f59e0b)

**Sovereign RAG and AI governance layer for regulated organizations.**

Adeptify Core is the public, auditable engine of the Adeptify platform. It is built for institutions that cannot treat AI as "just another connector": schools, public bodies, foundations, healthcare-adjacent teams and companies working with sensitive knowledge.

The core idea: **make private AI provable**. Every answer should be traceable to sources, every access should be permissioned, every sensitive boundary should be explicit, and the deployment should be able to run locally or in a private cloud.

## Why This Exists

Generic AI assistants and connector ecosystems will keep improving. That makes basic RAG a commodity.

Adeptify Core focuses on the part large AI vendors do not solve for each institution by default:

| Commodity RAG | Adeptify Core |
| --- | --- |
| Chat over documents | Governed AI access over institutional knowledge |
| Cloud-first connectors | Local-first or private-cloud deployment |
| Trust by vendor promise | Trust by audit logs, policy, RBAC and source citations |
| One user, one assistant | Multi-institution, role-scoped access |
| Hard to inspect | Open repository, open API contracts and reproducible stack |

## Core vs Suite

```text
adeptify-corerag  (PUBLIC · GNU AGPL-3.0)
RAG/CAG · ingestion · retrieval · chat API · RBAC base · audit · MCP layer · privacy gateway

        authenticated local/service API boundary

adeptify-suiterag (PRIVATE · proprietary)
Institutional workflows · real PII · school/company modules · integrations · SLAs · compliance packs
```

The boundary is intentional:

- **Core** contains the reusable trust engine and must be inspectable.
- **Suite** contains client-specific workflows, sensitive operational data and commercial modules.
- The Suite talks to the Core through an authenticated API. PII must be minimized or pseudonymized before crossing that boundary.

## Available Today

- Self-hosted RAG/CAG stack with document ingestion, semantic chunking, embeddings, hybrid retrieval and reranking.
- OpenAI-compatible local inference path for Ollama/vLLM. Production deployments should keep commercial LLM calls off the critical path unless explicitly approved.
- pgvector-backed retrieval and source-grounded answers.
- Multi-institution access model with baseline RBAC.
- Append-only audit log for chats, ingestion and administrative actions.
- MCP-style internal tool layer and privacy gateway for controlled connector execution.
- Privacy telemetry, DLP checks and production hardening checks.
- Synthetic/sample data for demos without real minors' or client data.
- Evaluation scripts for retrieval/routing quality.

## What Makes It Defensible

The moat is not "we have a chatbot." The moat is **operational trust**:

- **Policy-as-code:** institutional rules should be versioned, reviewed and tested.
- **Privacy firewall:** PII detection, pseudonymization and fail-closed boundaries before model or connector calls.
- **Forensic audit:** who asked, with which role, over which sources, and what was returned.
- **Local sovereignty:** local models first, private cloud when needed, no silent egress.
- **Domain packs:** education, GDPR/EU, public administration and other regulated playbooks.
- **Open-core credibility:** public engine for trust, private Suite for customer-specific workflows.

## Roadmap For Contributors

These are the highest-leverage areas if the goal is to make Adeptify Core a reference open-source project:

1. `adeptify.policy.yml`: policy-as-code for allowed models, connectors, roles, retention, PII rules and audit requirements.
2. `adeptify firewall`: CLI/API that scans prompts, retrieved chunks and connector payloads before anything leaves the trust boundary.
3. `adeptify eval`: reproducible RAG evaluation with hallucination, citation, privacy and permission tests.
4. Compliance packs: `education-es`, `gdpr-eu`, `ai-act-basic`, `public-admin`.
5. Air-gapped profile: documented deployment with no external network dependency.
6. Public synthetic demo: realistic enough to understand the product, clean enough to publish safely.
7. Connector sandbox: allow-list, per-tool permissions, audit, rate limits and redaction.

## Quick Start

```bash
git clone https://github.com/benetandujar72/adeptify-corerag.git
cd adeptify-corerag
cp .env.example .env

# Make sure Ollama is running and a local model is available, for example:
# ollama pull qwen2.5:7b

docker compose up -d
```

Then open the frontend, ingest sample documents and ask a question. The answer should cite sources and the privacy telemetry should show no unauthorized external LLM calls.

Before any production use:

- Change all default secrets.
- Enable HTTPS and network restrictions.
- Review RBAC and institution isolation.
- Run the production/security checks.
- Use only synthetic or approved data in demos.

## Repository Map

```text
backend/       FastAPI backend, RAG, RBAC, audit, MCP layer and security controls
frontend/      Core dashboard and chat UI
kernel/        Public/core-safe kernel pieces
sample_data/   Synthetic demo data
scripts/       Operational and evaluation scripts
```

## Contributing

Contributions are welcome, especially around privacy engineering, policy-as-code, local model deployment, RAG evaluation, documentation and synthetic demos.

By contributing, you agree that your contribution is licensed under the same license as the project. See `CONTRIBUTING.md` and `SECURITY.md` before opening large PRs or reporting vulnerabilities.

## License

`adeptify-corerag` is licensed under **GNU AGPL-3.0**. See `LICENSE`.

Commercial licensing for organizations that need different terms can be discussed with Adeptify.

## Short Version

Adeptify Core wants to be the **Keycloak-style trust layer for institutional AI**: open, inspectable, self-hostable and strict about privacy before any agent, RAG pipeline or connector touches sensitive knowledge.

