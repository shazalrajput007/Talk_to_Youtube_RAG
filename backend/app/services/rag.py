from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.services.llm import get_llm
from app.services.memory import memory
from app.services.vector_store import search

NOT_FOUND_MSG = "I couldn't find that in the video."

# Step 1 (only when there is history): turn follow-up questions into standalone ones.
CONDENSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Given the chat history and a follow-up question about a video, rewrite the "
            "follow-up question so it can be understood on its own. Do NOT answer it. "
            "If it is already standalone, return it unchanged. Return only the question.",
        ),
        MessagesPlaceholder("chat_history"),
        ("human", "{question}"),
    ]
)

# Step 2: answer using only the retrieved transcript context.
QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an assistant that answers questions about a specific YouTube video.\n"
            "Rules:\n"
            "- Use ONLY the transcript excerpts below. Do not use outside knowledge.\n"
            f"- If the answer is not in the excerpts, reply exactly: \"{NOT_FOUND_MSG}\"\n"
            "- When you use information from an excerpt, cite its timestamp in square "
            "brackets, for example [02:15].\n"
            "- Be clear and concise.\n"
            "- Use the conversation history only to understand follow-up questions.\n\n"
            "Transcript excerpts:\n{context}",
        ),
        MessagesPlaceholder("chat_history"),
        ("human", "{question}"),
    ]
)


def _to_source(video_id: str, doc) -> dict:
    start = int(doc.metadata["start_time"])
    text = doc.page_content
    return {
        "timestamp": doc.metadata["timestamp"],
        "start_time": doc.metadata["start_time"],
        "url": f"https://www.youtube.com/watch?v={video_id}&t={start}s",
        "text": text[:200] + ("..." if len(text) > 200 else ""),
    }


def answer_question(video_id: str, question: str, session_key: str) -> dict:
    llm = get_llm()
    history = memory.get(session_key)

    # 1. Rewrite the question if this is a follow-up (uses memory).
    search_query = question
    if history:
        rewritten = (CONDENSE_PROMPT | llm | StrOutputParser()).invoke(
            {"chat_history": history, "question": question}
        )
        search_query = rewritten.strip() or question

    # 2. Retrieve relevant chunks from Chroma.
    docs = search(video_id, search_query)

    if not docs:
        answer = NOT_FOUND_MSG
        sources = []
    else:
        # 3. Generate the answer from context + history + question.
        context = "\n\n".join(f"[{d.metadata['timestamp']}] {d.page_content}" for d in docs)
        answer = (QA_PROMPT | llm | StrOutputParser()).invoke(
            {"context": context, "chat_history": history, "question": question}
        ).strip()

        sources = []
        if NOT_FOUND_MSG not in answer:
            sources = sorted(
                (_to_source(video_id, d) for d in docs), key=lambda s: s["start_time"]
            )

    # 4. Save this exchange to memory.
    memory.add_turn(session_key, question, answer)

    return {"answer": answer, "sources": sources}