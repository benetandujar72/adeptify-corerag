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

# Build (la variable s'injecta en build-time si es passa com ARG)
ARG VITE_API_BASE_URL=http://localhost:8000/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ── Etapa 2: serve estàtic (sense toolchain de dev) ─────────────────────────────
# Servim el build estàtic amb `serve` (un sol paquet), NO amb `vite preview`, de
# manera que la imatge de runtime no arrossega les devDependencies. Usuari no-root.
FROM node:20-alpine AS runtime

WORKDIR /app

RUN npm install -g serve@14.2.3

# Només el build; cap codi font ni node_modules de dev.
COPY --from=builder /app/dist ./dist

# node:alpine ja inclou l'usuari no-root `node` (uid 1000).
USER node

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:5173/ >/dev/null 2>&1 || exit 1

# -s = SPA (fallback a index.html); -l = port.
CMD ["serve", "-s", "dist", "-l", "5173"]
