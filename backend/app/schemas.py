from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    url: str = Field(..., min_length=5, max_length=300)


class VideoResponse(BaseModel):
    video_id: str
    title: str | None = None
    cached: bool
    message: str


class ChatRequest(BaseModel):
    video_id: str
    session_id: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=1, max_length=1000)


class ClearRequest(BaseModel):
    video_id: str
    session_id: str = Field(..., min_length=1, max_length=100)


class Source(BaseModel):
    timestamp: str
    start_time: float
    url: str
    text: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]