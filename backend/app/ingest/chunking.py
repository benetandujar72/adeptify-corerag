"""Chunking semàntic amb solapament.

Estratègia: respectar els límits de paràgraf i frase tant com sigui possible.
Els paràgrafs s'acumulen fins a la mida objectiu (`chunk_size` caràcters); quan
es talla, es manté un solapament (`chunk_overlap`) amb el chunk anterior per no
perdre context a les fronteres. Cada chunk conserva la pàgina d'origen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.ingest.loaders import Pagina

_SEP_PARAGRAF = re.compile(r"\n\s*\n+")
_SEP_FRASE = re.compile(r"(?<=[\.\!\?·:])\s+")


@dataclass
class Chunk:
    """Fragment final, llest per a embedding."""

    contingut: str
    pagina: int | None
    ordre: int


def _divideix_unitats(text: str, mida_max: int) -> list[str]:
    """Trenca el text en unitats (paràgrafs; frases si un paràgraf és massa llarg)."""
    unitats: list[str] = []
    for paragraf in _SEP_PARAGRAF.split(text):
        paragraf = paragraf.strip()
        if not paragraf:
            continue
        if len(paragraf) <= mida_max:
            unitats.append(paragraf)
        else:
            frases = _SEP_FRASE.split(paragraf)
            buffer = ""
            for frase in frases:
                if len(buffer) + len(frase) + 1 > mida_max and buffer:
                    unitats.append(buffer.strip())
                    buffer = frase
                else:
                    buffer = f"{buffer} {frase}".strip()
            if buffer.strip():
                unitats.append(buffer.strip())
    return unitats


def chunk_pagines(
    pagines: list[Pagina],
    mida: int | None = None,
    solapament: int | None = None,
) -> list[Chunk]:
    """Converteix pàgines en chunks amb solapament, conservant la pàgina."""
    settings = get_settings()
    mida = mida or settings.chunk_size
    solapament = solapament if solapament is not None else settings.chunk_overlap

    chunks: list[Chunk] = []
    ordre = 0
    for pagina in pagines:
        unitats = _divideix_unitats(pagina.text, mida)
        buffer = ""
        for unitat in unitats:
            if len(buffer) + len(unitat) + 1 > mida and buffer:
                chunks.append(Chunk(contingut=buffer.strip(), pagina=pagina.pagina, ordre=ordre))
                ordre += 1
                # Solapament: arrossega la cua del buffer al següent chunk.
                cua = buffer[-solapament:] if solapament > 0 else ""
                buffer = f"{cua} {unitat}".strip()
            else:
                buffer = f"{buffer} {unitat}".strip()
        if buffer.strip():
            chunks.append(Chunk(contingut=buffer.strip(), pagina=pagina.pagina, ordre=ordre))
            ordre += 1
    return chunks
