"""Indexa la documentació INTERNA de gestió de l'aplicació al RAG.

Aquests documents són de **visibilitat "admin"**: només els recuperen els rols
direcció / PAS / superadmin (l'assistent d'administració). Així, l'equip de
gestió pot preguntar al sistema «com configuro X» i obtenir resposta, mentre que
docents/famílies/alumnes no hi accedeixen.

Ús (dins el contenidor):  python -m scripts.seed_ajuda_admin

S'indexa una còpia per a CADA institució (doc_id propi) perquè la cerca, que és
per tenant, la trobi a cada centre.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

from app.core import institucions
from app.db.models import Base
from app.db.session import get_engine, get_sessionmaker
from app.ingest import pipeline

CONTINGUT = """# Guia de gestió de l'aplicació (ús intern · administració)

Document intern per a direcció i PAS. Explica com configurar i gestionar la
plataforma d'IA del centre. Visibilitat restringida (no accessible a famílies,
alumnat ni professorat no administratiu).

## Rols i permisos
- **superadmin**: gestiona TOTA la plataforma (totes les institucions): crear/
  editar/esborrar institucions i usuaris, veure l'auditoria forense.
- **direcció**: administra la SEVA institució (configura integracions, pot passar
  llista, gestiona matrícula i assistència, usa l'Assistent d'Administració).
- **PAS** (administració i serveis): gestió documental, matrícula, assistència,
  Assistent d'Administració.
- **docent**: tutoria, secretaria/NOFC, atenció famílies, avaluació, assistència.
- **família**: atenció famílies, matrícula i assistència del seu fill/a.
- **alumne**: tutoria de matemàtiques.

## Usuaris
- El **nom d'usuari és únic per institució** (no globalment): pot haver-hi un
  `direccio` a «nou_patufet» i un altre `direccio` a «cic». En crear un usuari al
  panell Administració, tria sempre la **institució** correcta.
- Crear/editar/desactivar/esborrar usuaris i restablir contrasenyes: panell
  **Administració** (només superadmin).

## Institucions (multi-tenant)
- Cada institució té el seu **RAG aïllat**: documents, usuaris i converses propis.
- Al panell Administració → **Institucions**: crear (slug + nom + colors + logo +
  model), editar branding/config/estat i esborrar (excepte la institució per
  defecte). El **branding** (logo, colors, nom) s'aplica automàticament després
  del login de cada usuari segons la seva institució.

## Documents i RAG
- **Documents**: pujar/esborrar des de la vista Documents (PAS/docent/direcció).
  Els PDF escanejats i imatges passen per OCR automàticament.
- Cada document s'indexa al RAG de la institució de qui el puja.
- La documentació de gestió (com aquesta) té visibilitat **admin**.

## Integració amb Google (per institució)
- **Cada institució configura el SEU propi espai** a Configuració → Integració
  Google Workspace (només direcció/superadmin). Els paràmetres (project id, clau
  del compte de servei, scopes, carpetes/calendaris aprovats) es desen a la
  configuració de la institució; els secrets no es mostren mai.
- **Comptes de correu**: a «Comptes de correu autoritzats» s'indica quines bústies
  pot gestionar l'assistent. **Garantia**: el sistema NOMÉS pot consultar/gestionar
  aquests comptes; qualsevol altra bústia es rebutja.
- **Drive**: només lectura de carpetes aprovades; es poden ingerir documents al RAG.
- **Gmail**: només esborranys (mai s'envia automàticament).
- **Calendar**: lectura i creació en calendaris aprovats.
- Tota crida passa per la passarel·la de privadesa (allow-list + auditoria); la
  inferència segueix sent local (cap crida a IA externa).

## Assistent d'Administració (Gestió IA)
- Agent per a direcció/PAS: ajuda amb tasques, calendari, expedients, generació de
  documentació, comunicació amb famílies i seguiment de pagaments.
- Principi: **l'assistent proposa, la persona valida i executa**. Cap acció amb
  efectes (enviar correu, cobrar) és automàtica.

## Compliment
- Inferència 100% local; comptador de crides a IA externa sempre a 0.
- Dades de menors (matrícula/avaluació/assistència) → requereixen EIPD + CET en
  producció. Auditoria forense de totes les accions (panell Administració).
"""


def main() -> int:
    Base.metadata.create_all(bind=get_engine())
    db = get_sessionmaker()()
    try:
        insts = institucions.llista(db)
        if not insts:
            print("  (cap institució; executa abans el seed principal)")
            return 0
        for inst in insts:
            with tempfile.TemporaryDirectory() as d:
                cami = pathlib.Path(d) / f"ajuda_gestio_{inst.slug}.md"
                cami.write_text(CONTINGUT, encoding="utf-8")
                docs, chunks = pipeline.ingesta_fitxer(
                    db, cami, institucio_id=inst.slug, visibilitat="admin"
                )
                print(f"  ✓ {inst.slug}: {chunks} chunks (visibilitat=admin)")
        print("Llest. L'Assistent d'Administració ja pot respondre sobre la gestió de l'app.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
