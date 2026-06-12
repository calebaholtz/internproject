# internproject

## What This Is
A local web-based chatbot. Users log in and chat with an Ollama LLM grounded in uploaded PDFs via RAG. Admins can upload documents and configure the model and guidance prompt.

## What Is Built
- **Auth**: JWT login, hardcoded users, role-based access (`user` / `admin`)
- **Chat**: Fully wired to Ollama via streaming SSE — tokens appear as they're generated, typing indicator shows until first token arrives
- **Conversation history**: Per-user message history stored in memory on the backend — full conversation sent to Ollama on each request so the model remembers previous messages. Restarting the backend clears all history.
- **New conversation button**: Appears in chat header once a conversation starts — clears frontend messages and calls `POST /chat/clear` to reset server-side history
- **RAG pipeline**: Built directly with `pypdf`, `chromadb`, and `nomic-embed-text` (no LlamaIndex). PDFs are chunked, embedded, and stored in ChromaDB. On each chat message the query is embedded and the top 5 most relevant chunks are retrieved and injected into the system prompt.
- **PDF ingestion** (`ingest.py`): Reads PDFs with pypdf, splits into 512-word chunks with 50-word overlap, embeds with `nomic-embed-text` via Ollama, stores in ChromaDB
- **RAG retrieval** (`rag.py`): Embeds the user query, queries ChromaDB for top K chunks, returns them formatted with source labels
- **Document management**: Upload, list, and delete PDFs via the admin panel — all wired to the backend and ChromaDB
- **Ollama integration**: `ollama` Python package, `stream=True`, model and guidance configurable at runtime
- **Persisted config**: Active model and guidance saved to `app_config.json` on disk — survives backend restarts
- **Admin config**: GET and POST `/admin/config` read/write the active model and guidance prompt
- **Admin models**: `/admin/models` queries Ollama for installed models; embedding models filtered out of dropdown
- **Frontend chat**: Auto-resizing textarea, Enter to send, Shift+Enter for newline, Tab for 3-space indent, custom styled scrollbar, streaming message rendering, markdown rendering with bullet points
- **Frontend admin**: Model dropdown and guidance prompt wired to backend; document list loads from disk on mount; model dropdown auto-saves immediately on change
- **Sidebar document list**: Pulls real document list from backend, refreshes on navigation, shows "No documents uploaded" when empty
- **Stream error display**: Errors from the backend stream are now shown in the chat bubble instead of silently disappearing
- **Dynamic API URL**: Frontend uses `window.location.hostname` to build the API URL — works on both localhost and EC2 without code changes
- **Diagnostics panel**: Floating panel in bottom-right of chat screen showing active model, CPU%, RAM usage, time to first token, and total response time — polls every 2 seconds (temporary dev tool)
- **Performance tuning**: Context window set to 2048 tokens (`num_ctx`)
- **CORS**: Set to allow all origins (`*`) for EC2 compatibility — tighten before any real deployment

## What Is NOT Built Yet
- User database — users are hardcoded in `users.py`
- Conversation history does not persist across backend restarts

## Installed Ollama Models
### Laptop
- `llama3.2:latest` — general purpose, good balance of quality
- `llama3.2:1b` — smaller version, good for simple questions
- `gemma3:1b` — Google's latest small model, strong quality for its size
- `nomic-embed-text` — embedding model only, used by RAG pipeline (not a chat model)

### EC2
- `gemma4:latest` — Google's latest model, high quality, 9.6GB
- `nomic-embed-text` — embedding model, required for RAG pipeline

### Important
- `nomic-embed-text` must be pulled on every machine before RAG works — every chat message runs through it even with no documents uploaded

## Stack
- **Backend**: Python 3.11+, FastAPI, ollama, chromadb, pypdf, psutil, python-jose, passlib, bcrypt
- **Embeddings**: `nomic-embed-text` via Ollama (must be pulled before using RAG)
- **Vector store**: ChromaDB (persistent, stored in `chroma_db/`)
- **Frontend**: React 18, Vite, Tailwind CSS, Radix UI primitives, React Router, Lucide icons
- **Not used**: LlamaIndex — RAG pipeline built directly without it

## Project Layout
```
backend/       FastAPI app — main.py, auth.py, users.py, config.py, ingest.py, rag.py
frontend/      React SPA — login, chat, admin panel
knowledge/     PDF knowledge base — admin uploads land here
chroma_db/     Auto-generated vector store (gitignored)
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
- Active model and guidance are persisted to `backend/app_config.json` — loaded on startup, saved on every config update
- `app_config.json` is gitignored so each environment starts from `config.py` defaults until first save
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
| GET | `/admin/documents` | Admin | Working | Lists PDFs from knowledge folder |
| POST | `/admin/upload` | Admin | Working | Saves PDF, runs ingestion into ChromaDB |
| DELETE | `/admin/documents/{name}` | Admin | Working | Deletes PDF and removes from ChromaDB |
| GET | `/admin/config` | Admin | Working | Returns active model + guidance |
| POST | `/admin/config` | Admin | Working | Updates active model + guidance |
| GET | `/admin/models` | Admin | Working | Lists installed Ollama models |
| POST | `/chat/clear` | Any | Working | Clears conversation history for current user |
| GET | `/debug/stats` | Any | Working | Returns CPU%, RAM, active model (temp diagnostic) |

## Do not edit front end code without asking first
