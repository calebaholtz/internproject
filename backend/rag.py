import chromadb
import ollama
import config as cfg

_client = chromadb.PersistentClient(path="./chroma_db")
collection = _client.get_or_create_collection("knowledge")


def retrieve(query: str) -> str:
    embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=query).embedding
    results = collection.query(query_embeddings=[embedding], n_results=cfg.TOP_K)

    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results["metadatas"] else []

    if not docs:
        return ""

    parts = []
    for doc, meta in zip(docs, metas):
        source = meta.get("source", "unknown")
        parts.append(f"[Source: {source}]\n{doc}")

    return "\n\n---\n\n".join(parts)
