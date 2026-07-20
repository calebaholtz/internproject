from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from auth import authenticate_user, create_access_token, get_current_user, require_admin
from fpdf import FPDF
from fpdf.fonts import FontFace
from datetime import datetime
import ollama
import anthropic
import config as cfg
import json
import psutil
import os
import time
import random
import threading
import contextlib
import ingest
import rag
import mcp_server

CLAUDE_MODELS = [
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]

CLAUDE_PRICING = {
    "claude-opus-4-8":           {"input":  5.00, "output": 25.00},
    "claude-sonnet-4-6":         {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input":  1.00, "output":  5.00},
}

def _is_claude(model: str) -> bool:
    return model.startswith("claude-")

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    model = _load_config().get("model", cfg.DEFAULT_MODEL)
    if not _is_claude(model):
        try:
            ollama.chat(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1},
                keep_alive=-1,
            )
        except Exception:
            pass
    async with mcp_server.mcp_instance.session_manager.run():
        yield


app = FastAPI(title="DocBot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", mcp_server.mcp_app)

CONFIG_FILE = "app_config.json"
_default_config = {
    "model": cfg.DEFAULT_MODEL,
    "guidance": "Answer questions accurately and concisely. If you don't know, say so.",
    "app_name": "DocBot",
    "theme": "indigo",
}

def _load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return _default_config.copy()

def _save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(app_config, f, indent=2)

app_config = _load_config()

# Per-user conversation history
conversation_histories: dict[str, list] = {}

# Per-user Azure Security Risk Assessment progress (tracked server-side so the
# final summary reflects real captured answers, not the model's recollection
# of a conversation that may have scrolled out of MAX_HISTORY)
assessment_states: dict[str, dict] = {}

# Most recently completed assessment per user, kept after assessment_states is
# cleared so the PDF download route has real data to render
completed_assessments: dict[str, dict] = {}

ASSESSMENT_QUESTIONS = [
    {"id": 1, "type": "mc", "text": "Which Microsoft Azure subscription does your organization currently use?",
     "options": ["Free", "Pay-As-You-Go", "Microsoft 365 E3", "Microsoft 365 E5", "Azure AD Premium P1", "Azure AD Premium P2"]},
    {"id": 2, "type": "yesno", "text": "Do you have Microsoft Purview Insider Risk Management enabled as part of your license?"},
    {"id": 3, "type": "yesno", "text": "Have you configured policies for data leaks (e.g., large file downloads, uploads to external domains)?"},
    {"id": 4, "type": "yesno", "text": "Do you monitor privileged account activities (e.g., admin role changes, excessive permission grants)?"},
    {"id": 5, "type": "yesno", "text": "Are you currently tracking unusual login activity (e.g., impossible travel, risky sign-ins)?"},
    {"id": 6, "type": "yesno", "text": "Do you have policies for departing employees (e.g., downloading data before leaving, forwarding emails)?"},
    {"id": 7, "type": "yesno", "text": "Are you using Microsoft Defender for Cloud Apps (MCAS) to detect risky app usage?"},
    {"id": 8, "type": "yesno", "text": "Have you enabled alerts for unsanctioned cloud app usage or shadow IT?"},
    {"id": 9, "type": "yesno", "text": "Do you use Microsoft 365 Audit Logs for monitoring insider activity?"},
    {"id": 10, "type": "yesno", "text": "Have you set up automated alerting for unusual email forwarding or mailbox rules?"},
]
ASSESSMENT_QUESTIONS_BY_ID = {q["id"]: q for q in ASSESSMENT_QUESTIONS}

ASSESSMENT_TRIGGERS = [
    "start the assessment", "start the azure", "begin the assessment", "begin the azure",
    "walk me through the 10 question", "walk me through the ten question",
    "azure security questionnaire", "azure risk assessment", "take the assessment",
]
ASSESSMENT_CANCEL_TRIGGERS = ["cancel the assessment", "exit the assessment", "stop the assessment", "cancel assessment"]


def _is_assessment_trigger(message: str) -> bool:
    text = message.lower()
    return any(t in text for t in ASSESSMENT_TRIGGERS)


def _is_assessment_cancel(message: str) -> bool:
    text = message.lower()
    return any(t in text for t in ASSESSMENT_CANCEL_TRIGGERS)


def _parse_yes_no(message: str):
    text = message.strip().lower().strip(".,!? ")
    yes_words = {"yes", "y", "yeah", "yep", "yup", "correct", "affirmative"}
    no_words = {"no", "n", "nope", "nah", "negative"}
    first_word = text.split()[0] if text.split() else ""
    if text in yes_words or first_word in yes_words or text.startswith("yes"):
        return True
    if text in no_words or first_word in no_words or text.startswith("no"):
        return False
    return None


def _next_question_id(qid: int, is_yes: bool):
    if qid == 2:
        return 3 if is_yes else 7
    if qid == 7:
        return 8 if is_yes else 9
    if qid == 9:
        return 10 if is_yes else None
    if qid == 10:
        return None
    return qid + 1


def _format_question(q: dict) -> str:
    header = f"Question {q['id']} of 10\n\n{q['text']}"
    if q["type"] == "mc":
        options = "\n".join(f"- {o}" for o in q["options"])
        return f"{header}\n\nPlease select one:\n{options}"
    return f"{header}\n\nPlease answer: Yes or No"


def _build_summary_table(answers: dict) -> str:
    rows = "\n".join(
        f"| Q{qid}: {ASSESSMENT_QUESTIONS_BY_ID[qid]['text']} | {ans} |"
        for qid, ans in sorted(answers.items())
    )
    return f"| Question | Your Answer |\n|---|---|\n{rows}"


THEME_COLORS = {
    "indigo": (79, 70, 229),
    "orange": (225, 104, 57),
}
PDF_DARK = (30, 30, 32)
PDF_GRAY = (110, 110, 115)
PDF_LIGHT_GRAY = (240, 240, 241)
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "ats-logo.jpg")


class _AssessmentPDF(FPDF):
    accent_color = THEME_COLORS["indigo"]

    def header(self):
        # Small letterhead-style logo, top-left - no color blocks, just a clean corporate header
        if os.path.exists(LOGO_PATH):
            self.image(LOGO_PATH, x=10, y=10, w=26)
        self.set_xy(0, 12)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*PDF_DARK)
        self.cell(self.w - 10, 8, "Azure Security Risk Assessment", align="R")
        self.set_xy(0, 20)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*PDF_GRAY)
        self.cell(self.w - 10, 6, "Summary Report", align="R")
        # single thin accent rule - the only spot of color on the page
        self.set_draw_color(*self.accent_color)
        self.set_line_width(0.8)
        self.line(10, 32, self.w - 10, 32)
        self.set_y(40)

    def footer(self):
        self.set_draw_color(220, 220, 220)
        self.set_line_width(0.2)
        self.line(10, self.h - 18, self.w - 10, self.h - 18)
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*PDF_GRAY)
        self.cell(0, 10, f"Confidential  |  Page {self.page_no()}", align="C")


def _build_assessment_pdf(username: str, answers: dict, completed_at: str) -> bytes:
    accent = THEME_COLORS.get(app_config.get("theme", "indigo"), THEME_COLORS["indigo"])

    pdf = _AssessmentPDF()
    pdf.accent_color = accent
    pdf.add_page()

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*PDF_GRAY)
    pdf.cell(0, 6, f"Completed by: {username}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Date: {completed_at}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    heading_style = FontFace(emphasis="BOLD", color=PDF_DARK, fill_color=PDF_LIGHT_GRAY)
    with pdf.table(
        col_widths=(65, 35),
        text_align=("LEFT", "LEFT"),
        headings_style=heading_style,
        line_height=6,
        padding=2,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        header_row = table.row()
        header_row.cell("Question")
        header_row.cell("Answer")
        for qid, ans in sorted(answers.items()):
            row = table.row()
            row.cell(f"Q{qid}: {ASSESSMENT_QUESTIONS_BY_ID[qid]['text']}")
            row.cell(str(ans))

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(*PDF_GRAY)
    pdf.multi_cell(
        0, 6,
        "Responses have been captured for expert review. A dedicated team will "
        "follow up with a custom report and prioritized recommendations.",
    )

    return bytes(pdf.output())


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str


class ChatRequest(BaseModel):
    message: str


class ConfigUpdate(BaseModel):
    model: str | None = None
    guidance: str | None = None
    app_name: str | None = None
    theme: str | None = None


@app.post("/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@app.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"]}


def _stream_llm(system_message: str, messages: list[dict], response_holder: list):
    model = app_config["model"]

    if _is_claude(model):
        client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        with client.messages.stream(
            model=model,
            max_tokens=cfg.NUM_PREDICT,
            system=system_message,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        ) as stream:
            for text in stream.text_stream:
                response_holder.append(text)
                yield f"data: {json.dumps({'content': text})}\n\n"
            usage = stream.get_final_message().usage
            pricing = CLAUDE_PRICING.get(model, {"input": 0, "output": 0})
            cost = (usage.input_tokens * pricing["input"] + usage.output_tokens * pricing["output"]) / 1_000_000
            yield f"data: {json.dumps({'cost': round(cost, 8), 'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens})}\n\n"
    else:
        full_messages = [{"role": "system", "content": system_message}] + messages
        stream = ollama.chat(
            model=model,
            messages=full_messages,
            stream=True,
            options={"num_ctx": cfg.NUM_CTX, "num_predict": cfg.NUM_PREDICT},
            keep_alive=-1,
        )
        for chunk in stream:
            content = chunk.message.content
            if content:
                response_holder.append(content)
                yield f"data: {json.dumps({'content': content})}\n\n"
        yield f"data: {json.dumps({'cost': 0.0, 'input_tokens': None, 'output_tokens': None})}\n\n"


def _sse_response(
    system_message: str, messages: list[dict], username: str,
    in_assessment: bool = False, assessment_completed: bool = False,
) -> StreamingResponse:
    def generate():
        full_response = []
        try:
            yield from _stream_llm(system_message, messages, full_response)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if full_response:
                conversation_histories[username].append({"role": "assistant", "content": "".join(full_response)})
        yield f"data: {json.dumps({'in_assessment': in_assessment, 'assessment_completed': assessment_completed})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


def _sse_static(text: str, username: str, in_assessment: bool = False) -> StreamingResponse:
    def generate():
        yield f"data: {json.dumps({'content': text})}\n\n"
        conversation_histories[username].append({"role": "assistant", "content": text})
        yield f"data: {json.dumps({'cost': 0.0, 'input_tokens': None, 'output_tokens': None})}\n\n"
        yield f"data: {json.dumps({'in_assessment': in_assessment, 'assessment_completed': False})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/chat/message")
def chat_message(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    if username not in conversation_histories:
        conversation_histories[username] = []

    conversation_histories[username].append({"role": "user", "content": body.message})

    if assessment_states.get(username) is not None and _is_assessment_cancel(body.message):
        del assessment_states[username]
        return _sse_static("The Azure Security Risk Assessment has been cancelled. How else can I help?", username)

    if _is_assessment_trigger(body.message):
        assessment_states[username] = {"current_q": 1, "answers": {}}
        first_q = ASSESSMENT_QUESTIONS_BY_ID[1]
        instruction = (
            "The user wants to begin the Azure Security Risk Assessment. Write a warm, brief (2-4 sentence) "
            "opening: greet them, and include a short note on why organizations should proactively manage "
            "insider risk (vary the wording each time - don't reuse identical phrasing across runs). Then say "
            "exactly this, verbatim: \"Let's step through ten questions to assess Azure security. When "
            "complete, I'll summarize your responses and share them with our team of experts for review. "
            "They'll follow up soon with a highly tailored report and prioritized recommendations.\" Then "
            "present this exact question, verbatim and unaltered (do not change the wording or options):\n\n"
            f"{_format_question(first_q)}"
        )
        return _sse_response(app_config["guidance"], [{"role": "user", "content": instruction}], username, in_assessment=True)

    state = assessment_states.get(username)
    if state is not None:
        current_q = ASSESSMENT_QUESTIONS_BY_ID[state["current_q"]]

        if current_q["type"] == "yesno":
            is_yes = _parse_yes_no(body.message)
            if is_yes is None:
                return _sse_static("Sorry, I didn't catch that - could you answer with Yes or No?", username, in_assessment=True)
            state["answers"][current_q["id"]] = "Yes" if is_yes else "No"
            next_id = _next_question_id(current_q["id"], is_yes)
        else:
            state["answers"][current_q["id"]] = body.message.strip()
            next_id = _next_question_id(current_q["id"], True)

        if next_id is not None:
            state["current_q"] = next_id
            next_q = ASSESSMENT_QUESTIONS_BY_ID[next_id]
            instruction = (
                f"The user just answered the previous question with: \"{body.message.strip()}\". Briefly and "
                "warmly acknowledge their answer in one short sentence (vary the wording, no scored feedback "
                "or risk rating). Then present this exact next question, verbatim and unaltered (do not "
                f"change the wording or options):\n\n{_format_question(next_q)}"
            )
            return _sse_response(app_config["guidance"], [{"role": "user", "content": instruction}], username, in_assessment=True)

        answers = state["answers"]
        del assessment_states[username]
        completed_assessments[username] = {"answers": answers, "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
        summary_table = _build_summary_table(answers)
        instruction = (
            "The Azure Security Risk Assessment is now complete. Here is the user's real, captured data - "
            f"reproduce it exactly as given, do not alter, invent, or omit any row:\n\n{summary_table}\n\n"
            "Write a polished wrap-up: thank the user, clearly state the questionnaire is complete, then "
            "include the table above. Close by emphasizing their responses have been captured for expert "
            "review and a dedicated team will follow up with a custom report and prioritized "
            "recommendations. Do not offer automated recommendations, risk scores, or next steps yourself."
        )
        return _sse_response(
            app_config["guidance"], [{"role": "user", "content": instruction}], username,
            in_assessment=False, assessment_completed=True,
        )

    context = rag.retrieve(body.message)
    if context:
        system_message = (
            f"{app_config['guidance']}\n\n"
            "Use ONLY the following document excerpts to answer the question. "
            "Answer based strictly on what is written in these excerpts. "
            "If the question asks about a specific section or topic and it is not clearly present in the excerpts below, say so rather than guessing.\n\n"
            f"{context}"
        )
    else:
        system_message = app_config["guidance"]

    recent_history = conversation_histories[username][-cfg.MAX_HISTORY:]
    return _sse_response(system_message, recent_history, username)


@app.get("/chat/assessment/pdf")
def download_assessment_pdf(current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    record = completed_assessments.get(username)
    if not record:
        raise HTTPException(status_code=404, detail="No completed assessment found")

    pdf_bytes = _build_assessment_pdf(username, record["answers"], record["completed_at"])
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="azure-security-assessment-{username}.pdf"'},
    )


@app.post("/chat/clear")
def clear_history(current_user: dict = Depends(get_current_user)):
    conversation_histories[current_user["username"]] = []
    assessment_states.pop(current_user["username"], None)
    completed_assessments.pop(current_user["username"], None)
    return {"status": "ok"}


class TeamsIngestRequest(BaseModel):
    text: str
    source_name: str | None = None


@app.post("/webhook/teams-ingest")
def teams_ingest(body: TeamsIngestRequest, authorization: str = Header(default="")):
    if not cfg.MCP_API_KEY or authorization != f"Bearer {cfg.MCP_API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    source_name = body.source_name or f"teams-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if source_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="source_name must not end in .pdf")

    chunk_count = ingest.ingest_text(body.text, source_name)
    threading.Thread(
        target=ingest.enrich_file,
        args=(source_name, cfg.ENRICH_MODEL),
        daemon=True,
    ).start()

    return {"status": "ok", "source_name": source_name, "chunks_created": chunk_count}


@app.get("/admin/chunks")
def list_chunks(current_user: dict = Depends(require_admin)):
    counts = ingest.get_chunk_counts()
    return {"chunk_counts": counts, "total": sum(counts.values())}


@app.get("/admin/enrichment-status")
def enrichment_status(current_user: dict = Depends(require_admin)):
    os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)
    docs = [n for n in os.listdir(cfg.KNOWLEDGE_FOLDER) if n.endswith(".pdf")]
    return {name: ingest.enrichment_status(name) for name in docs}


@app.get("/admin/documents")
def list_documents(current_user: dict = Depends(require_admin)):
    os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)
    doc_info = ingest.get_document_info()
    docs = []
    for source, info in doc_info.items():
        path = os.path.join(cfg.KNOWLEDGE_FOLDER, source)
        if source.endswith(".pdf") and os.path.exists(path):
            size_kb = os.path.getsize(path) // 1024
            mtime = os.path.getmtime(path)
            uploaded = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            docs.append({"name": source, "size": f"{size_kb} KB", "uploaded": uploaded})
        else:
            uploaded = info.get("uploaded_at") or "N/A"
            docs.append({"name": source, "size": f"{info['chunk_count']} chunks", "uploaded": uploaded})
    return {"documents": docs}


@app.post("/admin/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)
    path = os.path.join(cfg.KNOWLEDGE_FOLDER, file.filename)
    contents = await file.read()
    with open(path, "wb") as f:
        f.write(contents)
    try:
        ingest.ingest_file(path)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ingestion error: {str(e)}")

    enrich_model = cfg.ENRICH_MODEL
    threading.Thread(
        target=ingest.enrich_file,
        args=(file.filename, enrich_model),
        daemon=True,
    ).start()

    return {"status": "ok", "filename": file.filename}


@app.delete("/admin/documents/{name}")
def delete_document(name: str, current_user: dict = Depends(require_admin)):
    path = os.path.join(cfg.KNOWLEDGE_FOLDER, name)
    if not os.path.exists(path) and name not in ingest.get_document_info():
        raise HTTPException(status_code=404, detail="Document not found")
    if os.path.exists(path):
        os.remove(path)
    ingest.delete_file(name)
    return {"status": "ok"}


@app.get("/admin/models")
def list_models(current_user: dict = Depends(require_admin)):
    try:
        models = ollama.list()
        embedding_models = {"nomic-embed-text", "mxbai-embed-large", "all-minilm", "nomic-embed-text:latest"}
        ollama_names = [m.model for m in models.models if m.model not in embedding_models]
    except Exception:
        ollama_names = []
    claude_names = CLAUDE_MODELS if cfg.ANTHROPIC_API_KEY else []
    return {"models": ollama_names + claude_names}


@app.get("/admin/config")
def get_config(current_user: dict = Depends(require_admin)):
    return app_config


@app.post("/admin/config")
def update_config(body: ConfigUpdate, current_user: dict = Depends(require_admin)):
    if body.model is not None:
        app_config["model"] = body.model
    if body.guidance is not None:
        app_config["guidance"] = body.guidance
    if body.app_name is not None:
        app_config["app_name"] = body.app_name
    if body.theme is not None:
        if body.theme not in ("indigo", "orange"):
            raise HTTPException(status_code=400, detail="theme must be 'indigo' or 'orange'")
        app_config["theme"] = body.theme
    _save_config()
    return {"status": "ok"}


@app.get("/branding")
def get_branding():
    return {
        "app_name": app_config.get("app_name", "DocBot"),
        "theme": app_config.get("theme", "indigo"),
    }


@app.get("/debug/stats")
def debug_stats(current_user: dict = Depends(get_current_user)):
    ram = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_used_gb": round(ram.used / 1024 ** 3, 1),
        "ram_total_gb": round(ram.total / 1024 ** 3, 1),
        "ram_percent": ram.percent,
        "active_model": app_config["model"],
    }


BENCHMARK_PROMPTS = [
    {"label": "Summary",      "prompt": "Summarize the main topics covered in the uploaded documents."},
    {"label": "Key details",  "prompt": "What are the most important details from the documents?"},
    {"label": "Specifics",    "prompt": "List the key findings or items mentioned in the documents as bullet points."},
]

@app.post("/debug/benchmark")
def run_benchmark(current_user: dict = Depends(get_current_user)):
    results = []
    for item in BENCHMARK_PROMPTS:
        try:
            context = rag.retrieve(item["prompt"])
            system_message = (
                f"{app_config['guidance']}\n\nUse the following document excerpts to answer the question. "
                f"If the answer is not in the documents, say so.\n\n{context}"
            ) if context else app_config["guidance"]

            # Background sampler
            samples = []
            stop_event = threading.Event()

            def _sample():
                psutil.cpu_percent(interval=None)
                while not stop_event.is_set():
                    samples.append({
                        "cpu": psutil.cpu_percent(interval=0.5),
                        "ram": psutil.virtual_memory().percent,
                    })

            sampler = threading.Thread(target=_sample, daemon=True)
            sampler.start()

            start = time.time()
            model = app_config["model"]
            response_text = ""
            ttft = None
            prompt_cost = 0.0
            if _is_claude(model):
                client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
                with client.messages.stream(
                    model=model,
                    max_tokens=cfg.NUM_PREDICT,
                    system=system_message,
                    messages=[{"role": "user", "content": item["prompt"]}],
                ) as stream:
                    for text in stream.text_stream:
                        if ttft is None:
                            ttft = round(time.time() - start, 2)
                        response_text += text
                    usage = stream.get_final_message().usage
                    pricing = CLAUDE_PRICING.get(model, {"input": 0, "output": 0})
                    prompt_cost = (usage.input_tokens * pricing["input"] + usage.output_tokens * pricing["output"]) / 1_000_000
            else:
                stream = ollama.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user",   "content": item["prompt"]},
                    ],
                    stream=True,
                    options={"num_ctx": cfg.NUM_CTX, "num_predict": cfg.NUM_PREDICT},
                    keep_alive=-1,
                )
                for chunk in stream:
                    content = chunk.message.content
                    if content:
                        if ttft is None:
                            ttft = round(time.time() - start, 2)
                        response_text += content
            total = round(time.time() - start, 2)

            stop_event.set()
            sampler.join()

            peak_cpu = round(max((s["cpu"] for s in samples), default=0), 1)
            avg_cpu  = round(sum(s["cpu"] for s in samples) / len(samples), 1) if samples else 0
            peak_ram = round(max((s["ram"] for s in samples), default=0), 1)
            avg_ram  = round(sum(s["ram"] for s in samples) / len(samples), 1) if samples else 0

            results.append({
                "label": item["label"],
                "prompt": item["prompt"],
                "ttft_s": ttft,
                "total_s": total,
                "cost": round(prompt_cost, 8),
                "peak_cpu": peak_cpu,
                "avg_cpu": avg_cpu,
                "peak_ram": peak_ram,
                "avg_ram": avg_ram,
                "response_preview": response_text[:150].strip(),
                "error": None,
            })
        except Exception as e:
            results.append({
                "label": item["label"],
                "prompt": item["prompt"],
                "ttft_s": None,
                "total_s": None,
                "cost": None,
                "peak_cpu": None,
                "avg_cpu": None,
                "peak_ram": None,
                "avg_ram": None,
                "response_preview": None,
                "error": str(e),
            })
    return {
        "model": app_config["model"],
        "results": results,
    }
