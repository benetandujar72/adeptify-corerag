"""Polítiques (allow-list) de les integracions externes (Fase 4).

Defineix, de manera declarativa i per institució, quines operacions i quins
recursos (carpetes de Drive, calendaris) estan aprovats. La passarel·la de
privadesa (`gateway.py`) hi consulta abans d'executar cap crida externa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:  # CORE: el mòdul d'integracions externes (Drive/Gmail/LMS) viu a la SUITE.
    from app.integracions import google as gintegr
    from app.integracions import lms as lmsintegr
except Exception:  # noqa: BLE001 - sense integracions, les polítiques queden inactives
    class _SenseIntegracions:
        @staticmethod
        def llegeix_emmascarat(config: dict | None) -> dict:
            return {}

    gintegr = _SenseIntegracions()  # type: ignore[assignment]
    lmsintegr = _SenseIntegracions()  # type: ignore[assignment]

# Operacions permeses per connector.
OPERACIONS_DRIVE = frozenset({"drive.list", "drive.read", "drive.ingest"})  # només lectura
# gmail.draft: esborranys (mai enviar). gmail.read: lectura de bústies (NOMÉS
# direcció; dada altament sensible → auditat i acotat a comptes registrats).
OPERACIONS_GMAIL = frozenset({"gmail.draft", "gmail.read"})
OPERACIONS_CALENDAR = frozenset({"calendar.list", "calendar.create"})
OPERACIONS_LMS = frozenset({"lms.list", "lms.ingest"})


@dataclass
class PoliticaGoogle:
    actiu: bool = False
    drive_folders: set[str] = field(default_factory=set)
    calendar_ids: set[str] = field(default_factory=set)
    gmail_sender: str = ""
    # Comptes de correu que l'assistent pot gestionar (allow-list).
    gmail_comptes: set[str] = field(default_factory=set)


@dataclass
class PoliticaLms:
    actiu: bool = False
    moodle_actiu: bool = False
    moodle_courses: set[str] = field(default_factory=set)
    classroom_actiu: bool = False
    classroom_courses: set[str] = field(default_factory=set)


def politica_google(config: dict | None) -> PoliticaGoogle:
    """Construeix la política a partir de la config de la institució."""
    g = gintegr.llegeix_emmascarat(config)  # no calen secrets per a la política
    sender = g.get("gmail_sender") or ""
    comptes = set(g.get("gmail_comptes") or [])
    if sender:
        comptes.add(sender)  # el remitent per defecte sempre és un compte permès
    return PoliticaGoogle(
        actiu=bool(g.get("actiu")),
        drive_folders=set(g.get("drive_folders") or []),
        calendar_ids=set(g.get("calendar_ids") or []),
        gmail_sender=sender,
        gmail_comptes=comptes,
    )


def politica_lms(config: dict | None) -> PoliticaLms:
    l = lmsintegr.llegeix_emmascarat(config)
    return PoliticaLms(
        actiu=bool(l.get("actiu")),
        moodle_actiu=bool(l.get("moodle_actiu")),
        moodle_courses=set(str(x) for x in (l.get("moodle_course_ids") or [])),
        classroom_actiu=bool(l.get("classroom_actiu")),
        classroom_courses=set(str(x) for x in (l.get("classroom_course_ids") or [])),
    )
