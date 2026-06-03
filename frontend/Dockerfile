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

# ── Etapa 2: serve estàtic ────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

WORKDIR /app

# Instal·la les dependències necessàries per a vite preview
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/vite.config.ts ./vite.config.ts

EXPOSE 5173

CMD ["npm", "run", "preview"]
