from functools import lru_cache

from langchain_chroma import Chroma
from langchain_cohere import CohereEmbeddings
from langchain_core.documents import Document

from app.config import CHROMA_COLLECTION, CHROMA_DIR, COHERE_API_KEY, COHERE_EMBED_MODEL, RETRIEVAL_K


@lru_cache(maxsize=1)
def get_embeddings() -> CohereEmbeddings:
    if not COHERE_API_KEY:
        raise RuntimeError("COHERE_API_KEY is missing. Add it to backend/.env")
    return CohereEmbeddings(model=COHERE_EMBED_MODEL, cohere_api_key=COHERE_API_KEY)


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    return Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def video_is_indexed(video_id: str) -> bool:
    result = get_vector_store().get(where={"video_id": video_id}, limit=1)
    return len(result["ids"]) > 0


def index_documents(docs: list[Document], batch_size: int = 90) -> None:
    """Embeds and stores chunks in batches (Cohere accepts up to 96 texts per call)."""
    store = get_vector_store()
    for i in range(0, len(docs), batch_size):
        store.add_documents(docs[i : i + batch_size])


def search(video_id: str, query: str, k: int = RETRIEVAL_K) -> list[Document]:
    """Similarity search restricted to a single video."""
    return get_vector_store().similarity_search(query, k=k, filter={"video_id": video_id})