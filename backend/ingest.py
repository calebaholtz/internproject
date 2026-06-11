import os
import pypdf
import chromadb
import ollama
import config as cfg

os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)

_client = chromadb.PersistentClient(path="./chroma_db")
collection = _client.get_or_create_collection("knowledge")


def _chunk_text(text: str) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + cfg.CHUNK_SIZE])
        if chunk:
            chunks.append(chunk)
        i += cfg.CHUNK_SIZE - cfg.CHUNK_OVERLAP
    return chunks


def ingest_file(path: str):
    filename = os.path.basename(path)

    existing = collection.get(where={"source": filename})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    reader = pypdf.PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    chunks = _chunk_text(text)

    if not chunks:
        return

    embeddings = [
        ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=c).embedding
        for c in chunks
    ]

    collection.add(
        ids=[f"{filename}_{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=chunks,
        metadatas=[{"source": filename}] * len(chunks),
    )


def delete_file(filename: str):
    existing = collection.get(where={"source": filename})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
