"""FastAPI chat and demo endpoints. Run with python main.py."""

import asyncio
import json
import sqlite3
import time
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from agent import chat, stream_chat
from leads import DemoRequest, save_demo
from memory import forget, load_history, save_history
from router import Intent, classify_intent

app = FastAPI(title="a31-assistance")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["POST"], allow_headers=["Content-Type"],
)
sessions: dict[UUID, float] = {}
model_lock = asyncio.Lock()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    page_path: str = Field(default="", max_length=300, pattern=r"^(?:/[A-Za-z0-9/_-]*)?$")


class ChatResponse(BaseModel):
    answer: str
    session_id: UUID
    intent: Intent


def get_session(request: ChatRequest) -> tuple[UUID, list[dict]]:
    for key, updated in list(sessions.items()):
        if time.monotonic() - updated > 3600:
            forget(key)
            del sessions[key]
    session_id = request.session_id or uuid4()
    if request.session_id and session_id not in sessions:
        raise HTTPException(404, "Session expired. Start a new conversation.")
    if session_id not in sessions and len(sessions) >= 100:
        raise HTTPException(429, "Too many conversations. Please retry later.")
    sessions[session_id] = time.monotonic()
    return session_id, load_history(session_id)


def remember(session_id, history, message, answer):
    save_history(session_id, history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ])
    sessions[session_id] = time.monotonic()


def reject_if_busy():
    if model_lock.locked():
        raise HTTPException(429, "The model is busy. Please retry shortly.")


@app.post("/chat", response_model=ChatResponse)
async def ask(request: ChatRequest):
    reject_if_busy()
    async with model_lock:
        session_id, history = get_session(request)
        intent = classify_intent(request.message, history, request.page_path)
        try:
            answer = await chat(request.message, history, request.page_path)
        except (httpx.HTTPError, ValueError, asyncio.TimeoutError):
            raise HTTPException(503, "The model or website search is unavailable. Please retry.") from None
        remember(session_id, history, request.message, answer)
        return ChatResponse(answer=answer, session_id=session_id, intent=intent)


@app.post("/chat/stream")
async def ask_stream(request: ChatRequest):
    reject_if_busy()
    session_id, history = get_session(request)
    intent = classify_intent(request.message, history, request.page_path)

    def event(kind, **payload):
        return json.dumps({"type": kind, **payload}) + "\n"

    async def events():
        if model_lock.locked():
            yield event("error", message="The model is busy. Please retry shortly.")
            return
        async with model_lock:
            yield event("session", session_id=str(session_id), intent=intent)
            chunks = []
            try:
                async for delta in stream_chat(request.message, history, request.page_path):
                    if delta:
                        chunks.append(delta)
                        yield event("delta", text=delta)
                remember(session_id, history, request.message, "".join(chunks))
                yield event("done")
            except (httpx.HTTPError, ValueError, asyncio.TimeoutError):
                yield event("error", message="The answer could not finish. Please retry.")

    return StreamingResponse(
        events(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.post("/leads")
async def submit_demo(lead: DemoRequest):
    try:
        return await asyncio.to_thread(save_demo, lead)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    except (sqlite3.Error, OSError):
        raise HTTPException(503, "Could not save the request. Please retry.") from None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
