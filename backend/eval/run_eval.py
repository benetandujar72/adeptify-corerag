"""Runner d'avaluació del backend IA Nou Patufet.

Executa l'eval set (`docs/eval/eval_set_ca.jsonl`) pel MATEIX camí intern que
`POST /api/chat` — sense aixecar cap servidor HTTP — i mesura tres dimensions:

1. **Routing accuracy**: l'agent triat per l'orquestrador == `agent_esperat`.
2. **Groundedness / contains**: la resposta conté els strings de
   `resposta_esperada_conté` (comparació normalitzada: minúscules, sense accents,
   espais col·lapsats).
3. **Retrieval hit**: el `document_font` esperat apareix entre les `fonts`
   recuperades.

Camí intern reproduït (idèntic a `app/api/routes_chat.py`):

    orq = get_orchestrator(db)
    prep = orq.prepara(pregunta, agent_suggerit, rol, historial=[])
    # prep.agent_id  → agent escollit (routing)
    # prep.fonts     → fonts recuperades (retrieval)
    text = orq.genera(prep)   # resposta del LLM

Dos modes:

- **Real** (per defecte): usa els components reals (embeddings bge-m3, reranker
  bge, LLM via `OPENAI_BASE_URL`). Útil al pilot GCP/vLLM.
- **Mock / offline** (`--mock`): injecta els mateixos dobles deterministes que
  els tests (`app.testing.fakes`), de manera que el runner corre a la CI sense
  GPU ni xarxa.

Ús:

    # arrel del repo o dins backend/ (la importació de `app` requereix backend/ al path)
    python -m eval.run_eval --mock
    python -m eval.run_eval --min-routing 0.8 --out informe.json
    python -m eval.run_eval                       # mode real (cal OPENAI_BASE_URL viu)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Permet `python eval/run_eval.py` (a part de `python -m eval.run_eval`) afegint
# l'arrel de `backend/` (carpeta pare d'aquesta) al sys.path.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ───────────────────────── Rutes robustes ───────────────────────────────────

# eval/run_eval.py → backend/ → <arrel del repo>
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_SET_PER_DEFECTE = _REPO_ROOT / "docs" / "eval" / "eval_set_ca.jsonl"
# sample_data viu a l'arrel del repo (es munta read-only al contenidor).
_SAMPLE_DATA = _REPO_ROOT / "sample_data"


# ───────────────────────── Normalització de text ────────────────────────────


def normalitza(text: str) -> str:
    """Minúscules, sense accents, espais col·lapsats (per a comparacions robustes)."""
    text = text.lower()
    # Elimina diacrítics (à→a, ç→c, ï→i…).
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(text.split())


# ───────────────────────── Estructures de resultat ──────────────────────────


@dataclass
class ResultatPregunta:
    """Resultat d'avaluar una entrada de l'eval set."""

    pregunta: str
    agent_esperat: str
    agent_obtingut: str
    routing_ok: bool
    document_font: str
    fonts_recuperades: list[str]
    retrieval_hit: bool
    esperats_conté: list[str]
    trobats_conté: list[str]
    contains_ratio: float
    contains_ok: bool
    resposta: str = ""
    error: str | None = None


@dataclass
class Resum:
    """Mètriques agregades de tota l'execució."""

    total: int = 0
    avaluades: int = 0
    errors: int = 0
    routing_correctes: int = 0
    routing_accuracy: float = 0.0
    contains_ratio_mitjà: float = 0.0
    contains_ok: int = 0
    contains_ok_pct: float = 0.0
    retrieval_hits: int = 0
    retrieval_hit_pct: float = 0.0


# ───────────────────────── Càrrega de l'eval set ────────────────────────────


def carrega_eval_set(cami: Path) -> list[dict[str, Any]]:
    """Llegeix un fitxer JSONL i en retorna les entrades (línies buides ignorades)."""
    if not cami.exists():
        raise FileNotFoundError(f"No s'ha trobat l'eval set: {cami}")
    entrades: list[dict[str, Any]] = []
    for n, linia in enumerate(cami.read_text(encoding="utf-8").splitlines(), start=1):
        linia = linia.strip()
        if not linia:
            continue
        try:
            entrades.append(json.loads(linia))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Línia {n} no és JSON vàlid: {exc}") from exc
    return entrades


# ───────────────────────── Configuració de l'entorn ─────────────────────────


def _prepara_entorn_mock() -> None:
    """Variables d'entorn segures per al mode offline (abans d'importar `app`)."""
    import os

    os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    os.environ.setdefault("JWT_SECRET", "secret-eval")
    os.environ.setdefault("ENTORN", "dev")
    os.environ.setdefault("OPENAI_BASE_URL", "http://ollama:11434/v1")
    os.environ.setdefault("AUDIT_LOG_PATH", "")


def _crea_sessio_en_memoria():
    """Crea una sessió SQLite en memòria amb les taules creades (mode mock)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.models import Base

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return SessionLocal()


def _injecta_dobles() -> None:
    """Injecta els mateixos dobles que els tests (sense GPU ni xarxa)."""
    from app.rag import embeddings, llm, rerank
    from app.testing.fakes import FakeEmbedder, FakeLLM, FakeReranker

    embeddings.set_embedder(FakeEmbedder())
    rerank.set_reranker(FakeReranker())
    # eco_context=True: la resposta reflecteix el context recuperat, de manera que
    # les comprovacions de `contains` són significatives també offline.
    llm.set_llm_client(FakeLLM(eco_context=True))


# ───────────────────────── Avaluació d'una entrada ──────────────────────────


def _rol_per_agent(agent_id: str):
    """Tria un rol amb accés a l'agent esperat (perquè el routing no el bloquegi).

    L'avaluació no mesura RBAC sinó routing/retrieval; per això s'usa un rol amb
    accés a l'agent que l'eval set espera. Si l'agent és desconegut, s'usa DOCENT.
    """
    from app.agents.registry import get_agent
    from app.core.roles import Rol

    agent = get_agent(agent_id)
    if agent is not None and agent.rols_permesos:
        # DOCENT té accés a la majoria d'agents; si no, el primer rol permès.
        if Rol.DOCENT in agent.rols_permesos:
            return Rol.DOCENT
        return agent.rols_permesos[0]
    return Rol.DOCENT


def avalua_entrada(db, entrada: dict[str, Any]) -> ResultatPregunta:
    """Executa una pregunta pel camí intern de l'orquestrador i la puntua."""
    from app.orchestrator.graph import get_orchestrator

    pregunta = entrada.get("pregunta", "")
    agent_esperat = entrada.get("agent_esperat", "")
    document_font = entrada.get("document_font", "")
    esperats = entrada.get("resposta_esperada_conté", []) or []

    rol = _rol_per_agent(agent_esperat)

    try:
        orq = get_orchestrator(db)
        # Mateix camí intern que /api/chat: el frontend suggereix un agent; aquí
        # suggerim l'esperat i deixem que l'orquestrador confirmi o reencamini.
        prep = orq.prepara(pregunta, agent_esperat, rol, historial=[])
        agent_obtingut = prep.agent_id
        fonts = [f.filename for f in prep.fonts]
        resposta = orq.genera(prep)
    except Exception as exc:  # noqa: BLE001
        return ResultatPregunta(
            pregunta=pregunta,
            agent_esperat=agent_esperat,
            agent_obtingut="",
            routing_ok=False,
            document_font=document_font,
            fonts_recuperades=[],
            retrieval_hit=False,
            esperats_conté=esperats,
            trobats_conté=[],
            contains_ratio=0.0,
            contains_ok=False,
            error=str(exc),
        )

    # Routing accuracy.
    routing_ok = agent_obtingut == agent_esperat

    # Retrieval hit: el document esperat apareix entre les fonts (comparació
    # normalitzada del nom de fitxer).
    font_norm = normalitza(document_font)
    retrieval_hit = any(normalitza(f) == font_norm for f in fonts) if document_font else False

    # Groundedness / contains.
    resposta_norm = normalitza(resposta)
    trobats = [s for s in esperats if normalitza(s) in resposta_norm]
    contains_ratio = (len(trobats) / len(esperats)) if esperats else 1.0

    return ResultatPregunta(
        pregunta=pregunta,
        agent_esperat=agent_esperat,
        agent_obtingut=agent_obtingut,
        routing_ok=routing_ok,
        document_font=document_font,
        fonts_recuperades=fonts,
        retrieval_hit=retrieval_hit,
        esperats_conté=esperats,
        trobats_conté=trobats,
        contains_ratio=round(contains_ratio, 4),
        contains_ok=False,  # s'emplena segons el llindar global a `executa`
        resposta=resposta,
    )


# ───────────────────────── Orquestració de l'execució ───────────────────────


def agrega(resultats: list[ResultatPregunta]) -> Resum:
    """Calcula les mètriques agregades."""
    resum = Resum(total=len(resultats))
    avaluats = [r for r in resultats if r.error is None]
    resum.avaluades = len(avaluats)
    resum.errors = len(resultats) - len(avaluats)
    if not avaluats:
        return resum

    resum.routing_correctes = sum(1 for r in avaluats if r.routing_ok)
    resum.routing_accuracy = round(resum.routing_correctes / len(avaluats), 4)
    resum.contains_ratio_mitjà = round(
        sum(r.contains_ratio for r in avaluats) / len(avaluats), 4
    )
    resum.contains_ok = sum(1 for r in avaluats if r.contains_ok)
    resum.contains_ok_pct = round(resum.contains_ok / len(avaluats), 4)
    resum.retrieval_hits = sum(1 for r in avaluats if r.retrieval_hit)
    resum.retrieval_hit_pct = round(resum.retrieval_hits / len(avaluats), 4)
    return resum


def executa(
    entrades: list[dict[str, Any]],
    *,
    mock: bool,
    contains_llindar: float,
) -> tuple[list[ResultatPregunta], Resum]:
    """Prepara components, ingesta sample_data i avalua totes les entrades."""
    from app.ingest import pipeline

    if mock:
        _injecta_dobles()
        db = _crea_sessio_en_memoria()
    else:
        from app.db.models import Base
        from app.db.session import get_engine, get_sessionmaker

        Base.metadata.create_all(bind=get_engine())
        db = get_sessionmaker()()

    try:
        # Ingesta sample_data al magatzem (idempotent: reindexar és segur).
        if _SAMPLE_DATA.exists():
            pipeline.ingesta_carpeta(db, _SAMPLE_DATA)
        else:
            print(f"AVÍS: no s'ha trobat sample_data a {_SAMPLE_DATA}; "
                  "el retrieval pot quedar buit.", file=sys.stderr)

        resultats: list[ResultatPregunta] = []
        for entrada in entrades:
            r = avalua_entrada(db, entrada)
            # `contains_ok`: assolit si supera el llindar (% de strings trobats).
            r.contains_ok = r.error is None and r.contains_ratio >= contains_llindar
            resultats.append(r)
    finally:
        db.close()

    return resultats, agrega(resultats)


# ───────────────────────── Informe ──────────────────────────────────────────


def _marca(ok: bool) -> str:
    return "OK " if ok else "FAIL"


def imprimeix_informe(resultats: list[ResultatPregunta], resum: Resum) -> None:
    """Informe per pregunta + resum agregat per stdout."""
    print("=" * 78)
    print("AVALUACIÓ IA NOU PATUFET — informe per pregunta")
    print("=" * 78)
    for i, r in enumerate(resultats, start=1):
        if r.error is not None:
            print(f"\n[{i:>2}] ERROR — {r.pregunta[:70]}")
            print(f"      {r.error}")
            continue
        print(f"\n[{i:>2}] {r.pregunta[:70]}")
        print(
            f"      routing : {_marca(r.routing_ok)} "
            f"esperat={r.agent_esperat} obtingut={r.agent_obtingut}"
        )
        print(
            f"      retrieval: {_marca(r.retrieval_hit)} "
            f"font={r.document_font} fonts={r.fonts_recuperades}"
        )
        falten = [s for s in r.esperats_conté if s not in r.trobats_conté]
        print(
            f"      contains : {_marca(r.contains_ok)} "
            f"{len(r.trobats_conté)}/{len(r.esperats_conté)} "
            f"({r.contains_ratio:.0%})"
            + (f" falten={falten}" if falten else "")
        )

    print("\n" + "=" * 78)
    print("RESUM AGREGAT")
    print("=" * 78)
    print(f"  Entrades totals     : {resum.total}")
    print(f"  Avaluades / errors  : {resum.avaluades} / {resum.errors}")
    print(
        f"  Routing accuracy    : {resum.routing_accuracy:.1%} "
        f"({resum.routing_correctes}/{resum.avaluades})"
    )
    print(
        f"  Contains (≥ llindar): {resum.contains_ok_pct:.1%} "
        f"({resum.contains_ok}/{resum.avaluades})  "
        f"ratio mitjà={resum.contains_ratio_mitjà:.1%}"
    )
    print(
        f"  Retrieval hit       : {resum.retrieval_hit_pct:.1%} "
        f"({resum.retrieval_hits}/{resum.avaluades})"
    )
    print("=" * 78)


def exporta_json(
    cami: Path,
    resultats: list[ResultatPregunta],
    resum: Resum,
    *,
    mode: str,
    contains_llindar: float,
) -> None:
    """Exporta l'informe complet a JSON."""
    dades = {
        "generat_el": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "contains_llindar": contains_llindar,
        "resum": asdict(resum),
        "resultats": [asdict(r) for r in resultats],
    }
    cami.write_text(json.dumps(dades, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nInforme exportat a: {cami}")


# ───────────────────────── CLI ──────────────────────────────────────────────


def construeix_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_eval",
        description=(
            "Avalua el backend IA Nou Patufet (routing, groundedness/contains, "
            "retrieval) pel camí intern de l'orquestrador."
        ),
    )
    p.add_argument(
        "--eval-file",
        type=Path,
        default=_EVAL_SET_PER_DEFECTE,
        help=f"Ruta a l'eval set JSONL (per defecte: {_EVAL_SET_PER_DEFECTE}).",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="Mode offline: usa els dobles de test (sense GPU ni xarxa).",
    )
    p.add_argument(
        "--min-routing",
        type=float,
        default=0.0,
        help=(
            "Llindar mínim de routing accuracy [0..1]. Si la precisió hi queda "
            "per sota, el procés surt amb codi != 0. Per defecte 0.0 (no trenca)."
        ),
    )
    p.add_argument(
        "--contains-llindar",
        type=float,
        default=1.0,
        help=(
            "Fracció [0..1] dels strings de `resposta_esperada_conté` que cal "
            "trobar perquè una entrada compti com a 'contains OK'. Per defecte 1.0."
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Si s'indica, exporta l'informe complet a aquest fitxer JSON.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = construeix_parser().parse_args(argv)

    if args.mock:
        _prepara_entorn_mock()

    try:
        entrades = carrega_eval_set(args.eval_file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not entrades:
        print("ERROR: l'eval set és buit.", file=sys.stderr)
        return 2

    resultats, resum = executa(
        entrades, mock=args.mock, contains_llindar=args.contains_llindar
    )
    imprimeix_informe(resultats, resum)

    if args.out is not None:
        exporta_json(
            args.out,
            resultats,
            resum,
            mode="mock" if args.mock else "real",
            contains_llindar=args.contains_llindar,
        )

    if resum.routing_accuracy < args.min_routing:
        print(
            f"\nFALLA: routing accuracy {resum.routing_accuracy:.1%} "
            f"< llindar {args.min_routing:.1%}.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
