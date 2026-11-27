import threading

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config import MAX_HISTORY_TURNS


class ChatMemory:
    """
    Keeps the last N exchanges per session in memory.
    Keys look like "<session_id>:<video_id>", so each video has its own conversation.
    For production, replace the dict with Redis or a database.
    """

    def __init__(self, max_turns: int):
        self.max_messages = max_turns * 2
        self._sessions: dict[str, list[BaseMessage]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> list[BaseMessage]:
        with self._lock:
            return list(self._sessions.get(key, []))

    def add_turn(self, key: str, question: str, answer: str) -> None:
        with self._lock:
            messages = self._sessions.setdefault(key, [])
            messages.append(HumanMessage(content=question))
            messages.append(AIMessage(content=answer))
            if len(messages) > self.max_messages:
                del messages[: -self.max_messages]

    def clear(self, key: str) -> None:
        with self._lock:
            self._sessions.pop(key, None)


memory = ChatMemory(MAX_HISTORY_TURNS)