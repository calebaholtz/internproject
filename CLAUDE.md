# internproject

## What This Is
A local web-based chatbot. Users log in and chat with an Ollama LLM grounded in uploaded PDFs via RAG. Admins can upload documents and configure the model and guidance prompt.

## What Is Built
- **Auth**: JWT login, hardcoded users, role-based access (`user` / `admin`)
- **Chat**: Fully wired to Ollama and Anthropic Claude API via streaming SSE — tokens appear as they're generated, typing indicator shows until first token arrives
- **Dual LLM provider**: Backend detects the model name — if it starts with `claude-` it routes to the Anthropic API, otherwise uses Ollama. No config changes needed, just select the model in the admin panel.
- **Anthropic integration**: Uses the `anthropic` Python SDK with streaming. API key loaded from `backend/.env` (gitignored). Claude models only appear in the dropdown if the key is set.
- **Message cost tracking**: After each message, the diagnostics panel shows the cost. Claude API calls calculate cost from token usage × per-model pricing. Ollama shows "Free".
- **Conversation history**: Per-user message history stored in memory on the backend — full conversation sent to the LLM on each request so the model remembers previous messages. Restarting the backend clears all history.
- **New conversation button**: Appears in chat header once a conversation starts — clears frontend messages and calls `POST /chat/clear` to reset server-side history
- **RAG pipeline**: Built with `pypdf`, `qdrant-client`, and `nomic-embed-text`. PDFs are chunked per-page with page number metadata, embedded, and stored in Qdrant. Each query runs hybrid search (semantic + keyword) and injects the top K results into the system prompt.
- **Hybrid Search**: Every query runs two searches simultaneously — semantic vector search (finds conceptually related content) and keyword full-text search (finds exact section/appendix names). Results appearing in both are ranked first. Built on Qdrant's native full-text payload index — no extra models or API costs.
- **Contextual Retrieval**: After initial ingestion, a background thread runs each chunk through `gemma4` (local Ollama) to generate a 1-2 sentence description of what that chunk is about. That description is prepended to the chunk before re-embedding — eliminating ambiguity when two sections use similar language. Admin panel shows enrichment progress ("Enriching 23/80" → "Ready ✓"). Claude is never used for enrichment — always local.
- **Parallel ingestion and enrichment**: Both the initial embedding step and the enrichment step run 4 chunks simultaneously using `ThreadPoolExecutor`. On EC2 with `OLLAMA_NUM_PARALLEL=4`, the T4 GPU processes all 4 concurrently for maximum throughput.
- **PDF ingestion** (`ingest.py`): Reads PDFs page-by-page with pypdf, splits each page into 256-word chunks with 40-word overlap, embeds with `nomic-embed-text` in parallel, stores in Qdrant with `{"source", "page", "text", "enriched"}` payload. `enrich_file()` runs background contextual enrichment in parallel. UUIDs used as point IDs.
- **RAG retrieval** (`rag.py`): Runs semantic + keyword search in parallel, merges with priority ordering (both > keyword-only > semantic-only), returns top K chunks formatted with source and page labels. The merge strategy is a lightweight fusion-based reranking (similar to Reciprocal Rank Fusion) — no separate reranking model needed.
- **Implicit metadata filtering**: Per-page chunking stores `source` and `page` on every chunk. The keyword search acts as an implicit section/appendix filter — asking about "Appendix A" or "Section 2.2" finds those chunks by exact string match, effectively filtering to that section without a separate filter step.
- **Query expansion analogy**: Contextual Retrieval enriches chunks from the document side rather than expanding the query — closes the same gap between how users ask questions and how documents are written, from the opposite direction.
- **Document management**: Upload, list, and delete PDFs via the admin panel — all wired to the backend and Qdrant. `DELETE /admin/documents/{name}` no longer requires a disk file to exist — it originally 404'd on any text-only source (MCP/Teams-ingested, no on-disk file by design), which the frontend silently swallowed as a no-op delete. Now it only 404s if the name is absent from both disk and `ingest.get_document_info()`.
- **MCP server** (`mcp_server.py`): A Model Context Protocol server mounted at `POST /mcp` (Streamable HTTP transport) alongside the REST API, in the same process. Lets external MCP clients (Claude Desktop, Claude Code, other agents) manage the knowledge base without going through the admin panel. Guarded by a shared-secret `MCP_API_KEY` — every request must send `Authorization: Bearer <MCP_API_KEY>` or gets a 401, enforced via Starlette middleware on the mounted sub-app (separate from the JWT scheme used by the REST routes). Six tools: `upload_text` (raw text, chunked/embedded/stored like a PDF but with `page: null`), `upload_pdf` (base64-encoded PDF bytes, reuses `ingest.ingest_file()` unchanged), `list_documents`, `delete_document` (also removes the on-disk file if present), `enrichment_status`, `query_knowledge` (wraps `rag.retrieve()`). Both upload tools trigger the same background enrichment thread pattern as `/admin/upload`. `upload_text` rejects `source_name` values ending in `.pdf` to avoid desyncing Qdrant chunks from the (nonexistent) disk file.
- **`ingest_text()`** (`ingest.py`): Chunks and embeds raw text directly (no PDF/disk file required) — reuses `_chunk_text`, `_make_id`, and the same parallel-embedding pattern as `ingest_file()`. Chunks get `payload["page"] = None`; `rag.py`'s formatter renders this as `Page N/A` instead of the literal string `"None"`.
- **Teams ingestion webhook** (`POST /webhook/teams-ingest` in `main.py`): A plain REST/JSON endpoint (not MCP) built for a Power Automate flow triggered on new Teams channel messages — Power Automate doesn't speak MCP's JSON-RPC protocol, so this is a simpler HTTP entry point into the same pipeline. Reuses `MCP_API_KEY` as its bearer secret and `ingest.ingest_text()` + the same background-enrichment thread pattern as the MCP `upload_text` tool. Body is `{"text": string, "source_name"?: string}`; if `source_name` is omitted it's auto-generated as `teams-YYYYMMDD-HHMMSS`, and `.pdf`-suffixed names are rejected for the same reason as `upload_text`.
- **Azure Security Risk Assessment flow** (`main.py`): A second chat mode that coexists with normal RAG chat in the same window — triggered when a user's message matches a phrase like "start the assessment" or "azure security questionnaire" (`ASSESSMENT_TRIGGERS`). Walks the user through 10 fixed Azure security questions one at a time with branching logic (Q2 No skips Q3–Q6, Q7 No skips Q8, Q9 No skips Q10), then produces a summary table and hands off to "our team of experts." **Server-side state, not model memory**: `assessment_states[username]` tracks `{current_q, answers}` explicitly in `main.py` — the model is only ever asked to *phrase* the next question or the final summary from data injected fresh into that single call's prompt, never to recall earlier answers from conversation history. This was a deliberate fix: an earlier guidance-prompt-only version relied on the model remembering prior answers, but `MAX_HISTORY=6` truncates a ~20-message assessment long before it ends, and the model was confirmed (via direct testing) to confabulate a plausible-looking but factually wrong summary once real answers scrolled out of context — unacceptable for a flow whose whole purpose is producing an accurate report. `_parse_yes_no()` normalizes free-text yes/no answers; ambiguous answers get a re-prompt instead of silently advancing state. Saying a cancel phrase (`ASSESSMENT_CANCEL_TRIGGERS`) mid-flow clears state and returns to normal chat. `POST /chat/clear` also clears `assessment_states` for that user. `_stream_llm()` and `_sse_response()`/`_sse_static()` are shared SSE-streaming helpers factored out of the original single chat-message code path, now used by both the normal RAG flow and every assessment branch.
- **Assessment PDF export** (`GET /chat/assessment/pdf` in `main.py`): Once an assessment completes, its real answers are saved into `completed_assessments[username]` (separate from `assessment_states`, which gets cleared immediately) so this route can render an accurate PDF on demand via `fpdf2` (`_build_assessment_pdf()`) — built directly from the same server-side data used for the chat summary, not from the model. Auth is the normal JWT (any logged-in user), not the MCP key. Returns 404 if the user has no completed assessment. `POST /chat/clear` also clears `completed_assessments`.
- **PDF branding** (`_AssessmentPDF(FPDF)` in `main.py`): Deliberately corporate/minimal, not a colored banner — white background throughout, a small letterhead-style logo top-left (`backend/assets/ats-logo.jpg`, no white box needed since the page is already white), bold black title + gray "Summary Report" subtitle right-aligned, and a single thin accent-colored rule under the header as the *only* spot of color on the page. `accent_color` is set from `THEME_COLORS[app_config["theme"]]` right before `add_page()`, so that one accent line always matches whatever theme is active in the admin panel. The Q&A table uses fpdf2's `pdf.table()` API with `borders_layout="HORIZONTAL_LINES"` and a light-gray (not colored) heading row — an earlier version used solid color fills for the header banner and table heading row, which read as too loud/branded rather than a professional report; this version keeps color to that single accent line and otherwise stays grayscale.
- **Assessment SSE signaling** (`main.py`/`Chat.tsx`): Every `/chat/message` SSE stream ends with `data: {"in_assessment": bool, "assessment_completed": bool}` before `[DONE]`, so the frontend knows without guessing whether the user is mid-assessment. `Chat.tsx` uses `in_assessment` to swap the input placeholder to "Answer the question above..." during the flow. On `assessment_completed`, the specific assistant `Message` gets a `showPdfCard: true` flag (matched by `assistantId`, not a global boolean) so the PDF card renders inline right under that summary bubble, not in a header that could scroll out of view. Placeholder resets on "New conversation" (state cleared, messages array wiped).
- **Inline PDF card + preview modal** (`Chat.tsx`): The card (file icon, filename, "Preview" and "Download" buttons) appears directly under the completed assessment's summary message. Both buttons call `fetchAssessmentPdfBlob()` (fetches `/chat/assessment/pdf` as a blob — needs the JWT header, so a plain `<a href>` won't work). "Preview" opens a modal rendering the PDF via `<iframe src={blobUrl}>` using the browser's native PDF viewer, with its own Download button inside; "Download" triggers an immediate save via a temporary `<a download>` click — no auto-download without the user explicitly clicking one of these. The object URL is revoked on modal close and on "New conversation." Note: headless-Chromium's stripped-down "headless shell" build (used by some test harnesses) doesn't include the PDF viewer plugin and renders the iframe blank — the full Chromium/Chrome/Edge/Firefox binaries a real user runs all support it natively.
- **Why FastAPI is pinned to `0.139.0` (not `0.115.0`)**: the `mcp` SDK requires `starlette>=0.48.0` on Python 3.14, which is incompatible with `fastapi==0.115.0`'s `starlette<0.39.0` ceiling — there is no starlette version that satisfies both. Do not downgrade FastAPI without also removing/replacing the MCP server, or main.py will fail to start (`TypeError: Router.__init__() got an unexpected keyword argument 'on_event'`-style breakage). The startup hook was also rewritten from `@app.on_event("startup")` to a `lifespan` context manager, which both preloads the Ollama model **and** starts the MCP session manager (`mcp_server.mcp_instance.session_manager.run()`) — the MCP session manager will not initialize if only mounted via `app.mount()` without also being entered in the app's own lifespan (Starlette does not propagate lifespan into mounted sub-apps).
- **Persisted config**: Active model and guidance saved to `app_config.json` on disk — survives backend restarts
- **Admin config**: GET and POST `/admin/config` read/write the active model and guidance prompt
- **Admin models**: Merges installed Ollama models + Claude models (if API key set); embedding models filtered out
- **Frontend chat**: Auto-resizing textarea, Enter to send, Shift+Enter for newline, Tab for 3-space indent, custom styled scrollbar, streaming message rendering, markdown rendering with bullet points
- **Suggestion bubbles** (`Chat.tsx`): Two clickable buttons on the empty-chat state — "Start the Azure Security Risk Assessment" and "Explain insider threat risks" — defined in `SUGGESTIONS`. Clicking one calls the same `sendMessage()` used by the text input, pre-loaded with the trigger phrase, so it's functionally identical to typing it (not a cosmetic shortcut). `handleSend` (form submit) and the bubbles both call the shared `sendMessage(text)` function, refactored out of the original single `handleSend` body.
- **Frontend admin**: Model dropdown and guidance prompt wired to backend; document list loads from disk on mount; model dropdown auto-saves immediately on change
- **Configurable branding** (`app_name`, `theme` in `app_config.json`): Admin panel has a "Branding" section — an App Name text field (saved via the normal "Save Configuration" button, alongside model/guidance) and a Theme selector with two swatches, Indigo (default) and ATS Orange, that auto-saves immediately on click (same pattern as the model dropdown). `GET /branding` is a public, unauthenticated endpoint (`main.py`) returning just `{app_name, theme}` — needed because the Login page has to show the right name/theme *before* a JWT exists, so it can't go through the JWT-gated `/admin/config`. `frontend/src/lib/useBranding.ts` is a small shared hook (`Login.tsx` and `Sidebar.tsx` both use it) that fetches `/branding` on mount and sets `document.documentElement.dataset.theme`, defaulting to `{appName: 'DocBot', theme: 'indigo'}` until it loads so there's no broken flash.
- **Theme system** (`index.css`): Tailwind v4's `@theme` block defines `--color-accent-{400,500,600,700}` as the indigo defaults; `:root[data-theme="orange"]` overrides those same variables with the ATS Orange ramp. Every Tailwind utility that used to say `indigo-*` (buttons, focus rings, chat bubbles, active nav state, etc. — `Login.tsx`, `Chat.tsx`, `Admin.tsx`, `Sidebar.tsx`, `ChatMessage.tsx`, `components/ui/button.tsx`, `components/ui/input.tsx`) now says `accent-*` instead, so switching `data-theme` re-colors the whole app instantly with zero JSX changes — the CSS variable is what actually changes, not the class names. The orange ramp (`#eb9c7d` / `#e6835d` / `#e16839` / `#d15120`) was computed from the real ATS logo's sampled brand color (`#E16839`), lightness-stepped to match how Tailwind's indigo-400/500/600/700 relate to each other, not hand-picked. `Login.tsx`'s animated canvas background (`WaveCanvas`) is separate from Tailwind entirely (raw canvas `fillStyle` RGB values, not CSS classes) — it has its own `WAVE_THEMES.indigo`/`WAVE_THEMES.orange` palettes, and takes `theme` as a prop from `useBranding()` so the wave colors switch along with everything else instead of staying hardcoded blue/purple. The orange wave palette is one orange layer (the brand color) plus grays and whites for the rest — an early version used several close-hue oranges for every layer, which visually flattened into a blob since adjacent wave layers need real color contrast (like indigo/purple/blue in the original) for the underlying wave motion to actually read as "wavy"; the geometry (amplitude/speed/frequency) was never the problem.
- **Company logo**: `ats-logo.jpg` lives in `frontend/public/` (served at `/ats-logo.jpg`, used by `Login.tsx` and `Sidebar.tsx`) and separately in `backend/assets/` (used by `_build_assessment_pdf()`'s PDF header — the backend doesn't reach across into the frontend's folder). It's a flat JPG with a baked-in white background (no transparency), so everywhere it's placed it's wrapped in a small white rounded box rather than dropped directly on the dark UI.
- **ATS tagline**: The subtitle under the app name on the login screen and in the sidebar reads "Real Projects. Real Missions. Real Impact." (hardcoded, not admin-configurable — a direct text swap, unlike `app_name`/`theme`). Purely functional "knowledge base" labels elsewhere (the Admin panel's upload section, the Chat empty-state description) were deliberately left alone since the tagline doesn't fit as a description of those features.
- **Sidebar document list**: Pulls real document list from backend, refreshes on navigation, shows "No documents uploaded" when empty
- **Stream error display**: Errors from the backend stream are shown in the chat bubble instead of silently disappearing
- **Dynamic API URL**: Frontend uses `window.location.hostname` to build the API URL — works on both localhost and EC2 without code changes
- **Diagnostics panel**: Shows active model, CPU%, RAM, response time, last message cost, and a Run Benchmark button — polls every 2 seconds
- **Performance tuning**: Context window 4096 tokens, max response 2048 tokens, last 6 messages of history sent, top 20 RAG chunks; `keep_alive=-1` keeps Ollama model permanently in VRAM
- **Model warmup**: On backend startup, a silent dummy request preloads the Ollama model into VRAM (skipped for Claude models)
- **Benchmark**: `POST /debug/benchmark` runs 3 RAG-grounded prompts and records first token time, total time, peak CPU, avg CPU, peak RAM, avg RAM per prompt
- **CORS**: Set to allow all origins (`*`) for EC2 compatibility — tighten before any real deployment

## What Is NOT Built Yet
- User database — users are hardcoded in `users.py`
- Conversation history does not persist across backend restarts

## Installed Ollama Models
### Laptop
- `gemma3:1b` — chat and enrichment model
- `nomic-embed-text` — embedding model only, used by RAG pipeline (not a chat model)

### EC2 (g4dn.xlarge — NVIDIA T4 GPU, 16GB VRAM)
- `gemma4:latest` — chat and enrichment model, 9.6GB — runs fully on GPU
- `gemma3:1b` — used as fallback enrichment model
- `nomic-embed-text` — embedding model, required for RAG pipeline

### Important
- `nomic-embed-text` must be pulled on every machine before RAG works
- Start Ollama on EC2 with `$env:OLLAMA_NUM_PARALLEL=4; ollama serve` for parallel enrichment
- Claude (API) is only used for chat responses — never for ingestion, embedding, or enrichment

## Claude API Pricing (per million tokens)
| Model | Input | Output |
|---|---|---|
| claude-opus-4-8 | $5.00 | $25.00 |
| claude-sonnet-4-6 | $3.00 | $15.00 |
| claude-haiku-4-5-20251001 | $1.00 | $5.00 |

Cost per message = `(input_tokens × input_rate + output_tokens × output_rate) / 1,000,000`

## Stack
- **Backend**: Python 3.11+ (developed/tested on 3.14), FastAPI, ollama, anthropic, python-dotenv, qdrant-client, pypdf, psutil, python-jose, passlib, bcrypt, `mcp[cli]` (Model Context Protocol server), `fpdf2` (assessment PDF export)
- **Embeddings**: `nomic-embed-text` via Ollama (must be pulled before using RAG)
- **Vector store**: Qdrant (persistent, stored in `qdrant_db/`) — supports hybrid dense + full-text search
- **Frontend**: React 18, Vite, Tailwind CSS, Radix UI primitives, React Router, Lucide icons
- **Not used**: LlamaIndex — RAG pipeline built directly without it

## Project Layout
```
backend/       FastAPI app — main.py, auth.py, users.py, config.py, ingest.py, rag.py
frontend/      React SPA — login, chat, admin panel
knowledge/     PDF knowledge base — admin uploads land here
qdrant_db/     Auto-generated vector store (gitignored)
```

## Running Locally
```bash
# Ollama must be running first
ollama serve

# Backend — uses a virtual environment (backend/.venv, gitignored)
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows; use `source .venv/bin/activate` on macOS/Linux
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
- The `/mcp` endpoint uses a **separate auth scheme** from the rest of the API — a shared-secret `MCP_API_KEY` sent as `Authorization: Bearer <key>`, checked by Starlette middleware before any request reaches MCP dispatch. It is not a JWT and does not go through `auth.py`/`require_admin`.
- `MCP_API_KEY` must be set in `backend/.env` (see `.env.example`) — an empty/unset key causes every MCP request to be rejected (fails closed, not open).

## config.py Reference
```python
KNOWLEDGE_FOLDER = "./knowledge"
QDRANT_PATH = "./qdrant_db"
DEFAULT_MODEL = "gemma4"
ENRICH_MODEL = "gemma4"     # local Ollama model used for contextual enrichment
ENRICH_WORKERS = 4          # parallel threads for ingestion and enrichment
EMBEDDING_MODEL = "nomic-embed-text"
CHUNK_SIZE = 256
CHUNK_OVERLAP = 40
TOP_K = 20          # chunks retrieved per query
MAX_HISTORY = 6     # last N messages sent to LLM
NUM_CTX = 4096      # context window size
NUM_PREDICT = 2048  # max response tokens
SECRET_KEY = "change-me-before-deploying"
ACCESS_TOKEN_EXPIRE_HOURS = 24
MCP_API_KEY = os.getenv("MCP_API_KEY", "")   # required for the MCP server — see backend/.env
```

## API Routes
| Method | Path | Auth | Status | Description |
|---|---|---|---|---|
| POST | `/auth/login` | None | Working | Returns JWT token |
| GET | `/auth/me` | Any | Working | Current user + role |
| POST | `/chat/message` | Any | Working | Streams response via SSE — routes to Ollama or Anthropic based on model name |
| GET | `/admin/documents` | Admin | Working | Lists PDFs from knowledge folder |
| POST | `/admin/upload` | Admin | Working | Saves PDF, runs parallel ingestion into Qdrant, triggers background enrichment |
| DELETE | `/admin/documents/{name}` | Admin | Working | Deletes PDF and removes from Qdrant |
| GET | `/admin/config` | Admin | Working | Returns active model + guidance + app_name + theme |
| POST | `/admin/config` | Admin | Working | Updates active model + guidance + app_name + theme |
| GET | `/branding` | None | Working | Public — returns `{app_name, theme}` only. Used by the Login page (pre-auth) and Sidebar to name/color the app without needing a JWT. |
| GET | `/admin/models` | Admin | Working | Lists installed Ollama models |
| POST | `/chat/clear` | Any | Working | Clears conversation history, assessment state, and completed-assessment record for current user |
| GET | `/chat/assessment/pdf` | Any | Working | Downloads the current user's most recently completed Azure Security Risk Assessment as a PDF (404 if none). Built from real stored answers via `fpdf2`, not the model. |
| GET | `/debug/stats` | Any | Working | Returns CPU%, RAM, active model (temp diagnostic) |
| POST | `/debug/benchmark` | Any | Working | Runs 3 RAG prompts, returns timing and resource usage per prompt |
| POST | `/mcp` | `MCP_API_KEY` (bearer, not JWT) | Working | MCP Streamable HTTP endpoint — six tools: `upload_text`, `upload_pdf`, `list_documents`, `delete_document`, `enrichment_status`, `query_knowledge`. Not a plain REST route — speaks MCP's JSON-RPC protocol. |
| POST | `/webhook/teams-ingest` | `MCP_API_KEY` (bearer, not JWT) | Working | Plain REST/JSON endpoint (not MCP) for Power Automate → Teams ingestion. Body: `{"text": string, "source_name"?: string}`. Reuses `ingest.ingest_text()` + background enrichment, same as MCP's `upload_text`. Auto-generates `source_name` as `teams-YYYYMMDD-HHMMSS` if omitted; rejects `.pdf` suffixes. |

## Do not edit front end code without asking first
