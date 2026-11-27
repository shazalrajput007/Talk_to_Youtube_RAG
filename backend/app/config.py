import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# --- API keys & models ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
COHERE_EMBED_MODEL = os.getenv("COHERE_EMBED_MODEL", "embed-multilingual-light-v3.0")

# --- Vector store ---
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "youtube_transcripts")

# --- Transcript & chunking ---
TRANSCRIPT_LANGUAGES = ["en", "en-US", "en-GB"]  # preferred languages, in order
CHUNK_SIZE = 800                                 # characters per chunk (approx.)
CHUNK_OVERLAP_SEGMENTS = 2                       # transcript segments shared by neighbouring chunks

# --- Retrieval & memory ---
RETRIEVAL_K = 4          # number of chunks retrieved per question
MAX_HISTORY_TURNS = 6    # number of user/assistant exchanges kept per session