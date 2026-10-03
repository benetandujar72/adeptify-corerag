# ── Etapa 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Instal·la dependències primer (millor cache).
# npm install (no npm ci) per resoldre els binaris natius de la plataforma del
# contenidor (linux-musl) i tolerar petites diferències del lock generat a Windows.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# Copia la resta de fitxers
COPY . .

# Mateix origen per defecte: nginx reenvia /api al backend intern.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ── Etapa 2: SPA i proxy /api, sense Node ni toolchain de dev; usuari no-root. ──
FROM nginxinc/nginx-unprivileged:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:5173/ >/dev/null 2>&1 || exit 1
