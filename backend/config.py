from dotenv import load_dotenv
import os
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

KNOWLEDGE_FOLDER = "./knowledge"
QDRANT_PATH = "./qdrant_db"
DEFAULT_MODEL = "gemma4"
ENRICH_MODEL = "gemma4"
ENRICH_WORKERS = 4
EMBEDDING_MODEL = "nomic-embed-text"
CHUNK_SIZE = 256
CHUNK_OVERLAP = 40
TOP_K = 20
MAX_HISTORY = 6
NUM_CTX = 4096
NUM_PREDICT = 2048

SECRET_KEY = "change-me-before-deploying"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
