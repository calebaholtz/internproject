from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from auth import authenticate_user, create_access_token, get_current_user, require_admin
import ollama
import anthropic
import config as cfg
import json
import psutil
import os
import time
import threading
import ingest
import rag

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

app = FastAPI(title="DocBot API")


@app.on_event("startup")
def warmup():
    model = _load_config().get("model", cfg.DEFAULT_MODEL)
    if _is_claude(model):
        return
    try:
        ollama.chat(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            options={"num_predict": 1},
            keep_alive=-1,
        )
    except Exception:
        pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = "app_config.json"
_default_config = {
    "model": cfg.DEFAULT_MODEL,
    "guidance": "Answer questions accurately and concisely. If you don't know, say so.",
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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str


class ChatRequest(BaseModel):
    message: str


class ConfigUpdate(BaseModel):
    model: str | None = None
    guidance: str | None = None


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


@app.post("/chat/message")
def chat_message(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    username = current_user["username"]
    if username not in conversation_histories:
        conversation_histories[username] = []

    conversation_histories[username].append({"role": "user", "content": body.message})

    def generate():
        full_response = []
        try:
            context = rag.retrieve(body.message)
            if context:
                system_message = (
                    f"{app_config['guidance']}\n\n"
                    "Use the following document excerpts to answer the question. "
                    "If the answer is not in the documents, say so.\n\n"
                    f"{context}"
                )
            else:
                system_message = app_config["guidance"]

            recent_history = conversation_histories[username][-cfg.MAX_HISTORY:]
            model = app_config["model"]

            if _is_claude(model):
                client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
                with client.messages.stream(
                    model=model,
                    max_tokens=cfg.NUM_PREDICT,
                    system=system_message,
                    messages=[{"role": m["role"], "content": m["content"]} for m in recent_history],
                ) as stream:
                    for text in stream.text_stream:
                        full_response.append(text)
                        yield f"data: {json.dumps({'content': text})}\n\n"
                    usage = stream.get_final_message().usage
                    pricing = CLAUDE_PRICING.get(model, {"input": 0, "output": 0})
                    cost = (usage.input_tokens * pricing["input"] + usage.output_tokens * pricing["output"]) / 1_000_000
                    yield f"data: {json.dumps({'cost': round(cost, 8), 'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens})}\n\n"
            else:
                messages = [{"role": "system", "content": system_message}] + recent_history
                stream = ollama.chat(
                    model=model,
                    messages=messages,
                    stream=True,
                    options={"num_ctx": cfg.NUM_CTX, "num_predict": cfg.NUM_PREDICT},
                    keep_alive=-1,
                )
                for chunk in stream:
                    content = chunk.message.content
                    if content:
                        full_response.append(content)
                        yield f"data: {json.dumps({'content': content})}\n\n"
                yield f"data: {json.dumps({'cost': 0.0, 'input_tokens': None, 'output_tokens': None})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if full_response:
                conversation_histories[username].append({
                    "role": "assistant",
                    "content": "".join(full_response),
                })
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/chat/clear")
def clear_history(current_user: dict = Depends(get_current_user)):
    conversation_histories[current_user["username"]] = []
    return {"status": "ok"}


@app.get("/admin/documents")
def list_documents(current_user: dict = Depends(require_admin)):
    os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)
    docs = []
    for name in os.listdir(cfg.KNOWLEDGE_FOLDER):
        if name.endswith(".pdf"):
            path = os.path.join(cfg.KNOWLEDGE_FOLDER, name)
            size_kb = os.path.getsize(path) // 1024
            mtime = os.path.getmtime(path)
            from datetime import datetime
            uploaded = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            docs.append({"name": name, "size": f"{size_kb} KB", "uploaded": uploaded})
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
    return {"status": "ok", "filename": file.filename}


@app.delete("/admin/documents/{name}")
def delete_document(name: str, current_user: dict = Depends(require_admin)):
    path = os.path.join(cfg.KNOWLEDGE_FOLDER, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Document not found")
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
    _save_config()
    return {"status": "ok"}


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
