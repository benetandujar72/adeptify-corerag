"""Graf d'orquestració LangGraph.

Nodes del graf (mockup 01, passos 2–5):
  classifica → comprova_rbac → recupera (RAG) → genera

L'estat flueix entre nodes amb la pregunta, la decisió de routing, els resultats
de retrieval i el prompt final. La generació es fa fora del graf (streaming o
no) reutilitzant el prompt construït pel node `genera`, perquè el contracte
exigeix SSE token a token.

Memòria conversacional: s'injecta l'historial (darrers missatges) recuperat de
la BD per `conversation_id`.

Si LangGraph no està instal·lat, es degrada a una execució seqüencial
equivalent (mateixos nodes, mateix ordre) perquè els tests funcionin sense la
dependència pesada.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.agents.registry import AgentDef, carrega_agents, get_agent
from app.core.config import get_settings
from app.core.roles import Rol
from app.mcp.server import get_mcp_server
from app.orchestrator import rbac
from app.orchestrator.router import DecisioRouting, classifica
from app.rag.llm import get_llm_client
from app.rag.retriever import ResultatRetrieval, agrega_fonts, retrieve


class EstatOrq(TypedDict, total=False):
    """Estat que circula pel graf."""

    message: str
    agent_suggerit: str
    rol: str
    institucio: str
    usuari_nom: str
    historial: list[dict[str, str]]
    decisio: DecisioRouting
    agent: AgentDef
    resultats: list[ResultatRetrieval]
    email_context: list[str]
    curriculum_context: list[str]
    cag_context: list[str]
    lomloe_context: list[str]
    prompt_messages: list[dict[str, str]]
    catala: bool


@dataclass
class ResultatOrquestracio:
    """Sortida de la preparació d'una resposta (abans de generar text)."""

    agent_id: str
    agent: AgentDef
    intencio: str
    reencaminat: bool
    resultats: list[ResultatRetrieval] = field(default_factory=list)
    prompt_messages: list[dict[str, str]] = field(default_factory=list)
    catala: bool = False
    # Tool-calling (assistent agèntic): resposta ja generada pel bucle de tools,
    # eines de lectura usades i proposta d'escriptura pendent de confirmació humana.
    resposta_precomputada: str | None = None
    tools_usades: list[str] = field(default_factory=list)
    proposta: dict[str, Any] | None = None
    model_utilitzat: str | None = None

    @property
    def fonts(self):
        return agrega_fonts(self.resultats)


def _construeix_prompt(
    agent: AgentDef,
    message: str,
    resultats: list[ResultatRetrieval],
    historial: list[dict[str, str]],
    llengua: str,
    email_context: list[str] | None = None,
    curriculum_context: list[str] | None = None,
    cag_context: list[str] | None = None,
    lomloe_context: list[str] | None = None,
) -> list[dict[str, str]]:
    """Construeix els missatges per al LLM: sistema + context + historial + pregunta."""
    blocs_context = []
    for i, r in enumerate(resultats, start=1):
        # Sanititzem el nom de fitxer abans d'interpolar-lo al prompt: un document
        # amb un nom manipulat (claudàtors, salts de línia) no ha de poder injectar
        # estructura ni instruccions al context del LLM (injecció indirecta).
        nom = re.sub(r"[\[\]{}<>\r\n]", " ", r.filename or "").strip()
        ref = f"[{i}] {nom}" + (f" (pàg. {r.pagina})" if r.pagina else "")
        blocs_context.append(f"{ref}\n{r.contingut}")
    context = "\n\n".join(blocs_context) if blocs_context else "(sense context recuperat)"

    # Humanisme digital (Conclusions UE C/2026/2826; art. 14/50 AI Act): el
    # guardrail emmarca SEMPRE la persona de l'agent (suport, no substitució).
    from app.core.principis import GUARDRAIL_HUMANISME

    sistema = f"{GUARDRAIL_HUMANISME}\n\n{agent.system_prompt}"
    if agent.bilingue and llengua == "es":
        sistema += "\n\nLa consulta està en castellà: respon en castellà."

    # Context de correu (només per a l'agent de seguiment de direcció).
    bloc_correu = ""
    if email_context:
        resum = "\n".join(f"- {l}" for l in email_context)
        bloc_correu = (
            f"\n\nCORREUS DE LES BÚSTIES REGISTRADES (resum, dades confidencials):\n{resum}"
        )

    bloc_curricular = ""
    if curriculum_context:
        resum = "\n".join(f"- {l}" for l in curriculum_context)
        bloc_curricular = (
            "\n\nPERFIL CURRICULAR DETECTAT (no és font normativa; usa'l per "
            "adequar la proposta al país, comunitat autònoma, etapa, curs, "
            f"nivell i matèria indicats):\n{resum}"
        )

    # Referència LOMLOE estructurada per a l'agent d'avaluació i Copilot.
    bloc_lomloe = ""
    if lomloe_context:
        resum = "\n".join(f"- {l}" for l in lomloe_context)
        bloc_lomloe = (
            "\n\nCRITERIS D'AVALUACIÓ LOMLOE DEL CENTRE (referència estructurada; "
            "usa aquests codis i enunciats per fonamentar rúbriques i el mapeig "
            f"competencial):\n{resum}"
        )

    bloc_cag = ""
    if cag_context:
        resum = "\n".join(f"- {l}" for l in cag_context)
        bloc_cag = (
            "\n\nPAQUET CAG DEL CURS I DEL CENTRE (guia d'ús dels materials "
            f"docents indexats; no és font normativa):\n{resum}"
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": sistema}]
    # Memòria conversacional (darrers torns).
    messages.extend(historial[-6:])
    messages.append(
        {
            "role": "user",
            "content": (
                f"CONTEXT (documents del centre):\n{context}{bloc_correu}{bloc_lomloe}{bloc_cag}\n\n"
                f"{bloc_curricular}\n\n"
                f"PREGUNTA: {message}\n\n"
                "Respon basant-te en el context i cita les fonts pertinents."
            ),
        }
    )
    return messages


class Orchestrator:
    """Orquestrador que prepara la resposta (routing + RBAC + RAG + prompt)."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._mcp = get_mcp_server(db)
        self._graph = self._compila_graf()
        # Mapa d'agents per a la petició (built-ins + personalitzats de la institució).
        self._agents_inst: dict[str, AgentDef] | None = None

    # ── Construcció del graf LangGraph (amb degradació) ──────────────────────

    def _compila_graf(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:  # pragma: no cover - sense langgraph instal·lat
            return None

        graf = StateGraph(EstatOrq)
        graf.add_node("classifica", self._node_classifica)
        graf.add_node("comprova_rbac", self._node_rbac)
        graf.add_node("recupera", self._node_recupera)
        graf.add_node("genera", self._node_prepara_prompt)
        graf.add_edge(START, "classifica")
        graf.add_edge("classifica", "comprova_rbac")
        graf.add_edge("comprova_rbac", "recupera")
        graf.add_edge("recupera", "genera")
        graf.add_edge("genera", END)
        return graf.compile()

    # ── Nodes ────────────────────────────────────────────────────────────────

    def _node_classifica(self, estat: EstatOrq) -> dict[str, Any]:
        decisio = classifica(
            estat["message"], estat["agent_suggerit"], Rol(estat["rol"]),
            agents=self._agents_inst,
        )
        return {"decisio": decisio, "catala": decisio.llengua == "ca"}

    def _node_rbac(self, estat: EstatOrq) -> dict[str, Any]:
        decisio = estat["decisio"]
        agent = rbac.comprova_acces_agent(
            decisio.agent_id, Rol(estat["rol"]), agents=self._agents_inst
        )
        return {"agent": agent}

    def _node_recupera(self, estat: EstatOrq) -> dict[str, Any]:
        rol = Rol(estat["rol"])
        # Documentació de gestió de l'aplicació: només per a admin/direcció/PAS.
        incloure_admin = rol in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}
        # Coneixement propi de l'skill (P3): si l'agent en declara, el RAG es limita
        # a aquests documents. Els agents integrats no en tenen → cap restricció.
        agent_prev = estat.get("agent")
        coneixement = (
            set(agent_prev.coneixement)
            if agent_prev is not None and agent_prev.coneixement
            else None
        )
        resultats = retrieve(
            self._db,
            estat["message"],
            doc_ids_permesos=rbac.doc_ids_permesos(rol),
            institucio_id=estat.get("institucio"),
            incloure_admin=incloure_admin,
            coneixement_doc_ids=coneixement,
        )
        sortida: dict[str, Any] = {"resultats": resultats}
        # Seguiment de correu: NOMÉS l'agent dedicat i NOMÉS rol direcció.
        agent = estat.get("agent")
        if agent is not None and agent.id == "seguiment_correu" and rol == Rol.DIRECCIO:
            try:
                from app.core.security import Usuari
                from app.integracions.seguiment_correu import context_correu

                u = Usuari(
                    usuari=estat.get("usuari_nom", ""),
                    rol=rol,
                    institucio=estat.get("institucio", "nou_patufet"),
                )
                # Tool-calling: recupera fils RELLEVANTS a la pregunta (no només recents).
                sortida["email_context"] = context_correu(
                    self._db, u, consulta=estat["message"]
                )
            except Exception:  # noqa: BLE001 - el seguiment no ha de trencar el xat
                sortida["email_context"] = []
        # Avaluació i Copilot didàctic: injecta la referència estructurada del
        # centre (competències + criteris) perquè les rúbriques, SdA, exercicis,
        # adaptacions i evidències es fonamentin en codis reals del centre.
        agents_curriculars = {
            "avaluacions",
            "copilot_didactic",
            "copilot_context",
            "copilot_contingut",
            "copilot_format",
            "copilot_exercicis",
            "copilot_rubriques",
            "copilot_adaptacions",
            "copilot_seguiment",
            "copilot_butlleti",
            "copilot_qualitat",
        }
        if agent is not None and agent.id in agents_curriculars:
            try:
                from app.agents.context_curricular import (
                    extreu_perfil_curricular,
                    linies_perfil_curricular,
                )

                perfil = extreu_perfil_curricular(estat["message"])
                sortida["curriculum_context"] = linies_perfil_curricular(estat["message"])
                nivell = perfil.get("nivell")
                area = perfil.get("materia")
            except Exception:  # noqa: BLE001 - el context no ha de trencar el xat
                sortida["curriculum_context"] = []
                nivell = None
                area = None
            try:
                from app.agents.context_cag import context_cag

                sortida["cag_context"] = context_cag(
                    self._db, estat.get("institucio", "nou_patufet")
                )
            except Exception:  # noqa: BLE001 - el context no ha de trencar el xat
                sortida["cag_context"] = []
            try:
                from app.agents.context_avaluacio import context_lomloe

                sortida["lomloe_context"] = context_lomloe(
                    self._db, estat.get("institucio", "nou_patufet"), nivell=nivell, area=area
                )
            except Exception:  # noqa: BLE001 - el context no ha de trencar el xat
                sortida["lomloe_context"] = []
        return sortida

    def _node_prepara_prompt(self, estat: EstatOrq) -> dict[str, Any]:
        prompt = _construeix_prompt(
            estat["agent"],
            estat["message"],
            estat["resultats"],
            estat.get("historial", []),
            estat["decisio"].llengua,
            estat.get("email_context", []),
            estat.get("curriculum_context", []),
            estat.get("cag_context", []),
            estat.get("lomloe_context", []),
        )
        return {"prompt_messages": prompt}

    # ── API pública ──────────────────────────────────────────────────────────

    def prepara(
        self,
        message: str,
        agent_suggerit: str,
        rol: Rol,
        historial: list[dict[str, str]] | None = None,
        institucio: str = "nou_patufet",
        usuari_nom: str = "",
    ) -> ResultatOrquestracio:
        """Executa el graf fins a tenir el prompt llest (sense generar text)."""
        estat_inicial: EstatOrq = {
            "message": message,
            "agent_suggerit": agent_suggerit,
            "rol": rol.value,
            "institucio": institucio,
            "usuari_nom": usuari_nom,
            "historial": historial or [],
        }
        # Agents disponibles per a aquesta petició: built-ins + personalitzats (skills)
        # de la institució (càrrega dinàmica, sense rebuild).
        self._agents_inst = carrega_agents(self._db, institucio)

        if self._graph is not None:
            estat: dict[str, Any] = dict(self._graph.invoke(estat_inicial))
        else:
            # Degradació seqüencial equivalent.
            estat = dict(estat_inicial)
            estat.update(self._node_classifica(estat))  # type: ignore[arg-type]
            estat.update(self._node_rbac(estat))  # type: ignore[arg-type]
            estat.update(self._node_recupera(estat))  # type: ignore[arg-type]
            estat.update(self._node_prepara_prompt(estat))  # type: ignore[arg-type]

        decisio: DecisioRouting = estat["decisio"]
        agent: AgentDef = estat["agent"]
        # Bucle de tool-calling per a l'assistent agèntic (lectura auto, escriptura proposa).
        resposta_precomputada: str | None = None
        tools_usades: list[str] = []
        proposta: dict[str, Any] | None = None
        if agent.id == "assistent_admin":
            resposta_precomputada, tools_usades, proposta = self._resol_tools(
                agent, estat.get("prompt_messages", []), rol, institucio,
                usuari_nom, estat.get("catala", True) and not agent.bilingue,
            )
        catala = estat.get("catala", True)
        return ResultatOrquestracio(
            agent_id=agent.id,
            agent=agent,
            intencio=decisio.intencio,
            reencaminat=decisio.reencaminat,
            resultats=estat.get("resultats", []),
            prompt_messages=estat.get("prompt_messages", []),
            catala=catala,
            resposta_precomputada=resposta_precomputada,
            tools_usades=tools_usades,
            proposta=proposta,
            model_utilitzat=self._model_efectiu(agent, catala),
        )

    def _resol_tools(
        self,
        agent: AgentDef,
        base_messages: list[dict[str, Any]],
        rol: Rol,
        institucio: str,
        usuari_nom: str,
        catala: bool,
    ) -> tuple[str | None, list[str], dict[str, Any] | None]:
        """Bucle de tool-calling. Lectura → s'executa; escriptura → es proposa.

        Retorna (resposta_final, tools_usades, proposta) o (None, [], None) si no
        aplica (client sense suport, sense tools, o error → degrada al flux normal).
        """
        try:
            from app.agents import tools_domini
            from app.core.security import Usuari

            client = get_llm_client()
            fn = getattr(client, "chat_amb_tools", None)
            schema = tools_domini.tools_per_agent(agent.id)
            if fn is None or not schema:
                return None, [], None

            u = Usuari(usuari=usuari_nom or "", rol=rol, institucio=institucio)
            msgs: list[dict[str, Any]] = list(base_messages)
            usades: list[str] = []
            proposta: dict[str, Any] | None = None

            def _final(text: str | None) -> str:
                if text and text.strip():
                    return text
                if proposta:
                    return ("He preparat una proposta; revisa-la i confirma-la a la "
                            "pàgina corresponent per executar-la.")
                return "No he trobat informació per respondre la consulta."

            for _ in range(4):
                torn = fn(msgs, schema, catala=catala)
                if not torn.tool_calls:
                    return _final(torn.content), usades, proposta
                msgs.append({
                    "role": "assistant",
                    "content": torn.content or "",
                    "tool_calls": [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in torn.tool_calls
                    ],
                })
                for tc in torn.tool_calls:
                    res = tools_domini.executa_tool(self._db, u, tc["name"], tc["arguments"])
                    usades.append(tc["name"])
                    if isinstance(res, dict) and res.get("proposta"):
                        proposta = res
                    msgs.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps(res, ensure_ascii=False)})
            # Límit d'iteracions assolit: força una resposta final sense tools.
            return _final(client.complete(msgs, catala=catala)), usades, proposta
        except Exception:  # noqa: BLE001 - el tool-calling no ha de trencar el xat
            return None, [], None

    def _model_efectiu(self, agent: AgentDef, catala: bool) -> str:
        """Nom del model que es fara servir per generar la resposta."""
        settings = get_settings()
        if agent.personalitzat:
            return settings.llm_model_skills
        if catala and not agent.bilingue:
            return settings.llm_model_catala
        return settings.llm_model

    def genera(self, prep: ResultatOrquestracio) -> str:
        """Genera la resposta completa (no streaming)."""
        if prep.resposta_precomputada is not None:
            return prep.resposta_precomputada  # ja resolta pel bucle de tools
        client = get_llm_client()
        return client.complete(
            prep.prompt_messages, model=prep.model_utilitzat
        )

    def genera_stream(self, prep: ResultatOrquestracio) -> Iterator[str]:
        """Genera la resposta com a flux de deltes de text (per a SSE)."""
        if prep.resposta_precomputada is not None:
            # Resposta ja generada pel bucle de tools: la trossegem per a l'SSE.
            for tros in re.findall(r"\S+\s*", prep.resposta_precomputada):
                yield tros
            return
        client = get_llm_client()
        yield from client.stream(
            prep.prompt_messages, model=prep.model_utilitzat
        )

    def prova(
        self, agent: AgentDef, message: str, rol: Rol, institucio: str
    ) -> tuple[str, list[ResultatRetrieval]]:
        """Prova efímera d'un skill (P3): retrieval (amb el coneixement de l'agent) +
        prompt + generació, SENSE desar res ni crear conversa. Reusa el mateix
        pipeline que el xat real perquè la prova sigui representativa."""
        incloure_admin = rol in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}
        coneixement = set(agent.coneixement) if agent.coneixement else None
        resultats = retrieve(
            self._db,
            message,
            doc_ids_permesos=rbac.doc_ids_permesos(rol),
            institucio_id=institucio,
            incloure_admin=incloure_admin,
            coneixement_doc_ids=coneixement,
        )
        prompt = _construeix_prompt(agent, message, resultats, [], "ca")
        # La prova és d'un skill → usa el model de qualitat lingüística.
        text = get_llm_client().complete(
            prompt, model=self._model_efectiu(agent, True)
        )
        return text, resultats


def get_orchestrator(db: Session) -> Orchestrator:
    """Construeix un orquestrador lligat a la sessió de BD donada."""
    return Orchestrator(db)
