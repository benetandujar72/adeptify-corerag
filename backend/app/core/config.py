"""Configuració de l'aplicació, carregada des de variables d'entorn (.env).

Usa exactament les variables descrites a `.env.example`. La configuració és un
singleton mandrós (`get_settings`) memoïtzat amb `lru_cache` perquè els tests la
puguin sobreescriure mitjançant variables d'entorn abans del primer accés.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables d'entorn de l'aplicació.

    Els valors per defecte coincideixen amb `.env.example` per facilitar el
    desenvolupament local i els tests sense `.env`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Base de dades (Postgres + pgvector) ──
    database_url: str = (
        "postgresql+psycopg://patufet:patufet@db:5432/patufet"
    )

    # ── Abstracció de model: client OpenAI-compatible ──
    # En dev apunta a Ollama; en GPU apunta a vLLM. MAI a OpenAI/Anthropic/Gemini.
    openai_base_url: str = "http://ollama:11434/v1"
    openai_api_key: str = "sk-no-cal-pero-el-client-ho-demana"
    llm_model: str = "qwen2.5:7b"
    llm_model_catala: str = "BSC-LT/salamandra-7b-instruct"
    # Model per a tasques BATCH / no interactives (generació de documents, anàlisi).
    # Pot ser un model gran (p. ex. qwen3-coder-rag, 30B MoE) on la latència no importa.
    # L'usen els fluxos que ho demanin explícitament (LLMClient.complete(..., usa_batch=True)).
    llm_model_batch: str = "qwen2.5:7b"
    # Model per als SKILLS (agents personalitzats) i la generació/prova de prompts:
    # prioritza la QUALITAT del català institucional (sense castellanismes) per damunt de
    # la latència. Els agents integrats segueixen amb `llm_model` (ràpid). Vegeu docs/19.
    llm_model_skills: str = "gemma3:12b"

    # ── Embeddings i reranker (auto-allotjats dins el backend) ──
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_dim: int = 1024  # dimensió de bge-m3
    rag_top_k: int = 20
    rag_top_n: int = 5
    # Reranker actiu: millora la qualitat i dona una confiança real i alta.
    # En GPU és ràpid (~1s); en CPU és car (~1,6s/parell).
    reranker_actiu: bool = True
    # Device dels models bge. El reranker a GPU (confiança alta i ràpida);
    # l'embedder a CPU per estalviar VRAM (la GPU de 8 GB la comparteix amb el LLM).
    # Si no hi ha CUDA disponible, es fa fallback automàtic a CPU.
    embedder_device: str = "cpu"   # cpu | cuda | cuda:0
    reranker_device: str = "cuda"  # cpu | cuda | cuda:0
    # Cerca híbrida: fusiona la cerca vectorial (semàntica) amb una cerca lèxica
    # (full-text de Postgres, estil BM25) via Reciprocal Rank Fusion. Millora el
    # recall en noms, dates i termes exactes (calendari, preus...). Només a Postgres.
    hybrid_actiu: bool = True

    # ── Veu (Whisper STT local via faster-whisper) ──
    # En CPU (int8) per no competir per la VRAM amb el LLM/reranker/embedder.
    whisper_model: str = "base"   # tiny | base | small | medium
    whisper_device: str = "cpu"   # cpu | cuda
    whisper_compute: str = "int8"  # int8 (CPU) | float16 (GPU)

    # Mida de chunk (caràcters) i solapament per al chunking semàntic.
    chunk_size: int = 1200
    chunk_overlap: int = 200

    # ── Seguretat ──
    jwt_secret: str = "canvia-aquest-secret"
    jwt_algorithm: str = "HS256"
    jwt_expira_hores: int = 8   # finestra de sessió més curta (revocació + caducitat)
    audit_log_path: str = "/app/data/audit.log"

    # ── Accés remot (Fase 1) ──
    # Quan és cert, les peticions que NO provenen de la xarxa local només
    # s'autoritzen per als rols d'administració (direcció/superadmin). Des de la
    # xarxa local (rang configurable) no s'aplica cap restricció per aquest motiu.
    acces_remot_admin_only: bool = True
    # Rangs CIDR considerats "xarxa local" (separats per comes). Per defecte:
    # loopback + rangs privats (RFC1918 + ULA IPv6). Restringeix-ho a la subxarxa
    # del centre (p. ex. "192.168.1.0/24") amb la variable XARXA_LOCAL_CIDRS.
    xarxa_local_cidrs: str = (
        "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
    )
    # Confiar en X-Forwarded-For per determinar la IP del client. Només actiu
    # darrere un reverse proxy/túnel DE CONFIANÇA (altrament es podria falsejar la
    # IP i saltar-se l'allow-list). Per defecte, IP directa del socket.
    proxy_de_confianca: bool = False

    # ── CORS i capçaleres de seguretat ──
    # Orígens permesos per CORS (separats per comes). "*" (per defecte) és còmode
    # en dev, però NO es pot combinar amb credencials i és insegur exposat a
    # Internet. En producció, posa-hi el/els domini(s) reals del frontend
    # (p. ex. "https://patufet.exemple.cat,https://www.patufet.exemple.cat").
    cors_origins: str = "*"
    # Exposar la documentació interactiva (/docs, /redoc, /openapi.json). Es
    # desactiva SEMPRE en entorns de producció (vegeu main.py), independentment
    # d'aquest valor; en dev/pilot es pot apagar posant-ho a false.
    exposa_docs: bool = True

    # ── Rate-limit del login (anti força bruta / credential stuffing) ──
    # Després de `login_max_intents` fallits consecutius per compte (usuari+centre),
    # es bloqueja el login d'aquell compte durant `login_bloqueig_minuts`. Un login
    # correcte reseteja el comptador. Mitiga atacs sobre la pantalla de login.
    login_max_intents: int = 5
    login_bloqueig_minuts: int = 15

    # ── Canal públic (/api/public/*) ──
    # Bearer públic que el front (WordPress, web pública) ha d'enviar a la
    # capçalera X-Public-Token. NO és un token d'usuari; només acredita l'origen.
    # Si està buit, l'endpoint públic queda DESACTIVAT (defensa en profunditat).
    public_chat_token: str = ""
    public_chat_max_per_minute: int = 5  # rate-limit per IP (5 peticions/min)
    public_chat_institucio: str = "nou_patufet"  # tenant del canal públic

    # ── Servei intern (suite → core): generació de propostes pedagògiques ──
    # Secret compartit (Bearer / X-Service-Token) que el suite (adeptify-suiterag,
    # privat) ha d'enviar per consumir POST /api/servei/*. NO és un token d'usuari:
    # acredita que la crida prové del suite de confiança a la mateixa LAN. Si està
    # buit, el servei intern queda DESACTIVAT (defensa en profunditat): el nucli no
    # delega cap inferència fins que s'hi configura un secret fort. La frontera
    # open-core es manté: el core no coneix el domini escolar; només rep criteris i
    # evidència com a context i retorna una proposta (sense desar res ni PII).
    core_service_token: str = ""

    # ── Capa vectorial: pgvector | qdrant ──
    vector_store: str = "pgvector"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""

    # ── Telegram bot (mòdul 2) ──
    telegram_bot_token: str = ""  # buit = bot desactivat
    telegram_magic_link_minuts: int = 5
    telegram_app_url: str = "http://localhost:5180"  # frontend base per al magic link

    # ── Auditoria diària (mòdul 4) ──
    audit_diaria_webhook: str = ""  # POST a aquest endpoint si hi ha alertes
    audit_diaria_email: str = ""  # còpia opcional

    # ── Entorn i metadades reportades a /api/system/status ──
    # Per defecte `dev` (sense porta de seguretat). En desplegar de debò, posa
    # `pilot-gcp`/`prod-onprem` al `.env`: aleshores la porta fail-closed exigeix
    # secrets forts i inferència local abans d'arrencar.
    entorn: str = "dev"  # dev | pilot-gcp | prod-onprem
    versio: str = "v0.1.0-mvp"
    server_host: str = "192.168.1.10 (o IP VM GCP)"

    # Carpeta muntada read-only amb els documents d'exemple del centre.
    sample_data_path: str = "/app/sample_data"

    @property
    def es_entorn_gpu(self) -> bool:
        """Cert si l'entorn correspon a un desplegament amb GPU (vLLM)."""
        return self.entorn in {"pilot-gcp", "prod-onprem"}

    @property
    def es_prod(self) -> bool:
        """Cert si l'entorn és de producció real (no dev/pilot)."""
        return (self.entorn or "").lower() in {"prod", "prod-local", "prod-onprem"}

    @property
    def cors_origins_list(self) -> list[str]:
        """Orígens CORS com a llista. Buit o '*' → ['*'] (permissiu)."""
        vals = [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]
        return vals or ["*"]


@lru_cache
def get_settings() -> Settings:
    """Retorna la configuració memoïtzada (un sol objecte per procés)."""
    return Settings()
