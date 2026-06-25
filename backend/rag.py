import ollama
import config as cfg
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchText

_client = QdrantClient(path=cfg.QDRANT_PATH)
COLLECTION = "knowledge"


def retrieve(query: str) -> str:
    embedding = ollama.embeddings(model=cfg.EMBEDDING_MODEL, prompt=query).embedding

    # Semantic search
    semantic_results = _client.search(
        collection_name=COLLECTION,
        query_vector=embedding,
        limit=cfg.TOP_K,
        with_payload=True,
    )

    # Keyword search
    try:
        keyword_results, _ = _client.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(must=[FieldCondition(key="text", match=MatchText(text=query))]),
            limit=cfg.TOP_K,
            with_payload=True,
            with_vectors=False,
        )
    except Exception:
        keyword_results = []

    # Hybrid merge: items in both lists get priority, then keyword-only, then semantic-only
    semantic_ids = {str(r.id) for r in semantic_results}
    keyword_ids = {str(r.id) for r in keyword_results}

    both = [r for r in semantic_results if str(r.id) in keyword_ids]
    only_keyword = [r for r in keyword_results if str(r.id) not in semantic_ids]
    only_semantic = [r for r in semantic_results if str(r.id) not in keyword_ids]

    merged = (both + only_keyword + only_semantic)[:cfg.TOP_K]

    if not merged:
        return ""

    parts = []
    for point in merged:
        source = point.payload.get("source", "unknown")
        page = point.payload.get("page", "?")
        text = point.payload.get("text", "")
        parts.append(f"[Source: {source}, Page {page}]\n{text}")

    return "\n\n---\n\n".join(parts)
