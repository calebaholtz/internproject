# internproject

## What This Is
A local web-based chatbot. Users log in and chat with an Ollama LLM; admins can configure the model and guidance prompt. The next major milestone is a RAG pipeline grounded in uploaded PDFs.

## What Is Built
- **Auth**: JWT login, hardcoded users, role-based access (`user` / `admin`)
- **Chat**: Fully wired to Ollama via streaming SSE — tokens appear as they're generated, typing indicator shows until first token arrives
- **Ollama integration**: `ollama` Python package, `stream=True`, model and guidance configurable at runtime via in-memory config
- **Admin config**: GET and POST `/admin/config` read/write the active model and guidance prompt — changes take effect immediately on the next chat message
- **Admin models**: `/admin/models` queries Ollama for installed models; frontend dropdown shows real models with use-case descriptions, `:latest` stripped from display labels
- **Frontend chat**: Auto-resizing textarea, Enter to send, Shift+Enter for newline, Tab for 3-space indent, custom styled scrollbar, streaming message rendering
- **Frontend admin**: Model dropdown and guidance prompt wired to backend; loads current config on mount, saves on button click
- **Diagnostics panel**: Floating panel in bottom-right of chat screen showing active model, CPU%, RAM usage, time to first token, and total response time — polls `/debug/stats` every 2 seconds (temporary dev tool, not for production)
- **Performance tuning**: Context window reduced to 1024 tokens (`num_ctx`) to lower RAM usage and reduce thinking delay

## What Is NOT Built Yet
- `rag.py` — does not exist; no RAG pipeline
- `ingest.py` — does not exist; no PDF ingestion or ChromaDB indexing
- `/admin/documents` — returns empty list; not reading from disk
- `/admin/upload` — not implemented; drag-and-drop in UI is local state only
- `DELETE /admin/documents/{name}` — not implemented; delete button is local state only

## Installed Ollama Models
- `llama3.2:latest` — general purpose, good balance of quality
- `llama3.2:1b` — smaller version, good for simple questions
- `phi3.5:latest` — Microsoft model, good for reasoning and structured answers

## Stack
- **Backend**: Python 3.11+, FastAPI, ollama, psutil, python-jose, passlib, bcrypt
- **Frontend**: React 18, Vite, Tailwind CSS, Radix UI primitives, React Router, Lucide icons
- **Not yet installed**: LlamaIndex, ChromaDB, pypdf

## Project Layout
```
backend/       FastAPI app — main.py, auth.py, users.py, config.py
frontend/      React SPA — login, chat, admin panel
knowledge/     Intended drop folder for PDFs (not yet used)
```

## Running Locally
```bash
# Ollama must be running first
ollama serve

# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173

Default credentials:
- `user / user123` — chat only
- `admin / admin123` — chat + admin panel
- `caleb / password` — admin

## Key Conventions
- Users are hardcoded in `backend/users.py`; add a database before any real deployment
- `/admin/*` routes enforce `require_admin` dependency server-side
- Active model and guidance are stored in `app_config` dict in `main.py` — restarting the backend resets them to defaults from `config.py`
- Chat uses SSE streaming — frontend reads `data: {"content": "..."}` chunks and appends to the message, terminated by `data: [DONE]`

## config.py Reference
```python
KNOWLEDGE_FOLDER = "./knowledge"
DEFAULT_MODEL = "llama3.2"
EMBEDDING_MODEL = "nomic-embed-text"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
TOP_K = 5
SECRET_KEY = "change-me-before-deploying"
ACCESS_TOKEN_EXPIRE_HOURS = 24
```

## API Routes
| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| POST | `/auth/login` | None | Working | Returns JWT token |
| GET | `/auth/me` | Any | Working | Current user + role |
| POST | `/chat/message` | Any | Working | Streams Ollama response via SSE |
| GET | `/admin/documents` | Admin | Stub | Returns empty list |
| POST | `/admin/upload` | Admin | Not implemented | — |
| DELETE | `/admin/documents/{name}` | Admin | Not implemented | — |
| GET | `/admin/config` | Admin | Working | Returns active model + guidance |
| POST | `/admin/config` | Admin | Working | Updates active model + guidance |
| GET | `/admin/models` | Admin | Working | Lists installed Ollama models |
| GET | `/debug/stats` | Any | Working | Returns CPU%, RAM, active model (temp diagnostic) |

## Do not edit front end code without asking first
