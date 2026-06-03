# Contributing to adeptify-corerag

Thank you for your interest in contributing to **Adeptify** — «IA que protegeix». This guide explains how to contribute and the rules that keep the project sovereign, compliant and safe.

## 1. Contribution terms (interim)

By submitting a contribution you agree it is licensed under **AGPL-3.0-or-later**.

A formal **contribution agreement** (to support the dual-licensing model, under which the core stays open under AGPL-3.0-or-later while Adeptify can also offer a commercial licence) is being finalised with legal counsel. Until it is published, external contributions are accepted on a case-by-case basis — please open an issue first (see §3) and email bandujar@xtec.cat to coordinate. This section will be updated when the agreement is in place.

## 2. Ground rules (non-negotiable)

These protect minors' data and keep us within the EU AI Act and GDPR. PRs that break them will not be merged:

- **No real PII.** Never commit real personal data, least of all about minors. Use **synthetic data** for tests and examples.
- **No secrets.** Never commit `.env`, keys, tokens, credentials or service-account files. A secret scanner and a pre-commit hook are expected; if you leak a secret, tell us so we can rotate it.
- **Zero egress.** Do not add calls to third-party commercial APIs on the critical path. Inference must remain local (Ollama / vLLM).
- **Human oversight (Art. 14).** The AI proposes; a person validates. Do not add features that take automated decisions about people.
- **Keep the boundary clean.** Commercial / school-management features belong in `adeptify-suiterag`, not here. The core exposes a stable API; it must run on its own.

## 3. How to contribute

1. **Open an issue first** for non-trivial changes, so we can agree on the approach.
2. **Fork** and create a branch: `feature/<short-name>` or `fix/<short-name>`.
3. Make focused commits. We use **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`…).
4. Add or update **tests**, and keep documentation in sync.
5. Open a **pull request** describing the motivation, the change, and how you tested it.

## 4. Development setup

```bash
cp .env.example .env            # core-only keys; never commit real values
docker compose up -d            # db (pgvector) + backend + frontend
# run the quality gate before pushing (tests + type-check + lint + build):
make verifica                   # or pwsh scripts/verifica.ps1 / bash scripts/verifica.sh
```

A PR is ready when the full gate is green: backend `pytest`, frontend type-check, lint and build.

## 5. Review & quality

We look for: correctness and tests; respect for RBAC, multi-tenant isolation and audit; no new egress; no secrets or real data; clear, normative-Catalan or English user-facing strings; and changes scoped to the core. Be kind and assume good faith — code review is a conversation.

## 6. Security

**Do not open public issues for security problems.** Follow `SECURITY.md` (GitHub Security Advisories or email). Coordinated disclosure, please.

## 7. Language

Code, comments and docs may be in **English or Catalan**. User-facing strings follow the project's i18n; keep Catalan normative (IEC) and avoid castellanisms.

---

By submitting a contribution you agree it is licensed under **AGPL-3.0-or-later** (see §1 on the forthcoming contribution agreement). Gràcies! · ¡Gracias! · Thank you!
