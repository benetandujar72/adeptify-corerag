"""Onboarding d'un centre nou (alta guiada).

Dona d'alta una institució (tenant) nova en una instància d'Adeptify:
crea la institució amb el seu branding i la seva llicència (pla), crea l'usuari
administrador (direcció) del centre amb una contrasenya, i sembra la referència
LOMLOE per a aquell centre. Idempotent: si el centre ja existeix, només avisa.

Ús (dins el contenidor o amb el venv actiu):

    python -m scripts.onboard_centre \\
        --slug escola-exemple \\
        --nom "Escola Exemple SCCL" \\
        --pla avancat \\
        --admin-usuari direccio_exemple \\
        --admin-contrasenya "una-contrasenya-forta" \\
        [--color-primari "#0B2545"] [--color-secundari "#C0633A"] \\
        [--lema "IA que protegeix"] [--caducitat 2027-08-31]

Si no es passa `--admin-contrasenya`, se'n genera una d'aleatòria i s'imprimeix.
El pla determina les features actives i els límits (vegeu app/core/llicencia.py).
"""

from __future__ import annotations

import argparse
import secrets
import sys

from app.core import institucions, llicencia, users
from app.core.roles import Rol
from app.db.models import Base
from app.db.session import get_engine, get_sessionmaker


def _branding(args) -> dict:
    b: dict = {}
    if args.color_primari:
        b["color_primari"] = args.color_primari
    if args.color_secundari:
        b["color_secundari"] = args.color_secundari
    if args.logo_url:
        b["logo_url"] = args.logo_url
    if args.lema:
        b["lema"] = args.lema
    return b


def main() -> int:
    ap = argparse.ArgumentParser(description="Alta d'un centre nou a Adeptify.")
    ap.add_argument("--slug", required=True, help="Identificador únic del centre (a-z, guions).")
    ap.add_argument("--nom", required=True, help="Nom complet del centre.")
    ap.add_argument("--pla", default="avancat", choices=sorted(llicencia.PLANS),
                    help="Pla de llicència (per defecte: avancat).")
    ap.add_argument("--admin-usuari", required=True, help="Nom d'usuari de la direcció del centre.")
    ap.add_argument("--admin-contrasenya", default=None, help="Contrasenya de la direcció (si falta, se'n genera una).")
    ap.add_argument("--admin-nom", default=None, help="Nom complet de la direcció.")
    ap.add_argument("--color-primari", default=None)
    ap.add_argument("--color-secundari", default=None)
    ap.add_argument("--logo-url", default=None)
    ap.add_argument("--lema", default=None)
    ap.add_argument("--caducitat", default=None, help="Data de caducitat de la llicència (YYYY-MM-DD).")
    ap.add_argument("--sense-seed", action="store_true", help="No sembris la referència LOMLOE.")
    args = ap.parse_args()

    Base.metadata.create_all(bind=get_engine())
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        # 1) Institució (idempotent).
        existent = institucions.obte(db, args.slug)
        if existent is not None:
            print(f"⚠ El centre «{args.slug}» ja existeix. No es torna a crear.")
            return 1

        config = llicencia.fusiona(
            None, pla=args.pla, data_caducitat=args.caducitat, estat="activa",
        )
        institucions.crea(
            db, args.slug, args.nom, config=config, branding=_branding(args),
        )
        lic = llicencia.llegeix(config)
        print(f"✓ Centre «{args.nom}» ({args.slug}) creat · pla {lic['pla_nom']} · "
              f"{len(lic['features'])} mòduls actius.")

        # 2) Usuari administrador (direcció).
        contrasenya = args.admin_contrasenya or secrets.token_urlsafe(12)
        try:
            users.crea_usuari(
                db, args.admin_usuari, contrasenya, Rol.DIRECCIO.value,
                nom=args.admin_nom or "Direcció", institucio_id=args.slug,
            )
        except ValueError as exc:
            print(f"✗ No s'ha pogut crear l'administrador: {exc}")
            return 1
        print(f"✓ Administrador del centre: {args.admin_usuari} (rol direcció).")
        if not args.admin_contrasenya:
            print(f"  Contrasenya generada: {contrasenya}  (guarda-la i canvia-la al primer accés)")

        # 3) Seed de la referència LOMLOE per a aquest centre (opcional).
        if not args.sense_seed:
            try:
                from scripts.seed_avaluacio_lomloe import _seed_institucio
                n_comp, n_crit = _seed_institucio(db, args.slug)
                print(f"✓ Referència LOMLOE sembrada ({n_comp} competències + {n_crit} criteris).")
            except Exception as exc:  # noqa: BLE001
                print(f"⚠ No s'ha pogut sembrar LOMLOE automàticament ({exc}). "
                      f"Executa: python -m scripts.seed_avaluacio_lomloe {args.slug}")

        print()
        print(f"Centre «{args.nom}» llest. Accedeix-hi seleccionant-lo a la pantalla de login.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
