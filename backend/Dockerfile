# ───────── IA Nou Patufet · backend · Dockerfile ─────────
# Python 3.11-slim. Exposa 8000 i arrenca uvicorn.
FROM python:3.11-slim

# Evita .pyc i activa logs sense buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Dependències de sistema mínimes (compilació d'algunes wheels i suport PDF).
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instal·la dependències primer (millor cache de capes).
COPY requirements.txt constraints-security.txt requirements-runtime.txt requirements-linux-cpu.lock ./
# El backend del compose actual no rep GPU. Ollama manté la seva reserva separada.
# CPU abans del core: evita instal·lar CUDA transitiva i evita el torch vulnerable de cu128.
RUN pip install --upgrade pip \
    && pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-linux-cpu.lock

# OCR (Fase 5): Tesseract (català+castellà) + Poppler per a PDFs escanejats.
# En capes separades DESPRÉS de torch perquè el torch (gran) es mantingui en cache.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr tesseract-ocr-cat tesseract-ocr-spa poppler-utils \
    && rm -rf /var/lib/apt/lists/*
# OCR/veu també estan fixats al lock instal·lat anteriorment.

# Veu (Fase 5): Whisper STT local via faster-whisper (CPU, int8). Independent de
# torch (usa ctranslate2). El model es baixa a la cache de HF (volum persistent).
# faster-whisper és a requirements-runtime.txt, amb versió fixada.

RUN pip check \
    && python -m pip uninstall -y pip \
    && apt-get purge -y build-essential gcc g++ dpkg-dev linux-libc-dev libc6-dev libstdc++-14-dev

# Codi de l'aplicació.
COPY app ./app
COPY scripts ./scripts
COPY db ./db
COPY README.md .

# Usuari NO-root + directoris escrivibles. La cache de models HuggingFace va al
# HOME de l'usuari (HF_HOME) i el log d'auditoria a /app/data; ambdós es munten
# com a volums al compose (sobre aquestes mateixes rutes, propietat de `app`).
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data /home/app/.cache/huggingface \
    && chown -R app:app /app /home/app
ENV HF_HOME=/home/app/.cache/huggingface
USER app

EXPOSE 8000

# Comprovació de salut bàsica.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# El guardià valida XFF contra el peer REAL del socket; uvicorn no l'ha de reescriure.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
