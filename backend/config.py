from dotenv import load_dotenv
import os
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

KNOWLEDGE_FOLDER = "./knowledge"
DEFAULT_MODEL = "llama3.2"
EMBEDDING_MODEL = "nomic-embed-text"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
TOP_K = 3
MAX_HISTORY = 6
NUM_CTX = 1024
NUM_PREDICT = 2048

SECRET_KEY = "change-me-before-deploying"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
