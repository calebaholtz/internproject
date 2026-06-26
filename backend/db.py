import os
import config as cfg
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

os.makedirs(cfg.QDRANT_PATH, exist_ok=True)

client = QdrantClient(path=cfg.QDRANT_PATH)
COLLECTION = "knowledge"
VECTOR_SIZE = 768


def ensure_collection():
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name="text",
            field_schema="text",
        )


ensure_collection()
