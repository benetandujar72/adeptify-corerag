"""Endpoints d'autenticació (MVP simplificat).

POST /api/auth/login → emet un JWT per a un usuari i rol.
GET  /api/auth/me    → retorna la identitat del token.

Al MVP el login és una sessió simple per rol (sense contrasenya); en el futur
es connectarà SSO Clickedu.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    IdiomaUpdate,
    InstitucioPublica,
    InstitucionsPubliquesResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MfaCodi,
    MfaEstat,
    MfaSetupResponse,
)
from app.core import audit, institucions, rate_limit, totp, users
from app.core.config import Settings, get_settings
from app.core.roles import Rol
from app.core.security import (
    ROLS_ACCES_REMOT,
    Usuari,
    acces_es_remot,
    crea_token,
    get_current_user,
    ip_de_peticio,
)
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    cos: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Autentica amb usuari + contrasenya contra el registre d'usuaris."""
    if not cos.contrasenya:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cal indicar la contrasenya.",
        )
    # Rate-limit anti força bruta: bloqueig temporal del compte després de N fallits.
    clau_rl = f"{cos.usuari}@{cos.institucio or '-'}"
    restant = rate_limit.segons_bloqueig_restant(clau_rl)
    if restant > 0:
        try:
            audit.registra_accio(
                db, usuari=cos.usuari, rol="?", accio="login_bloquejat",
                detalls={"institucio": cos.institucio, "segons_restants": restant},
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Massa intents fallits. Torna-ho a provar d'aquí a {restant // 60 + 1} min.",
        )
    user = users.autentica(db, cos.usuari, cos.contrasenya, institucio_id=cos.institucio)
    if user is None:
        rate_limit.registra_fallit(
            clau_rl, settings.login_max_intents, settings.login_bloqueig_minuts * 60
        )
        # Auditem l'intent fallit (forense) sense revelar si l'usuari existeix.
        try:
            audit.registra_accio(
                db, usuari=cos.usuari, rol="?", accio="login_fallit"
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuari o contrasenya incorrectes (o usuari desactivat).",
        )
    # ── Segon factor (MFA/TOTP) si l'usuari el té activat ──
    if user.totp_actiu:
        if not cos.codi_mfa:
            # Credencials correctes però cal el codi: el frontend mostrarà el camp.
            return LoginResponse(token="", rol=user.rol, mfa_required=True)
        if not totp.verifica(user.totp_secret or "", cos.codi_mfa):
            rate_limit.registra_fallit(
                clau_rl, settings.login_max_intents, settings.login_bloqueig_minuts * 60
            )
            try:
                audit.registra_accio(
                    db, usuari=user.username, rol=user.rol, accio="login_fallit",
                    detalls={"motiu": "codi_mfa_incorrecte"},
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Codi de verificació (MFA) incorrecte.",
            )
    rate_limit.registra_exit(clau_rl)  # credencials (+ MFA) correctes → reseteja el comptador
    rol = Rol(user.rol)
    ip = ip_de_peticio(request, settings)
    remot = acces_es_remot(request, settings)
    # Control d'accés remot: si la connexió és remota i el rol no és d'administració,
    # no s'emet cap token (defensa a la porta d'entrada). Vegeu `comprova_acces_remot`.
    if settings.acces_remot_admin_only and remot and rol not in ROLS_ACCES_REMOT:
        try:
            audit.registra_accio(
                db, usuari=user.username, rol=rol.value, accio="acces_remot_denegat",
                detalls={"ip": ip, "motiu": "rol no autoritzat per a accés remot"},
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Accés remot restringit al rol d'administració. "
                "Connecta't des de la xarxa del centre per a aquest rol."
            ),
        )
    token = crea_token(user.username, rol, institucio=user.institucio_id)
    try:
        audit.registra_accio(
            db, usuari=user.username, rol=rol.value, accio="login",
            detalls={"ip": ip, "remot": remot},
        )
    except Exception:
        pass
    return LoginResponse(token=token, rol=rol.value)


@router.get("/institucions", response_model=InstitucionsPubliquesResponse)
def institucions_publiques(db: Session = Depends(get_db)) -> InstitucionsPubliquesResponse:
    """Llista MÍNIMA d'institucions ACTIVES per a la pantalla de selecció (pre-login).

    PÚBLIC (sense auth): retorna només slug, nom i branding —cap dada sensible ni
    config. El frontend l'usa per: si n'hi ha una de sola, autoseleccionar-la i
    ometre la pantalla; si n'hi ha diverses, mostrar el selector.
    """
    items = [
        InstitucioPublica(slug=i.slug, nom=i.nom, branding=i.branding)
        for i in institucions.llista(db)
        if i.actiu
    ]
    return InstitucionsPubliquesResponse(institucions=items)


@router.get("/me", response_model=MeResponse)
def me(
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Retorna la identitat de l'usuari autenticat (inclou l'idioma preferit)."""
    u = users.obte_usuari(db, usuari.usuari, institucio_id=usuari.institucio)
    idioma = (u.idioma or "ca") if u else "ca"
    return MeResponse(usuari=usuari.usuari, rol=usuari.rol.value, idioma=idioma)


_IDIOMES_ADMESOS = {"ca", "es", "eu"}


@router.patch("/idioma", response_model=MeResponse)
def actualitza_idioma(
    cos: IdiomaUpdate,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Desa l'idioma preferit de l'usuari (ca/es/eu). Es respecta a futurs accessos."""
    if cos.idioma not in _IDIOMES_ADMESOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Idioma no admès. Valors vàlids: {sorted(_IDIOMES_ADMESOS)}.",
        )
    u = users.obte_usuari(db, usuari.usuari, institucio_id=usuari.institucio)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuari no trobat.")
    u.idioma = cos.idioma
    db.commit()
    return MeResponse(usuari=usuari.usuari, rol=usuari.rol.value, idioma=u.idioma)


# ───────────────────────── MFA / 2FA (TOTP) ─────────────────────────────────
# L'usuari autenticat gestiona el SEU propi segon factor.


@router.get("/mfa/estat", response_model=MfaEstat)
def mfa_estat(
    usuari: Usuari = Depends(get_current_user), db: Session = Depends(get_db),
) -> MfaEstat:
    u = users.obte_usuari(db, usuari.usuari, usuari.institucio)
    return MfaEstat(actiu=bool(u and u.totp_actiu))


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(
    usuari: Usuari = Depends(get_current_user), db: Session = Depends(get_db),
) -> MfaSetupResponse:
    """Inicia l'enrolment: genera un secret (encara NO activat) i retorna el secret
    (entrada manual) + l'URI otpauth (per al QR). Cal confirmar amb un codi a /activar."""
    secret = users.inicia_mfa(db, usuari.usuari, usuari.institucio)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuari no trobat.")
    audit.registra_accio(db, usuari=usuari.usuari, rol=usuari.rol.value, accio="mfa_setup")
    return MfaSetupResponse(secret=secret, otpauth_uri=totp.uri_otpauth(secret, usuari.usuari))


@router.post("/mfa/activar", response_model=MfaEstat)
def mfa_activar(
    cos: MfaCodi,
    usuari: Usuari = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MfaEstat:
    """Activa l'MFA si el codi verifica contra el secret generat al setup."""
    if not users.activa_mfa(db, usuari.usuari, cos.codi, usuari.institucio):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Codi incorrecte o enrolment no iniciat. Torna a generar el codi QR.",
        )
    audit.registra_accio(db, usuari=usuari.usuari, rol=usuari.rol.value, accio="mfa_activat")
    return MfaEstat(actiu=True)


@router.post("/mfa/desactivar", response_model=MfaEstat)
def mfa_desactivar(
    usuari: Usuari = Depends(get_current_user), db: Session = Depends(get_db),
) -> MfaEstat:
    """Desactiva l'MFA de l'usuari autenticat (ja ha passat el 2n factor en aquesta sessió)."""
    users.desactiva_mfa(db, usuari.usuari, usuari.institucio)
    audit.registra_accio(db, usuari=usuari.usuari, rol=usuari.rol.value, accio="mfa_desactivat")
    return MfaEstat(actiu=False)
