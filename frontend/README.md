# Frontend — IA Nou Patufet

Dashboard SPA React + Vite + TypeScript + Tailwind CSS que implementa el mockup 03.

## Tecnologia

| Capa | Eina |
|------|------|
| Framework | React 18 + TypeScript 5 |
| Bundler | Vite 5 |
| Estils | Tailwind CSS 3 |
| Icones | lucide-react |
| Utilitats | clsx, date-fns |
| Estat | React Context + useReducer (sense Redux) |
| Streaming | Fetch SSE (ReadableStream) |

## Com executar

### Desenvolupament local

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

> La variable `VITE_API_BASE_URL` es llegeix de `.env.local` (o del `.env` del projecte arrel).
> Per defecte apunta a `http://localhost:8000/api`.

Crea `frontend/.env.local` si vols sobreescriure la URL:
```
VITE_API_BASE_URL=http://localhost:8000/api
```

### Build de producció

```bash
npm run build    # genera dist/
npm run preview  # serveix dist/ al port 5173
```

### Docker (stack complet)

```bash
# Des de l'arrel del projecte:
docker compose --profile dev up --build
# Frontend disponible a http://localhost:5173
```

La imatge Docker fa un build de dues etapes: compila amb Node 20 i serveix
l'artefacte estàtic via `vite preview`.

## Estructura de fitxers

```
frontend/
├── src/
│   ├── api/
│   │   └── client.ts          # Client HTTP/SSE centralitzat
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatArea.tsx   # Zona central de xat
│   │   │   └── MessageBubble.tsx  # Bombolla de missatge + accions
│   │   ├── context/
│   │   │   └── ContextPanel.tsx   # Panell dret: docs, privadesa
│   │   ├── layout/
│   │   │   └── TopBar.tsx     # Barra superior navy
│   │   └── sidebar/
│   │       └── Sidebar.tsx    # Sidebar esquerra
│   ├── hooks/
│   │   ├── useChat.ts         # Hook de xat + SSE
│   │   └── useInitApp.ts      # Càrrega inicial de dades
│   ├── pages/
│   │   ├── DashboardPage.tsx  # Layout del dashboard
│   │   └── LoginPage.tsx      # Login simple per rol
│   ├── store/
│   │   └── appStore.ts        # Context + Reducer global
│   ├── types/
│   │   └── index.ts           # Tipus TypeScript (API_CONTRACT.md)
│   ├── App.tsx
│   ├── index.css
│   └── main.tsx
├── index.html
├── Dockerfile
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── vite.config.ts
```

## Funcionalitats implementades

- **Login** per rol (docent / alumne / família / direcció). Si el backend no respon, entra en mode demo.
- **Streaming SSE** via `fetch` + `ReadableStream`. Els tokens es renderitzen en temps real.
- **4 agents** carregats de `/api/agents`, filtrats pel rol de l'usuari. Selector de dropdown al sidebar.
- **Converses**: llista des de `/api/conversations`, selecció amb càrrega de `/api/conversations/{id}`, eliminació, nova conversa.
- **Panell dret**: fonts citades de l'últim missatge, indicadors de privadesa de `/api/system/status`, accions.
- **Feedback** 👍 Útil / 👎 Millorar via `/api/feedback`.
- **Estat del sistema**: indicadors al sidebar i panell dret, refresc cada 60 s.
- **Estats** loading, error i buit ben resolts. Si el backend no respon, mostra missatge clar.

## Paleta de colors

| Token | Hex | Ús |
|-------|-----|----|
| navy | `#0B2545` | Barra superior, capçaleres |
| terra | `#C97B4E` | Accions primàries, botó nova conversa |
| sage | `#84B59F` | Indicadors OK, accents verds |
| cherry | `#6D2E46` | Agent documental |
| crema | `#F4F1EA` | Fons de targetes |
| fons | `#E5E0D5` | Fons general |

## Assumpicions sobre l'API

1. **SSE format**: cada línia `data: {...}` conté JSON amb `type` o `event` = `"token"` / `"sources"` / `"done"` / `"error"`. El client és tolerant a variacions del format.
2. **Login de demo**: si `/api/auth/login` no respon (backend no aixecat), el frontend genera un token local temporal i permet navegar en mode demo sense dades reals.
3. **Conversa nova**: quan es crea una nova conversa des del frontend (primera missatge), el backend retorna `conversation_id` al event `done`. El frontend no actualitza la llista de converses automàticament en aquesta versió (pendent de webhook o polling).
4. **Agents de demo**: si `/api/agents` no respon, el selector mostra "Selecciona un agent…" i permet escriure igualment (la petició de xat fallarà graciosament).

## Properes millores (backlog)

- Actualització automàtica de la llista de converses en crear-ne una de nova.
- Scroll virtual per a converses llargues (react-window).
- Mode responsive per a tablets.
- Notificacions en temps real (WebSocket).
- Suport a `POST /api/ingest` per pujar documents des del dashboard.

---
*Adeptify · Benet Andújar · bandujar@xtec.cat*
