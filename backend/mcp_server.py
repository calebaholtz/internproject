import os
import base64
import threading
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import config as cfg
import ingest
import rag

mcp_instance = FastMCP(
    "knowledge-base",
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        expected = cfg.MCP_API_KEY
        provided = request.headers.get("authorization", "")
        if not expected or provided != f"Bearer {expected}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


@mcp_instance.tool()
def upload_text(text: str, source_name: str) -> dict:
    """Add raw text content to the knowledge base under the given source name.
    Re-using an existing source_name REPLACES that document's existing chunks.
    source_name must not end in .pdf — use upload_pdf for PDF files."""
    if source_name.lower().endswith(".pdf"):
        raise ValueError("source_name must not end in .pdf — use upload_pdf for PDF files.")
    chunk_count = ingest.ingest_text(text, source_name)
    threading.Thread(
        target=ingest.enrich_file,
        args=(source_name, cfg.ENRICH_MODEL),
        daemon=True,
    ).start()
    return {"status": "ok", "source_name": source_name, "chunks_created": chunk_count}


@mcp_instance.tool()
def upload_pdf(filename: str, content_base64: str) -> dict:
    """Upload a PDF file to the knowledge base. filename must end in .pdf.
    content_base64 is the base64-encoded bytes of the PDF file."""
    if not filename.lower().endswith(".pdf"):
        raise ValueError("filename must end in .pdf")
    os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)
    path = os.path.join(cfg.KNOWLEDGE_FOLDER, filename)
    try:
        contents = base64.b64decode(content_base64)
    except Exception as e:
        raise ValueError(f"Invalid base64 content: {e}")
    with open(path, "wb") as f:
        f.write(contents)
    try:
        ingest.ingest_file(path)
    except Exception as e:
        raise RuntimeError(f"Ingestion error: {e}")
    threading.Thread(
        target=ingest.enrich_file,
        args=(filename, cfg.ENRICH_MODEL),
        daemon=True,
    ).start()
    return {"status": "ok", "filename": filename}


@mcp_instance.tool()
def list_documents() -> dict:
    """List all documents currently in the knowledge base with their chunk counts."""
    counts = ingest.get_chunk_counts()
    return {"documents": [{"source_name": name, "chunk_count": count} for name, count in counts.items()]}


@mcp_instance.tool()
def delete_document(source_name: str) -> dict:
    """Delete a document from the knowledge base by its source name.
    Also removes the on-disk file if one exists (e.g. an uploaded PDF)."""
    path = os.path.join(cfg.KNOWLEDGE_FOLDER, source_name)
    if os.path.exists(path):
        os.remove(path)
    ingest.delete_file(source_name)
    return {"status": "ok"}


@mcp_instance.tool()
def enrichment_status(source_name: str) -> dict:
    """Check background contextual-enrichment progress for a document."""
    return ingest.enrichment_status(source_name)


@mcp_instance.tool()
def query_knowledge(query: str) -> dict:
    """Query the knowledge base and return the most relevant document context for a question."""
    context = rag.retrieve(query)
    return {"context": context}


mcp_app = mcp_instance.streamable_http_app()
mcp_app.add_middleware(ApiKeyMiddleware)
