"""Resolució del device (cpu/cuda) amb fallback segur.

Si es demana CUDA però no hi ha GPU disponible (p. ex. torch CPU, o sense
passthrough), es retorna 'cpu' perquè el sistema funcioni igualment.
"""

from __future__ import annotations


def resol_device(configurat: str | None) -> str:
    dev = (configurat or "cpu").strip().lower()
    if dev.startswith("cuda"):
        try:
            import torch

            if torch.cuda.is_available():
                return dev
        except Exception:
            pass
        return "cpu"
    return dev or "cpu"
