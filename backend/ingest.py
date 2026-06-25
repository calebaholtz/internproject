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
    all_chunks = []
    all_embeddings = []
    all_ids = []
    all_metadatas = []
    chunk_index = 0

    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        chunks = _chunk_text(text)
        for chunk in chunks:
            embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=chunk).embedding
            all_chunks.append(chunk)
            all_embeddings.append(embedding)
            all_ids.append(f"{filename}_{chunk_index}")
            all_metadatas.append({"source": filename, "page": page_num, "enriched": False})
            chunk_index += 1

    if all_chunks:
        collection.add(
            ids=all_ids,
            embeddings=all_embeddings,
            documents=all_chunks,
            metadatas=all_metadatas,
        )


def enrich_file(filename: str, model: str):
    results = collection.get(where={"source": filename})
    if not results["ids"]:
        return

    for chunk_id, doc, meta in zip(results["ids"], results["documents"], results["metadatas"]):
        if meta.get("enriched"):
            continue
        try:
            response = ollama.chat(
                model=model,
                messages=[{
                    "role": "user",
                    "content": (
                        "Briefly describe in 1-2 sentences what section, topic, or concept "
                        "this text chunk is from. Mention any visible section numbers, headings, "
                        "or key topics. Output only the description.\n\nText:\n" + doc
                    ),
                }],
                options={"num_predict": 80},
            )
            description = response.message.content.strip()
            enriched_text = f"{description}\n\n{doc}"
            new_embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=enriched_text).embedding
            collection.update(
                ids=[chunk_id],
                embeddings=[new_embedding],
                documents=[enriched_text],
                metadatas=[{**meta, "enriched": True}],
            )
        except Exception:
            continue


def enrichment_status(filename: str) -> dict:
    results = collection.get(where={"source": filename})
    total = len(results["ids"])
    enriched = sum(1 for m in results["metadatas"] if m.get("enriched"))
    return {"total": total, "enriched": enriched, "done": total > 0 and enriched == total}


def delete_file(filename: str):
    existing = collection.get(where={"source": filename})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
