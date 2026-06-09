# RAG Document Chatbot — Plan

## What It Is
A web-based chatbot that answers questions about uploaded documents. Users log in, ask questions in a chat UI, and get answers grounded in the knowledge base. An admin can swap or upload new PDFs at any time without touching code. Everything runs locally via Ollama — no cloud, no data leaves the machine.

## Starting Point
Prove the pipeline with a single 1-page PDF (e.g., a CVE entry or any plain document) before scaling to a full library. If the chatbot can correctly answer a question about that one PDF, the pipeline is validated.

## Two User Roles
- **User** → logs in → chat UI → asks questions → gets grounded answers from the knowledge base
- **Admin** → logs in → same chat + admin panel → upload/delete PDFs → knowledge base re-indexes automatically

## Three Admin Configurables
1. **Knowledge base** — upload or delete PDFs; triggers automatic re-ingestion
2. **Model** — which Ollama model answers questions (from dropdown of installed models)
3. **Guidance** — system prompt that shapes how the AI answers (tone, focus, constraints)

## Tech Stack
| Layer | Tool |
|---|---|
| Backend | Python + FastAPI |
| Auth | JWT (`python-jose` + `passlib`) |
| LLM | Ollama (local) — `llama3.2` default |
| RAG + Embeddings | LlamaIndex + ChromaDB |
| PDF parsing | pypdf |
| Frontend | React + Vite + Tailwind CSS + shadcn/ui |

## Pre-requisites (manual install before first run)
1. Install Ollama from https://ollama.com
2. Pull models:
   ```
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```

## Data Flow
```
Admin uploads PDF → pypdf parses → LlamaIndex chunks → nomic-embed-text embeds → ChromaDB

User sends message
  → embed query via nomic-embed-text
  → ChromaDB top-k retrieval
  → [guidance] + [context chunks] + [user message] → llama3.2 via Ollama
  → answer streamed back to chat UI
```

## Auth Design (v1 — hardcoded users)
- Two users in `users.py`: `admin / admin123` and `user / user123`
- JWT tokens, 24hr expiry, role claim (`admin` vs `user`)
- Admin routes protected server-side by `Depends(require_admin)`
- Frontend stores token in `localStorage`, sends as `Authorization: Bearer`

## API Routes
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | None | Username + password → JWT |
| GET | `/auth/me` | Any | Current user info + role |
| POST | `/chat/message` | Any | Message → RAG → Ollama → reply |
| GET | `/admin/documents` | Admin | List all PDFs in knowledge base |
| POST | `/admin/upload` | Admin | Upload PDF → triggers re-ingest |
| DELETE | `/admin/documents/{name}` | Admin | Remove PDF → re-index |
| GET | `/admin/config` | Admin | Get current model + guidance |
| POST | `/admin/config` | Admin | Update model and/or guidance |
| GET | `/admin/models` | Admin | List available Ollama models |

## UI Design
- **Login**: Centered card, gradient background, clean form
- **Chat**: Two-column — sidebar (nav, doc list, logout) + main chat with message bubbles and bottom input
- **Admin panel**: Drag-and-drop upload zone + table of documents with delete buttons + model/guidance config

## Project Structure
```
internproject/
├── backend/
│   ├── main.py          # FastAPI app, all routes
│   ├── auth.py          # JWT login, role enforcement
│   ├── users.py         # Hardcoded users for v1
│   ├── rag.py           # LlamaIndex query engine
│   ├── ingest.py        # PDF → chunks → ChromaDB
│   ├── config.py        # Settings: model, paths, secret key
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Chat.tsx
│   │   │   └── Admin.tsx
│   │   ├── components/
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── ProtectedRoute.tsx
│   │   ├── lib/
│   │   │   └── api.ts       # Axios client with JWT header
│   │   └── App.tsx          # React Router setup
│   ├── package.json
│   └── tailwind.config.js
└── knowledge/
    └── sample.pdf           # Starter PDF — swap this out as needed
```

## Build Order
1. Backend scaffold — FastAPI, `config.py`, `auth.py`, `users.py`, `main.py` skeleton
2. Drop a sample PDF into `/knowledge`
3. `ingest.py` — PDF → ChromaDB (prove it populates)
4. `rag.py` — query engine (prove it returns grounded answers)
5. Wire all API endpoints in `main.py`
6. Frontend scaffold — Vite + React + Tailwind + shadcn/ui
7. Login page + auth flow (store JWT, redirect)
8. Chat page — connect to `/chat/message`
9. Admin page — upload, delete, config
10. Polish — loading spinners, error states, empty states
