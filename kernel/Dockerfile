# Secure Agent Kernel — imatge mínima (Python 3.12). NO inclou la pila ML del RAG.
FROM python:3.12-slim

# gnupg per verificar la signatura GPG de l'allowlist (K3.1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gnupg \
    && rm -rf /var/lib/apt/lists/*

# Usuari no-root (defensa en profunditat).
RUN useradd --uid 10002 --create-home kernel

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GNUPGHOME=/home/kernel/.gnupg
RUN mkdir -p /home/kernel/.gnupg && chmod 700 /home/kernel/.gnupg \
    && chown -R kernel:kernel /home/kernel /app
USER kernel

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
