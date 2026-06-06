"""Endpoints d'agents i estat del sistema.

GET /api/agents        → agents accessibles pel rol de l'usuari (RBAC).
GET /api/system/status → indicadors per a la UI (mockup 03), incloent-hi
                         crides_externes (sempre 0 cap a tercers).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.registry import agents_per_rol_inst
from app.api.schemas import (
    Agent,
    AgentsResponse,
    InstitucioOut,
    StatusIndexacio,
    StatusModel,
    StatusPrivadesa,
    StatusServidor,
    SystemStatusResponse,
)
from app.core import arsul, audit, hwfit, institucions, llicencia, retencio, telemetria
from app.core.config import Settings, get_settings
from app.core.roles import Rol
from app.core.security import Usuari, get_current_user
from app.db.models import Document, User
from app.db.session import get_db
from app.security.produccio_check import executa_check

router = APIRouter(prefix="/api", tags=["sistema"])


@router.get("/agents", response_model=AgentsResponse)
def llista_agents(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentsResponse:
    """Agents que el rol de l'usuari pot usar: built-ins + skills personalitzats de
    la seva institució (càrrega dinàmica)."""
    agents = [
        Agent(
            id=a.id,
            nom=a.nom,
            descripcio=a.descripcio,
            color=a.color,
            rols_permesos=a.rols_str,
        )
        for a in agents_per_rol_inst(db, usuari.institucio, usuari.rol)
    ]
    return AgentsResponse(agents=agents)


@router.get("/institucio/actual", response_model=InstitucioOut)
def institucio_actual(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InstitucioOut:
    """Institució (tenant) de l'usuari autenticat: branding + config per a la UI.

    Accessible a TOTS els rols (a diferència de `/api/admin/institucions`, que és
    només del superadmin). El frontend la fa servir per aplicar el tema (colors,
    logo, nom) després del login. Si la institució encara no existeix a la BD,
    retorna un objecte per defecte perquè la UI no es bloquegi.
    """
    inst = institucions.obte(db, usuari.institucio)
    if inst is None:
        return InstitucioOut(
            slug=usuari.institucio,
            nom="Escola Nou Patufet",
            actiu=True,
            config=None,
            branding=None,
            creat_el=None,
        )
    return InstitucioOut(
        slug=inst.slug,
        nom=inst.nom,
        actiu=inst.actiu,
        config=inst.config,
        branding=inst.branding,
        creat_el=inst.creat_el.isoformat() if inst.creat_el else None,
    )


def _us_actual(db: Session, institucio: str) -> dict[str, int]:
    """Compta l'ús actual de la institució per a la verificació de límits."""
    return {
        "usuaris": int(db.scalar(
            select(func.count(User.id)).where(User.institucio_id == institucio)
        ) or 0),
        "documents": int(db.scalar(
            select(func.count(Document.id)).where(Document.institucio_id == institucio)
        ) or 0),
        # 'alumnes' (PII de menors) viu a la SUITE; el core no el compta.
        "alumnes": 0,
    }


@router.get("/institucio/llicencia")
def institucio_llicencia(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Llicència de la institució de l'usuari + ús actual vs límits.

    Accessible a tots els rols (el frontend l'usa per ocultar mòduls no llicenciats).
    No exposa res sensible: només pla, features actives, límits i ús agregat."""
    inst = institucions.obte(db, usuari.institucio)
    config = inst.config if inst else None
    lic = llicencia.llegeix(config)
    us = _us_actual(db, usuari.institucio)
    return {
        "pla": lic["pla"],
        "pla_nom": lic["pla_nom"],
        "estat": lic["estat"],
        "features": lic["features"],
        "totes_les_features": llicencia.FEATURES,
        "limits": lic["limits"],
        "us_actual": us,
        "data_inici": lic["data_inici"],
        "data_caducitat": lic["data_caducitat"],
        "dies_fins_caducitat": lic["dies_fins_caducitat"],
    }


@router.get("/system/status", response_model=SystemStatusResponse)
def system_status(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SystemStatusResponse:
    """Indicadors d'estat per al dashboard (requereix autenticació: exposa
    host/model/entorn, que no s'han de filtrar a usuaris no autenticats; per a
    una sonda de vida pública useu GET /health)."""
    try:
        n_docs = db.scalar(select(func.count(Document.id))) or 0
        ultima = db.scalar(select(func.max(Document.creat_el)))
        ultima_iso = ultima.isoformat() if ultima else None
    except Exception:
        n_docs = 0
        ultima_iso = None

    backend_model = "vllm" if settings.es_entorn_gpu else "ollama"
    return SystemStatusResponse(
        servidor=StatusServidor(
            actiu=True,
            host=settings.server_host,
            entorn=settings.entorn,
        ),
        indexacio=StatusIndexacio(
            al_dia=True,
            documents=int(n_docs),
            ultima=ultima_iso,
        ),
        privadesa=StatusPrivadesa(
            processament_local=True,
            crides_externes=telemetria.crides_externes(),  # ha de ser 0
            xifratge="AES-256",
            auditat_el="2026-05-18",
        ),
        model=StatusModel(
            nom=settings.llm_model,
            backend=backend_model,
            catala=settings.llm_model_catala,
        ),
        versio=settings.versio,
    )


@router.get("/system/produccio")
def estat_produccio(
    usuari: Usuari = Depends(get_current_user),
) -> dict:
    """Estat de producció (controls de seguretat + robustesa).

    Accessible només a direcció/PAS/superadmin (informació sensible: presència
    de credencials demo, longitud de secrets, etc., però sense exposar valors)."""
    if usuari.rol not in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només la direcció/PAS pot consultar l'estat de producció.",
        )
    return executa_check()


@router.get("/system/hardware-fit")
def system_hardware_fit(
    usuari: Usuari = Depends(get_current_user),
) -> dict:
    """Dimensionament de models locals segons GPU/RAM/disc disponibles.

    No descarrega models ni arrenca cap servei. Exposa inventari de maquina i
    decisions de desplegament, per tant queda limitat a direccio/PAS/superadmin.
    """
    if usuari.rol not in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només la direcció/PAS pot consultar el dimensionament de models.",
        )
    return hwfit.informe_hwfit()


@router.get("/system/retencio")
def system_retencio(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Informe dry-run de retenció RGPD.

    No esborra cap dada. Serveix per revisar quantes converses/feedback/auditoria
    quedarien afectades abans que Direccio/DPD aprovin una politica destructiva.
    """
    if usuari.rol not in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només la direcció/PAS pot consultar l'informe de retenció.",
        )
    return retencio.build_report(db)


@router.get("/system/arsul/export")
def system_arsul_export(
    usuari_objectiu: str,
    institucio: str | None = None,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Exportacio assistida ARSUL d'un usuari del centre.

    No esborra ni anonimitza dades. El paquet exclou secrets d'autenticacio
    (password_hash, totp_secret) i queda limitat a la institucio autoritzada.
    """
    if usuari.rol not in {Rol.DIRECCIO, Rol.PAS, Rol.SUPERADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Només la direcció/PAS pot generar exports ARSUL.",
        )
    institucio_objectiu = institucio or usuari.institucio
    if usuari.rol != Rol.SUPERADMIN and institucio_objectiu != usuari.institucio:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No pots exportar dades d'una altra institució.",
        )
    try:
        paquet = arsul.build_export(
            db, username=usuari_objectiu, institucio_id=institucio_objectiu
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuari no trobat en aquesta institució.",
        ) from None

    audit.registra_accio(
        db,
        usuari=usuari.usuari,
        rol=usuari.rol.value,
        accio="arsul_export",
        detalls={
            "subject": usuari_objectiu,
            "institucio": institucio_objectiu,
            "summary": paquet["summary"],
        },
        base_legal="art. 15 i 20 RGPD (dret d'acces i portabilitat)",
    )
    return paquet
