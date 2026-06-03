"""Client LLM OpenAI-compatible (Ollama en dev, vLLM en GPU).

CRÍTIC per a la portabilitat: tota inferència LLM passa per aquest client, que
apunta a `OPENAI_BASE_URL`. MAI es criden OpenAI/Anthropic/Gemini reals: si la
URL base apunta a un domini comercial prohibit, es bloqueja i s'incrementa el
comptador de crides externes.

El client és embolicable per a tests: `set_llm_client()` permet injectar un
doble, i `complete()`/`stream()` són les úniques entrades d'inferència.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import OpenAI

from app.core.config import Settings, get_settings
from app.core import telemetria


@dataclass
class TornAssistent:
    """Resultat d'un torn amb tool-calling: text final i/o crides a tools."""

    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # [{id, name, arguments: dict}]


class LLMClient(Protocol):
    """Interfície mínima d'un client LLM (per a tipatge i dobles de test)."""

    def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...

    def stream(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> Iterator[str]: ...


class OpenAICompatibleClient:
    """Implementació real sobre l'SDK d'OpenAI apuntant a un endpoint local."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if telemetria.es_domini_prohibit(self._settings.openai_base_url):
            telemetria.registra_crida_externa(self._settings.openai_base_url)
            raise RuntimeError(
                "OPENAI_BASE_URL apunta a un proveïdor comercial prohibit. "
                "La inferència ha de ser sempre sobre models auto-allotjats."
            )
        self._client = OpenAI(
            base_url=self._settings.openai_base_url,
            api_key=self._settings.openai_api_key,
        )

    def _model_per(self, catala: bool, usa_batch: bool = False) -> str:
        if usa_batch:
            return self._settings.llm_model_batch  # model gran per a tasques no interactives
        return (
            self._settings.llm_model_catala if catala else self._settings.llm_model
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        catala: bool = False,
        temperatura: float = 0.2,
        usa_batch: bool = False,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Genera una resposta completa (no streaming).

        `usa_batch=True` → usa el model BATCH (gran, no interactiu) de la config.
        `model` → força un model concret (p. ex. el dels skills); té prioritat.
        """
        resposta = self._client.chat.completions.create(
            model=model or self._model_per(catala, usa_batch),
            messages=messages,  # type: ignore[arg-type]
            temperature=temperatura,
            stream=False,
            **kwargs,
        )
        return resposta.choices[0].message.content or ""

    def stream(
        self,
        messages: list[dict[str, str]],
        *,
        catala: bool = False,
        temperatura: float = 0.2,
        usa_batch: bool = False,
        model: str | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Genera la resposta com a flux de deltes de text. `model` força un model concret."""
        flux = self._client.chat.completions.create(
            model=model or self._model_per(catala, usa_batch),
            messages=messages,  # type: ignore[arg-type]
            temperature=temperatura,
            stream=True,
            **kwargs,
        )
        for tros in flux:
            delta = tros.choices[0].delta.content if tros.choices else None
            if delta:
                yield delta

    def chat_amb_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        catala: bool = False,
        temperatura: float = 0.1,
    ) -> TornAssistent:
        """Un torn de xat amb tools disponibles. Retorna text i/o crides a tools.

        Usat pel bucle de tool-calling de l'assistent agèntic. Si `tools` és buit,
        es comporta com un `complete` que retorna el text final.
        """
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        resposta = self._client.chat.completions.create(
            model=self._model_per(catala),
            messages=messages,  # type: ignore[arg-type]
            temperature=temperatura,
            stream=False,
            **kwargs,
        )
        msg = resposta.choices[0].message
        crides: list[dict[str, Any]] = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except (ValueError, TypeError):
                args = {}
            crides.append({"id": tc.id, "name": tc.function.name, "arguments": args})
        return TornAssistent(content=msg.content, tool_calls=crides)


# ── Singleton injectable (per a tests) ──────────────────────────────────────

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Retorna el client LLM actiu, creant-lo de forma mandrosa si cal."""
    global _client
    if _client is None:
        _client = OpenAICompatibleClient()
    return _client


def set_llm_client(client: LLMClient | None) -> None:
    """Injecta (o reinicia amb None) el client LLM. Pensat per a tests."""
    global _client
    _client = client
