"""Transcripció de veu (STT) local amb faster-whisper, càrrega mandrosa.

Corre en CPU (int8) per defecte per no competir per la VRAM amb l'LLM. El model
es baixa la primera vegada a la cache de HuggingFace (volum persistent).
"""

from __future__ import annotations

from app.core.config import get_settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # import diferit (pesat)

        s = get_settings()
        _model = WhisperModel(
            s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute
        )
    return _model


def transcriu(cami: str) -> str:
    """Transcriu un fitxer d'àudio a text. Detecta la llengua automàticament (ca/es)."""
    model = _get_model()
    segments, _info = model.transcribe(cami, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()
