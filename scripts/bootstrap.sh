#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Adeptify · Bootstrap d'un servidor nou
# ─────────────────────────────────────────────────────────────────────────────
# Aquest script porta un servidor des de zero fins a tenir l'aplicatiu
# funcionant. Idempotent: pots tornar-lo a executar amb seguretat.
#
# Què fa:
#   1. Verifica que docker + docker compose estan instal·lats.
#   2. Detecta si hi ha GPU NVIDIA disponible (per al reranker).
#   3. Crea un `.env` segur si no existeix (secrets aleatoris).
#   4. Aixeca el stack (db + ollama + backend + frontend).
#   5. Baixa els models LLM necessaris a Ollama.
#   6. Sembra la BD amb usuaris i dades demo.
#   7. Imprimeix les credencials per a la primera entrada.
#
# Ús:
#   bash scripts/bootstrap.sh                 # arrencada completa
#   bash scripts/bootstrap.sh --skip-models   # sense baixar models (els ja tens)
#   bash scripts/bootstrap.sh --skip-seed     # sense sembrar BD (ja la tens)
#   bash scripts/bootstrap.sh --reset         # PURGA pgdata + volums (DESTRUCTIU)
#
# Funciona a Linux i a WSL (Windows). Per a Windows pur, executa'l des de Git Bash.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# Colors per a la sortida ──────────────────────────────────────────────────
if [[ -t 1 ]]; then
    C_RED=$'\033[0;31m'; C_GREEN=$'\033[0;32m'; C_YELLOW=$'\033[0;33m'
    C_BLUE=$'\033[0;34m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""
fi

info()  { echo "${C_BLUE}ℹ${C_RESET} $*"; }
ok()    { echo "${C_GREEN}✓${C_RESET} $*"; }
warn()  { echo "${C_YELLOW}⚠${C_RESET} $*"; }
err()   { echo "${C_RED}✗${C_RESET} $*" >&2; }
title() { echo; echo "${C_BOLD}$*${C_RESET}"; echo "$(printf '%.0s─' {1..60})"; }

# ─── Arguments ────────────────────────────────────────────────────────────
SKIP_MODELS=false
SKIP_SEED=false
RESET=false
for arg in "$@"; do
    case "$arg" in
        --skip-models) SKIP_MODELS=true ;;
        --skip-seed)   SKIP_SEED=true ;;
        --reset)       RESET=true ;;
        --help|-h)     sed -n '4,30p' "$0"; exit 0 ;;
        *)             warn "Argument desconegut: $arg" ;;
    esac
done

# ─── 1. Prerequisits ──────────────────────────────────────────────────────
title "1. Verificació de prerequisits"
if ! command -v docker >/dev/null 2>&1; then
    err "Docker no està instal·lat. Vegeu https://docs.docker.com/engine/install/"
    exit 1
fi
ok "docker · $(docker --version | head -1)"

if ! docker compose version >/dev/null 2>&1; then
    err "docker compose v2 no disponible. Cal Docker ≥ 20.10 amb el plugin Compose."
    exit 1
fi
ok "docker compose · $(docker compose version --short)"

# ─── 2. Detecció de GPU NVIDIA ────────────────────────────────────────────
title "2. Detecció de maquinari"
HAS_GPU=false
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
    ok "GPU NVIDIA detectada: $GPU_NAME"
    # Comprova si el runtime de docker té accés a la GPU.
    if docker info 2>/dev/null | grep -qi "nvidia"; then
        ok "Runtime NVIDIA per a Docker configurat."
        HAS_GPU=true
    else
        warn "GPU detectada però el runtime de Docker no la veu."
        warn "  Instal·la nvidia-container-toolkit: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
        warn "  L'aplicatiu funcionarà amb CPU; el reranker serà més lent."
    fi
else
    info "Sense GPU NVIDIA detectada → es farà servir CPU (el reranker serà més lent)."
fi

# ─── 3. Generació de `.env` segur ─────────────────────────────────────────
title "3. Configuració d'entorn (.env)"
if [[ "$RESET" == true && -f .env ]]; then
    warn "RESET demanat: backup de l'.env actual a .env.bak.$(date +%s)"
    mv .env ".env.bak.$(date +%s)"
fi

if [[ -f .env ]]; then
    ok ".env ja existeix; no el sobreescric. Esborra'l si vols regenerar-lo."
else
    info "Creant nou .env amb secrets aleatoris…"
    # Genera secrets amb /dev/urandom (compatible Linux/Mac/WSL/Git Bash).
    rand_token() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-48}"; }
    JWT_SECRET="$(rand_token 48)"
    PG_PASS="$(rand_token 24)"
    PUBLIC_TOKEN="$(rand_token 40)"

    # Device per a embeddings i reranker segons GPU.
    if [[ "$HAS_GPU" == true ]]; then
        DEV="cuda"
    else
        DEV="cpu"
    fi

    cat > .env <<EOF
# ──────────────────────────────────────────────────────────────────────────
# Adeptify · .env generat per scripts/bootstrap.sh ($(date -u +%FT%TZ))
# Mantén-lo PRIVAT: conté secrets. No el commitis (.gitignore ja l'exclou).
# ──────────────────────────────────────────────────────────────────────────

# Postgres + pgvector
POSTGRES_USER=patufet
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=patufet
DATABASE_URL=postgresql+psycopg://patufet:${PG_PASS}@db:5432/patufet

# Inferència LLM (Ollama dins docker, perfil dev)
OPENAI_BASE_URL=http://ollama:11434/v1
OPENAI_API_KEY=sk-no-cal-pero-el-client-ho-demana
LLM_MODEL=qwen2.5:7b
LLM_MODEL_CATALA=qwen2.5:7b
LLM_MODEL_BATCH=qwen2.5:7b
LLM_MODEL_SKILLS=qwen2.5:7b

# Embeddings i reranker
EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
EMBEDDER_DEVICE=${DEV}
RERANKER_DEVICE=${DEV}
RERANKER_ACTIU=true
HYBRID_ACTIU=true
RAG_TOP_K=8
RAG_TOP_N=5
CHUNK_SIZE=1200
CHUNK_OVERLAP=200

# Frontend
VITE_API_BASE_URL=http://localhost:8000/api

# Seguretat
JWT_SECRET=${JWT_SECRET}
AUDIT_LOG_PATH=/app/data/audit.log
ENTORN=prod-local
SERVER_HOST=localhost (configura'l a la IP del servidor)

# Accés remot i xarxa
ACCES_REMOT_ADMIN_ONLY=false
XARXA_LOCAL_CIDRS=127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7
PROXY_DE_CONFIANCA=false

# Rate-limit del login
LOGIN_MAX_INTENTS=5
LOGIN_BLOQUEIG_MINUTS=15

# Canal públic (Mòdul 1)
PUBLIC_CHAT_TOKEN=${PUBLIC_TOKEN}
PUBLIC_CHAT_MAX_PER_MINUTE=5
PUBLIC_CHAT_INSTITUCIO=nou_patufet

# Capa vectorial
VECTOR_STORE=pgvector
QDRANT_URL=http://qdrant:6333

# Bot Telegram (Mòdul 2) — deixa buit per desactivar
TELEGRAM_BOT_TOKEN=
TELEGRAM_MAGIC_LINK_MINUTS=5
TELEGRAM_APP_URL=http://localhost:5173

# Auditoria diària (Mòdul 4)
AUDIT_DIARIA_WEBHOOK=
AUDIT_DIARIA_EMAIL=
EOF
    chmod 600 .env
    ok ".env creat amb secrets aleatoris (chmod 600)."
    ok "  JWT_SECRET     · 48 caràcters aleatoris"
    ok "  Postgres pass  · 24 caràcters aleatoris"
    ok "  PUBLIC_TOKEN   · 40 caràcters aleatoris"
fi

# ─── 4. Reset de volums si s'ha demanat ──────────────────────────────────
if [[ "$RESET" == true ]]; then
    title "4. RESET DESTRUCTIU"
    warn "S'esborraran TOTS els volums (pgdata, ollama, hf_cache, backend_data)."
    read -p "Estàs segur? Escriu 'RESET' per confirmar: " conf
    if [[ "$conf" == "RESET" ]]; then
        docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile dev down -v
        ok "Volums esborrats."
    else
        info "Reset cancel·lat."
    fi
fi

# ─── 5. Aixeca el stack ────────────────────────────────────────────────────
title "5. Aixecant el stack docker"
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile dev up -d --build
ok "Stack aixecat. Esperant que els serveis estiguin healthy…"

# Espera explícita a la BD.
for i in {1..30}; do
    if docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db pg_isready -U patufet >/dev/null 2>&1; then
        ok "Postgres healthy."
        break
    fi
    sleep 2
done

# Espera al backend.
for i in {1..60}; do
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        ok "Backend healthy."
        break
    fi
    sleep 2
done

# ─── 6. Baixar models a Ollama ────────────────────────────────────────────
if [[ "$SKIP_MODELS" == true ]]; then
    info "Salt de baixada de models (--skip-models)."
else
    title "6. Baixant model LLM a Ollama (qwen2.5:7b · ~4.4 GB)"
    info "Això pot trigar uns minuts segons l'amplada de banda…"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T ollama \
        ollama pull qwen2.5:7b
    ok "Model qwen2.5:7b disponible."
fi

# ─── 7. Sembrar BD amb dades demo ─────────────────────────────────────────
if [[ "$SKIP_SEED" == true ]]; then
    info "Salt de sembra de BD (--skip-seed)."
else
    title "7. Sembra de la BD (usuaris demo + LOMLOE)"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend \
        python -m scripts.seed || warn "seed.py: revisa si calia (potser ja sembrat)."
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend \
        python -m scripts.seed_domini || warn "seed_domini.py: revisa."
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend \
        python -m scripts.seed_avaluacio_lomloe || warn "seed_avaluacio_lomloe.py: revisa."
    ok "BD sembrada."
fi

# ─── 8. Resum final ───────────────────────────────────────────────────────
title "8. Estat final"
PUBLIC_TOKEN_SHOW="$(grep '^PUBLIC_CHAT_TOKEN=' .env | cut -d'=' -f2 | head -c 8)…"
echo
echo "${C_GREEN}${C_BOLD}Adeptify funcionant!${C_RESET}"
echo
echo "  Frontend  → http://localhost:5173"
echo "  Backend   → http://localhost:8000  (docs: /docs)"
echo "  Postgres  → localhost:5432 (usuari: patufet)"
echo
echo "  Credencials demo:"
echo "    admin            / admin-patufet-2026   (superadmin)"
echo "    direccio         / patufet2026          (direcció)"
echo "    marta            / patufet2026          (docent)"
echo "    pas_admin        / patufet2026          (PAS)"
echo "    familia_garcia   / patufet2026          (família)"
echo
echo "  ${C_YELLOW}Recomanacions abans d'usar amb usuaris reals:${C_RESET}"
echo "  · Canvia les contrasenyes demo (Administració → Usuaris)"
echo "  · Configura SERVER_HOST i VITE_API_BASE_URL a la IP real del servidor"
echo "  · Activa HTTPS amb un reverse proxy (Caddy/Traefik/Tailscale Funnel)"
echo "  · Comprova l'estat: docker compose ... exec backend python -m scripts.produccio_check"
echo
echo "  PUBLIC_CHAT_TOKEN (per al plugin WordPress): comença per ${PUBLIC_TOKEN_SHOW}"
echo "    (mira'l sencer amb: grep PUBLIC_CHAT_TOKEN .env)"
echo
