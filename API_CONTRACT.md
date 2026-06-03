# Contracte d'API — backend ⇄ frontend

Contracte **estable** que el `backend/` implementa i el `frontend/` consumeix. Qualsevol canvi
s'ha de reflectir aquí primer. Base URL del backend: `/api`. Format: JSON (UTF-8).
Autenticació: capçalera `Authorization: Bearer <token>` (al MVP, sessió simple per rol).

## Models de dades

```jsonc
// Agent
{
  "id": "tutor_mates",                 // tutor_mates | secretaria | families | documental
  "nom": "Tutor Matemàtiques",
  "descripcio": "Resol dubtes de matemàtiques amb context del nivell de l'alumne.",
  "color": "#0B2545",                  // per a la UI (mockup 02/03)
  "rols_permesos": ["docent", "alumne"]
}

// Font citada (per a la columna dreta del dashboard, mockup 03)
{
  "doc_id": "pec_2024",
  "filename": "PEC_2024.pdf",
  "tipus": "pdf",                      // pdf | docx | xlsx | md | html
  "pagina": 34,                        // opcional
  "fragments": 4,                      // nombre de chunks rellevants d'aquest document
  "score": 0.87,                       // confiança/similitud 0..1
  "verificat_el": "2024-09-01",        // metadada de versió del document
  "snippet": "…text del fragment…"     // opcional, per a previsualització
}

// Missatge
{
  "id": "msg_123",
  "rol": "user",                       // user | assistant
  "contingut": "…",
  "agent_id": "tutor_mates",           // a les respostes de l'assistant
  "fonts": [Font, …],                  // a les respostes de l'assistant
  "confianca": 0.87,                   // a les respostes de l'assistant
  "creat_el": "2026-05-22T09:42:00Z"
}

// Conversa (sidebar esquerra)
{
  "id": "conv_1",
  "titol": "Esquema d'unitat de fraccions",
  "agent_id": "tutor_mates",
  "etiqueta": "Mates · 5è",
  "actualitzat_el": "2026-05-22T09:42:00Z",
  "n_missatges": 4
}
```

## Endpoints

### Agents i sistema
- `GET /api/agents` → `{ "agents": [Agent, …] }`
- `GET /api/system/status` → indicadors per a la UI (mockup 03):
  ```jsonc
  {
    "servidor": { "actiu": true, "host": "192.168.1.10 (o IP VM GCP)", "entorn": "pilot-gcp" },
    "indexacio": { "al_dia": true, "documents": 128, "ultima": "2026-05-22T08:00:00Z" },
    "privadesa": {
      "processament_local": true,
      "crides_externes": 0,
      "xifratge": "AES-256",
      "auditat_el": "2026-05-18"
    },
    "model": { "nom": "Llama-3.3-70B-Instruct-AWQ", "backend": "vllm", "catala": "Salamandra-7B" },
    "versio": "v0.1.0-mvp"
  }
  ```

### Xat (cor del sistema)
- `POST /api/chat`
  ```jsonc
  // request
  { "agent_id": "tutor_mates", "conversation_id": "conv_1|null", "message": "…", "stream": true }
  // response (si stream=false)
  {
    "conversation_id": "conv_1",
    "message": Message,        // rol=assistant, amb fonts[] i confianca
    "agent_utilitzat": "tutor_mates"   // l'orquestrador pot reencaminar
  }
  ```
  Si `stream=true`: **Server-Sent Events** (`text/event-stream`). Esdeveniments:
  `token` (delta de text), `sources` (array de Font quan el retrieval acaba),
  `done` (objecte Message final), `error`.

### Converses
- `GET /api/conversations` → `{ "conversations": [Conversa, …] }` (ordenades per `actualitzat_el`)
- `GET /api/conversations/{id}` → `{ "conversation": Conversa, "messages": [Message, …] }`
- `DELETE /api/conversations/{id}` → `204`

### Documents i ingesta
- `GET /api/documents` → `{ "documents": [Font sense pàgina/score, amb estat d'indexació] }`
- `POST /api/ingest` (multipart o `{ "path": "sample_data/" }`) → encua ingesta →
  `{ "job_id": "…", "estat": "encuat" }`
- `GET /api/ingest/{job_id}` → `{ "estat": "processant|fet|error", "documents": N, "chunks": N }`

### Feedback i accions (mockup 03: 👍 Útil / 👎 Millorar)
- `POST /api/feedback` → `{ "message_id": "…", "valor": "util|millorar", "comentari": "…?" }` → `204`

### Auth (MVP simplificat; SSO Clickedu en el futur)
- `POST /api/auth/login` → `{ "usuari": "marta", "rol": "docent" }` → `{ "token": "…", "rol": "docent" }`
- `GET /api/auth/me` → `{ "usuari": "…", "rol": "…" }`

## Rols (RBAC)
`docent` · `alumne` · `familia` · `direccio`. Cada agent declara `rols_permesos`. El backend filtra
documents i agents segons el rol del token. Tota petició a `/api/chat` queda al **registre d'auditoria**.

## Errors
Format uniforme: `{ "error": { "codi": "FORBIDDEN|NOT_FOUND|RATE_LIMIT|INTERNAL", "missatge": "…" } }`
amb el codi HTTP corresponent (403/404/429/500).
