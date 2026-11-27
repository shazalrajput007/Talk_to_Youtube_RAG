import re
from urllib.parse import parse_qs, urlparse

import httpx
from langchain_core.documents import Document
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from app.config import TRANSCRIPT_LANGUAGES

VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")


class TranscriptError(Exception):
    """A user-facing error about the transcript (shown directly in the UI)."""


# ---------------------------------------------------------------------------
# 1. URL handling
# ---------------------------------------------------------------------------
def extract_video_id(url: str) -> str | None:
    """Supports watch?v=, youtu.be/, /embed/, /shorts/, /live/ and raw IDs."""
    url = url.strip()
    if VIDEO_ID_RE.match(url):
        return url

    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().replace("www.", "").replace("m.", "")
    candidate = None

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/", "/v/")):
            parts = parsed.path.split("/")
            candidate = parts[2] if len(parts) > 2 else None

    if candidate and VIDEO_ID_RE.match(candidate):
        return candidate
    return None


def fetch_title(video_id: str) -> str | None:
    """Gets the video title via YouTube's public oEmbed endpoint (best effort)."""
    try:
        response = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=5,
        )
        response.raise_for_status()
        return response.json().get("title")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 2. Transcript fetching
# ---------------------------------------------------------------------------
def clean_text(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", " ", text)  # remove [Music], [Applause], etc.
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def fetch_segments(video_id: str) -> list[dict]:
    """Returns a list of {text, start, duration} dictionaries."""
    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(video_id, languages=TRANSCRIPT_LANGUAGES)
        except NoTranscriptFound:
            # No English transcript: fall back to the first available language.
            transcripts = list(api.list(video_id))
            if not transcripts:
                raise TranscriptError("No transcript is available for this video.")
            fetched = transcripts[0].fetch()
    except TranscriptsDisabled:
        raise TranscriptError("Transcripts are disabled for this video.")
    except VideoUnavailable:
        raise TranscriptError("This video is unavailable (private, deleted, or region-locked).")
    except NoTranscriptFound:
        raise TranscriptError("No transcript is available for this video.")
    except CouldNotRetrieveTranscript:
        raise TranscriptError("Could not retrieve the transcript for this video.")

    segments = []
    for snippet in fetched:
        text = clean_text(snippet.text)
        if text:
            segments.append(
                {"text": text, "start": float(snippet.start), "duration": float(snippet.duration)}
            )

    if not segments:
        raise TranscriptError("The transcript is empty.")
    return segments


# ---------------------------------------------------------------------------
# 3. Chunking (groups segments into blocks and keeps timestamps)
# ---------------------------------------------------------------------------
def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def build_chunks(
    segments: list[dict],
    video_id: str,
    chunk_size: int = 800,
    overlap: int = 2,
) -> list[Document]:
    """
    Groups consecutive transcript segments into chunks of roughly `chunk_size`
    characters. Each chunk remembers its start/end time, so answers can point
    to the exact moment in the video.
    """
    chunks: list[Document] = []
    buffer: list[dict] = []
    buffer_len = 0

    def make_chunk(buf: list[dict]) -> Document:
        start = buf[0]["start"]
        end = buf[-1]["start"] + buf[-1]["duration"]
        return Document(
            page_content=" ".join(s["text"] for s in buf),
            metadata={
                "video_id": video_id,
                "start_time": start,
                "end_time": end,
                "timestamp": format_timestamp(start),
            },
        )

    for seg in segments:
        seg_len = len(seg["text"]) + 1

        if buffer and buffer_len + seg_len > chunk_size:
            chunks.append(make_chunk(buffer))
            # Keep the last few segments so context carries over between chunks.
            buffer = buffer[-overlap:] if overlap > 0 else []
            buffer_len = sum(len(s["text"]) + 1 for s in buffer)
            if buffer_len + seg_len > chunk_size:
                buffer, buffer_len = [], 0

        buffer.append(seg)
        buffer_len += seg_len

    if buffer:
        chunks.append(make_chunk(buffer))

    return chunks