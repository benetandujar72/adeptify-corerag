"""Context CAG (Context-Augmented Generation) per al Copilot didàctic.

El CAG no substitueix el RAG: prepara una fitxa curta i estable sobre quins
canals de coneixement pot usar el Copilot (currículum, materials docents,
documents de centre i zona sensible local).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document


def context_cag(db: Session, institucio_id: str, *, limit: int = 8) -> list[str]:
    rows = db.execute(
        select(Document.canal_rag, Document.origen, func.count(Document.id))
        .where(Document.institucio_id == institucio_id)
        .group_by(Document.canal_rag, Document.origen)
        .order_by(Document.canal_rag, Document.origen)
    ).all()
    linies: list[str] = []
    if rows:
        resum = ", ".join(f"{canal}/{origen}: {n}" for canal, origen, n in rows)
        linies.append(f"Canals RAG disponibles: {resum}.")
    else:
        linies.append("Encara no hi ha materials docents indexats al RAG del centre.")

    curriculum = db.scalars(
        select(Document)
        .where(
            Document.institucio_id == institucio_id,
            Document.canal_rag == "rag_curriculum",
        )
        .order_by(Document.creat_el.desc())
        .limit(limit)
    ).all()
    if curriculum:
        titols = "; ".join(f"{d.filename} ({d.origen})" for d in curriculum)
        linies.append(
            "Curriculum/programacio i avaluacio competencial indexats: "
            f"{titols}."
        )

    materials = db.scalars(
        select(Document)
        .where(
            Document.institucio_id == institucio_id,
            Document.canal_rag == "rag_materials_docents",
        )
        .order_by(Document.creat_el.desc())
        .limit(limit)
    ).all()
    if materials:
        titols = "; ".join(
            f"{d.filename} ({d.origen}, {d.sensibilitat}, exportable_ia={bool(d.exportable_ia)})"
            for d in materials
        )
        linies.append(f"Materials docents recents reutilitzables: {titols}.")

    linies.append(
        "Regla CAG: usa el canal rag_curriculum com a referencia curricular i "
        "competencial, i Moodle/Classroom/Drive només com a materials docents; "
        "no facis servir entregues, notes, feedback individual ni dades d'alumnat "
        "per crear contingut o prendre decisions."
    )
    return linies
