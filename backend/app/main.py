import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import CHUNK_OVERLAP_SEGMENTS, CHUNK_SIZE
from app.schemas import ChatRequest, ChatResponse, ClearRequest, VideoRequest, VideoResponse
from app.services import rag, transcript, vector_store
from app.services.memory import memory
from app.services.transcript import TranscriptError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("youtube-rag")

app = FastAPI(title="YouTube RAG Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Process a video: fetch transcript -> chunk -> embed -> store in Chroma
# ---------------------------------------------------------------------------
@app.post("/api/videos", response_model=VideoResponse)
def process_video(req: VideoRequest):
    video_id = transcript.extract_video_id(req.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Please enter a valid YouTube URL.")

    title = transcript.fetch_title(video_id)

    # Skip re-processing if this video is already indexed.
    try:
        if vector_store.video_is_indexed(video_id):
            return VideoResponse(
                video_id=video_id,
                title=title,
                cached=True,
                message="Video already processed. You can start asking questions.",
            )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        segments = transcript.fetch_segments(video_id)
    except TranscriptError as e:
        raise HTTPException(status_code=422, detail=str(e))

    chunks = transcript.build_chunks(segments, video_id, CHUNK_SIZE, CHUNK_OVERLAP_SEGMENTS)
    if not chunks:
        raise HTTPException(status_code=422, detail="Could not build any text chunks from the transcript.")

    try:
        vector_store.index_documents(chunks)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        logger.exception("Indexing failed for video %s", video_id)
        raise HTTPException(status_code=503, detail="Could not index the video right now. Please try again.")

    return VideoResponse(
        video_id=video_id,
        title=title,
        cached=False,
        message=f"Video processed successfully ({len(chunks)} chunks indexed).",
    )


# ---------------------------------------------------------------------------
# Ask a question (with conversation memory)
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        indexed = vector_store.video_is_indexed(req.video_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not indexed:
        raise HTTPException(status_code=404, detail="This video has not been processed yet.")

    session_key = f"{req.session_id}:{req.video_id}"

    try:
        return rag.answer_question(req.video_id, req.question.strip(), session_key)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        logger.exception("Chat failed for video %s", req.video_id)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Please try again.")


# ---------------------------------------------------------------------------
# Clear conversation memory for a session
# ---------------------------------------------------------------------------
@app.post("/api/chat/clear")
def clear_chat(req: ClearRequest):
    memory.clear(f"{req.session_id}:{req.video_id}")
    return {"status": "cleared"}


# ---------------------------------------------------------------------------
# Serve the frontend (mounted LAST so /api routes take priority)
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")