from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from auth import authenticate_user, create_access_token, get_current_user, require_admin
import ollama
import config as cfg
import json
import psutil

app = FastAPI(title="DocBot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory config — persists for the lifetime of the server process
app_config = {
    "model": cfg.DEFAULT_MODEL,
    "guidance": "Answer questions accurately and concisely. If you don't know, say so.",
}

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
            messages = [{"role": "system", "content": app_config["guidance"]}] + conversation_histories[username]
            stream = ollama.chat(
                model=app_config["model"],
                messages=messages,
                stream=True,
                options={"num_ctx": 2048},
            )
            for chunk in stream:
                content = chunk.message.content
                if content:
                    full_response.append(content)
                    yield f"data: {json.dumps({'content': content})}\n\n"
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
    return {"documents": []}


@app.get("/admin/models")
def list_models(current_user: dict = Depends(require_admin)):
    try:
        models = ollama.list()
        names = [m.model for m in models.models]
        return {"models": names}
    except Exception:
        return {"models": []}


@app.get("/admin/config")
def get_config(current_user: dict = Depends(require_admin)):
    return app_config


@app.post("/admin/config")
def update_config(body: ConfigUpdate, current_user: dict = Depends(require_admin)):
    if body.model is not None:
        app_config["model"] = body.model
    if body.guidance is not None:
        app_config["guidance"] = body.guidance
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
