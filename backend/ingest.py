import os
import uuid
import pypdf
import ollama
import config as cfg
from concurrent.futures import ThreadPoolExecutor, as_completed
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from db import client, COLLECTION

os.makedirs(cfg.KNOWLEDGE_FOLDER, exist_ok=True)


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


def _make_id(filename: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{filename}_{chunk_index}"))


def ingest_file(path: str):
    filename = os.path.basename(path)
    delete_file(filename)

    reader = pypdf.PdfReader(path)
    raw_chunks = []
    chunk_index = 0

    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        for chunk in _chunk_text(text):
            raw_chunks.append((chunk_index, page_num, chunk))
            chunk_index += 1

    def _embed_chunk(item):
        idx, page_num, chunk = item
        embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=chunk).embedding
        return PointStruct(
            id=_make_id(filename, idx),
            vector=embedding,
            payload={"source": filename, "page": page_num, "text": chunk, "enriched": False},
        )

    points = []
    with ThreadPoolExecutor(max_workers=cfg.ENRICH_WORKERS) as executor:
        futures = {executor.submit(_embed_chunk, item): item for item in raw_chunks}
        for future in as_completed(futures):
            try:
                points.append(future.result())
            except Exception:
                pass

    if points:
        client.upsert(collection_name=COLLECTION, points=points)


def _enrich_chunk(point, model: str):
    if point.payload.get("enriched"):
        return
    try:
        original_text = point.payload.get("text", "")
        response = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": (
                    "Briefly describe in 1-2 sentences what section, topic, or concept "
                    "this text chunk is from. Mention any visible section numbers, headings, "
                    "or key topics. Output only the description.\n\nText:\n" + original_text
                ),
            }],
            options={"num_predict": 80},
        )
        description = response.message.content.strip()
        enriched_text = f"{description}\n\n{original_text}"
        new_embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=enriched_text).embedding
        client.upsert(
            collection_name=COLLECTION,
            points=[PointStruct(
                id=point.id,
                vector=new_embedding,
                payload={**point.payload, "text": enriched_text, "enriched": True},
            )],
        )
    except Exception:
        pass


def enrich_file(filename: str, model: str):
    results, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=filename))]),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    unenriched = [p for p in results if not p.payload.get("enriched")]

    with ThreadPoolExecutor(max_workers=cfg.ENRICH_WORKERS) as executor:
        futures = [executor.submit(_enrich_chunk, point, model) for point in unenriched]
        for future in as_completed(futures):
            future.result()


def enrichment_status(filename: str) -> dict:
    all_points, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=filename))]),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )
    total = len(all_points)
    enriched = sum(1 for p in all_points if p.payload.get("enriched"))
    return {"total": total, "enriched": enriched, "done": total > 0 and enriched == total}


def get_chunk_counts() -> dict:
    all_points, _ = client.scroll(
        collection_name=COLLECTION,
        limit=100000,
        with_payload=True,
        with_vectors=False,
    )
    counts: dict[str, int] = {}
    for p in all_points:
        source = p.payload.get("source", "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def delete_file(filename: str):
    client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(must=[FieldCondition(key="source", match=MatchValue(value=filename))]),
    )
