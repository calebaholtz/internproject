import os
import uuid
import pypdf
import ollama
import config as cfg
from qdrantclient.models import PointStruct, Filter, FieldCondition, MatchValue
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
    points = []
    chunk_index = 0

    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        chunks = _chunk_text(text)
        for chunk in chunks:
            embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=chunk).embedding
            points.append(PointStruct(
                id=_make_id(filename, chunk_index),
                vector=embedding,
                payload={
                    "source": filename,
                    "page": page_num,
                    "text": chunk,
                    "enriched": False,
                },
            ))
            chunk_index += 1

    if points:
        client.upsert(collection_name=COLLECTION, points=points)


def enrich_file(filename: str, model: str):
    results, _ = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=filename))]),
        limit=10000,
        with_payload=True,
        with_vectors=False,
    )

    for point in results:
        if point.payload.get("enriched"):
            continue
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
            continue


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
