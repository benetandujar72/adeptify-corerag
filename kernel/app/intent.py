"""K13·F5a — Resolutor d'INTENCIÓ: text en llenguatge natural → `playbook_id`.

La capa conversacional NO genera plans ni passos: NOMÉS TRIA un playbook del catàleg
SIGNAT (sortida d'un ENUM TANCAT). Aquest mòdul és el nucli d'aquesta garantia.

Decisions de disseny (INV-4 / G-I / INV-1, ancorades al red-team F4↔F5):

- **ENUM TANCAT (INV-4).** `IntentResolver.resol()` NOMÉS pot retornar un `playbook_id`
  que ja és al `SignedPlaybookCatalog`, o `None`. Estructuralment no pot inventar-ne cap:
  itera sobre els playbooks del catàleg i en puntua la coincidència. NO reusa cap
  canonada generativa (res de `skill_builder`): no hi ha generació de passos a partir del text.
- **DETERMINISTA i SENSE LLM (INV-1).** La correspondència és aritmètica pura (solapament
  de tokens normalitzats); no crida cap model ni executa res. Mateix text → mateixa sortida.
- **Vocabulari SIGNAT.** Els `alias` surten de l'artefacte de playbooks signat (G-D): la
  correspondència NL→id és tan fiable com la signatura, no manipulable en runtime.
- **FAIL-CLOSED davant l'ambigüitat.** Si dos playbooks empaten o cap no domina amb prou
  marge, NO s'endevina: es retorna `ambigu=True` amb els candidats perquè un HUMÀ triï de
  la llista tancada. Mai se selecciona "el més probable" a cegues.
- **Frontera PII (G-I).** Si el text conté PII evident (DNI/NIE/email/telèfon), es REBUTJA:
  el CORE no ha de rebre PII; el text es reformula o la PII passa per la seudonimització del
  SUITE. S'usa el MATEIX detector que els playbooks (`conte_pii_evident`), no un de paral·lel.

El `playbook_id` triat encara ha de passar per `instantiate()` (validació de params + guarda
PII) i per la compuerta d'aprovació (K6) abans que res s'executi: aquest mòdul només SELECCIONA.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .playbooks import SignedPlaybookCatalog, conte_pii_evident

# Pesos: un encert per id/alias (vocabulari triat a posta) val més que una paraula solta
# de la descripció (que pot compartir mots genèrics amb altres playbooks).
_PES_ID = 3
_PES_ALIAS = 3
_PES_DESCRIPCIO = 1
# Bonus si el text conté literalment l'id del playbook o una frase d'alias sencera.
_BONUS_FRASE = 5

# Mots buits (ca/es) que NO han de comptar com a coincidència: inflarien la puntuació
# amb soroll comú («una», «de», «el»…) i farien triar per casualitat.
_STOPWORDS = frozenset({
    "el", "la", "els", "les", "un", "una", "uns", "unes", "lo", "los", "las",
    "de", "del", "dels", "d", "a", "al", "als", "en", "amb", "con", "per", "por",
    "para", "que", "i", "y", "o", "u", "the", "of", "to", "and",
    "em", "et", "es", "se", "li", "me", "te", "su", "sus", "mi", "mis",
    "vull", "vol", "quiero", "puc", "pot", "fes", "fer", "fa", "haz", "hacer",
    "si", "us", "vos",
})


def _normalitza(text: str) -> str:
    """Forma canònica: NFKD sense diacrítics + minúscules. Tanca homòglifs accentuats
    (`envià`≡`envia`) i unifica majúscules abans de tokenitzar."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    sense_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sense_accents.casefold()


_RE_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text_normalitzat: str) -> set[str]:
    """Conjunt de tokens alfanumèrics ≥3 car. que no siguin mots buits."""
    return {t for t in _RE_TOKEN.findall(text_normalitzat)
            if len(t) >= 3 and t not in _STOPWORDS}


def _tokens_id(pid: str) -> set[str]:
    """Tokens d'un playbook_id (es parteix per `_`, `.`, `-` i s'aplica el mateix filtre)."""
    return _tokens(_normalitza(pid).replace("_", " ").replace(".", " ").replace("-", " "))


@dataclass(frozen=True)
class IntentCandidate:
    playbook_id: str
    score: int


@dataclass(frozen=True)
class IntentResult:
    """Resultat del resolutor. `match` és None si no hi ha coincidència ÚNICA i clara."""
    match: str | None
    candidates: tuple[IntentCandidate, ...]  # ordenats per score desc (només score>0)
    ambigu: bool
    refusat_pii: bool
    motiu: str


class IntentResolver:
    """Mapeja NL → `playbook_id` sobre el catàleg SIGNAT (ENUM tancat), determinista.

    `min_score`: puntuació mínima perquè un candidat sigui considerat coincidència (per
    defecte 3 = un token d'id/alias, o tres mots de descripció). `marge`: el millor
    candidat ha de superar el segon en ≥ `marge` per ser una tria CLARA; si no, ambigu."""

    def __init__(self, catalog: SignedPlaybookCatalog, *, min_score: int = _PES_ID,
                 marge: int = 1) -> None:
        self._catalog = catalog
        self._min_score = int(min_score)
        self._marge = int(marge)
        # Precòmput del vocabulari per playbook (tot del catàleg signat).
        self._vocab: dict[str, tuple[set[str], set[str], set[str], tuple[str, ...]]] = {}
        for pid in sorted(catalog.ids):  # ordre estable → desempat determinista
            pb = catalog.require(pid)
            id_tok = _tokens_id(pid)
            alias_tok: set[str] = set()
            frases: list[str] = [_normalitza(pid)]
            for a in pb.alias:
                na = _normalitza(a)
                alias_tok |= _tokens(na)
                if na.strip():
                    frases.append(na.strip())
            desc_tok = _tokens(_normalitza(pb.descripcio)) - id_tok - alias_tok
            self._vocab[pid] = (id_tok, alias_tok, desc_tok, tuple(frases))

    def _score(self, pid: str, text_norm: str, toks: set[str]) -> int:
        id_tok, alias_tok, desc_tok, frases = self._vocab[pid]
        s = (_PES_ID * len(toks & id_tok)
             + _PES_ALIAS * len(toks & alias_tok)
             + _PES_DESCRIPCIO * len(toks & desc_tok))
        # Bonus si una frase sencera (id o alias) apareix literalment dins el text.
        if any(len(f) >= 3 and f in text_norm for f in frases):
            s += _BONUS_FRASE
        return s

    def resol(self, text_nl: str) -> IntentResult:
        """Resol el text a un playbook del catàleg. Fail-closed: davant PII o ambigüitat,
        NO selecciona (retorna match=None amb el motiu i, si escau, els candidats)."""
        if not isinstance(text_nl, str) or not text_nl.strip():
            return IntentResult(None, (), ambigu=False, refusat_pii=False,
                                motiu="text buit")
        text_norm = _normalitza(text_nl)
        # G-I: el CORE no rep PII. Es comprova sobre el text CRU i sobre el NORMALITZAT
        # (NFKD) — així una PII ofuscada amb dígits/«@» de doble amplada o accents no
        # evadeix el detector (red-team F5). Mateix detector que playbooks (font única).
        if conte_pii_evident(text_nl) or conte_pii_evident(text_norm):
            return IntentResult(None, (), ambigu=False, refusat_pii=True,
                                motiu="el text sembla contenir PII evident; el CORE no pot rebre PII")
        toks = _tokens(text_norm)
        bruts = [(pid, self._score(pid, text_norm, toks)) for pid in sorted(self._vocab)]
        candidats = tuple(
            IntentCandidate(pid, sc) for pid, sc in
            sorted((p for p in bruts if p[1] > 0), key=lambda x: (-x[1], x[0]))
        )
        if not candidats:
            return IntentResult(None, (), ambigu=False, refusat_pii=False,
                                motiu="cap playbook del catàleg coincideix amb la petició")
        millor = candidats[0]
        if millor.score < self._min_score:
            return IntentResult(None, candidats, ambigu=False, refusat_pii=False,
                                motiu="coincidència massa feble; cal que un humà triï del catàleg")
        segon = candidats[1].score if len(candidats) > 1 else 0
        if millor.score - segon < self._marge:
            return IntentResult(None, candidats, ambigu=True, refusat_pii=False,
                                motiu="empat entre playbooks; cal desambiguació humana")
        return IntentResult(millor.playbook_id, candidats, ambigu=False, refusat_pii=False,
                            motiu=f"coincidència clara amb «{millor.playbook_id}»")
