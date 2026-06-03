"""Passarel·la de privadesa (Privacy Gateway) — Fase 4.

ÚNIC punt pel qual passen totes les crides a sistemes externs (Google Drive,
Gmail, Calendar). Abans d'executar: comprova que la integració és activa, que
l'operació és a l'allow-list i que el recurs (carpeta/calendari) està aprovat;
registra l'INTENT a l'auditoria. Després d'executar, registra el RESULTAT i
incrementa el comptador d'integracions (transparència; NO és inferència LLM).

Cap connector extern s'ha d'invocar sense passar per aquí. L'acció d'auditoria
és `mcp_<connector>_intent` / `mcp_<connector>_resultat` (connector deduït de
l'operació, p. ex. `drive.list` → `drive`).
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import audit, telemetria
from app.core.roles import Rol
from app.core.security import Usuari
from app.mcp.policies import (
    OPERACIONS_CALENDAR,
    OPERACIONS_DRIVE,
    OPERACIONS_GMAIL,
    OPERACIONS_LMS,
    PoliticaGoogle,
    PoliticaLms,
    politica_google,
    politica_lms,
)

# Operacions extra-sensibles (lectura de bústies): NOMÉS direcció (i superadmin).
ROLS_LECTURA_CORREU = {Rol.DIRECCIO, Rol.SUPERADMIN}


class PrivacyGateway:
    def __init__(self, db: Session, usuari: Usuari, config: dict | None) -> None:
        self.db = db
        self.usuari = usuari
        self.pol: PoliticaGoogle = politica_google(config)
        self.pol_lms: PoliticaLms = politica_lms(config)

    # ── Autorització (abans de tocar Google) ────────────────────────────────
    def _exigeix_actiu(self) -> None:
        if not self.pol.actiu:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La integració de Google està desactivada per a aquesta institució.",
            )

    def autoritza_drive(self, operacio: str, folder_id: str | None = None) -> None:
        self._exigeix_actiu()
        if operacio not in OPERACIONS_DRIVE:
            self._intent(operacio, folder_id, permes=False, motiu="operacio_no_permesa")
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Operació no permesa: {operacio}")
        if folder_id is not None and folder_id not in self.pol.drive_folders:
            self._intent(operacio, folder_id, permes=False, motiu="carpeta_no_aprovada")
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Carpeta no aprovada (allow-list). Afegeix-la a la configuració d'integracions.",
            )
        self._intent(operacio, folder_id, permes=True)

    def autoritza_gmail(self, operacio: str, compte: str | None = None) -> None:
        self._exigeix_actiu()
        if operacio not in OPERACIONS_GMAIL:
            self._intent(operacio, compte, permes=False, motiu="operacio_no_permesa")
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Operació no permesa: {operacio}")
        # Lectura de bústies: NOMÉS direcció (dada molt sensible).
        if operacio == "gmail.read" and self.usuari.rol not in ROLS_LECTURA_CORREU:
            self._intent(operacio, compte, permes=False, motiu="rol_no_autoritzat_lectura")
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Només la direcció pot consultar el contingut de les bústies de correu.",
            )
        if not self.pol.gmail_sender and not self.pol.gmail_comptes:
            self._intent(operacio, compte, permes=False, motiu="cap_compte_configurat")
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Cal configurar com a mínim un compte de correu (remitent o allow-list) a la integració.",
            )
        # GARANTIA: només es poden gestionar els comptes de l'allow-list.
        compte_efectiu = compte or self.pol.gmail_sender
        if compte_efectiu not in self.pol.gmail_comptes:
            self._intent(operacio, compte_efectiu, permes=False, motiu="compte_no_autoritzat")
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Compte de correu no autoritzat: {compte_efectiu}. Afegeix-lo a l'allow-list de comptes.",
            )
        self._intent(operacio, compte_efectiu, permes=True)

    def autoritza_calendar(self, operacio: str, calendar_id: str | None = None) -> None:
        self._exigeix_actiu()
        if operacio not in OPERACIONS_CALENDAR:
            self._intent(operacio, calendar_id, permes=False, motiu="operacio_no_permesa")
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Operació no permesa: {operacio}")
        if calendar_id is not None and calendar_id not in self.pol.calendar_ids:
            self._intent(operacio, calendar_id, permes=False, motiu="calendari_no_aprovat")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Calendari no aprovat (allow-list).")
        self._intent(operacio, calendar_id, permes=True)

    def autoritza_lms(self, operacio: str, connector: str, course_id: str) -> None:
        if not self.pol_lms.actiu:
            self._intent(operacio, course_id, permes=False, motiu="lms_desactivat")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La integració LMS està desactivada per a aquesta institució.",
            )
        if operacio not in OPERACIONS_LMS:
            self._intent(operacio, course_id, permes=False, motiu="operacio_no_permesa")
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Operació no permesa: {operacio}")
        if connector == "moodle":
            if not self.pol_lms.moodle_actiu or course_id not in self.pol_lms.moodle_courses:
                self._intent(operacio, course_id, permes=False, motiu="curs_moodle_no_aprovat")
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Curs Moodle no aprovat.")
        elif connector == "classroom":
            if not self.pol_lms.classroom_actiu or course_id not in self.pol_lms.classroom_courses:
                self._intent(operacio, course_id, permes=False, motiu="curs_classroom_no_aprovat")
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Curs Classroom no aprovat.")
        else:
            self._intent(operacio, course_id, permes=False, motiu="connector_no_permes")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Connector LMS no permès.")
        self._intent(operacio, f"{connector}:{course_id}", permes=True)

    # ── Registre del resultat (després de la crida) ──────────────────────────
    def registra_resultat(self, operacio: str, ok: bool, detall: str | None = None) -> None:
        connector = self._connector(operacio)
        telemetria.registra_crida_integracio(connector)
        audit.registra_accio(
            self.db, usuari=self.usuari.usuari, rol=self.usuari.rol.value,
            accio=f"mcp_{connector}_resultat",
            detalls={
                "operacio": operacio, "ok": ok,
                "detall": (detall or "")[:200], "institucio": self.usuari.institucio,
            },
        )

    # ── Intern ────────────────────────────────────────────────────────────────
    @staticmethod
    def _connector(operacio: str) -> str:
        return operacio.split(".", 1)[0]

    def _intent(self, operacio: str, recurs: str | None, permes: bool, motiu: str | None = None) -> None:
        audit.registra_accio(
            self.db, usuari=self.usuari.usuari, rol=self.usuari.rol.value,
            accio=f"mcp_{self._connector(operacio)}_intent",
            detalls={
                "operacio": operacio, "recurs": recurs, "permes": permes,
                **({"motiu": motiu} if motiu else {}), "institucio": self.usuari.institucio,
            },
        )
