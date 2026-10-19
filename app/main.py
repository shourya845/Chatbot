"""FastAPI endpoints for chat streaming and demo requests."""

import asyncio
import json
import sqlite3
import time
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from .agent import chat, stream_chat
from .leads import DemoRequest, save_demo
from .memory import forget, load_history, save_history
from .privacy import get_privacy_mode
from .security import RateLimiter, cors_origins, positive_int
from .telemetry import (
    finish_trace,
    new_trace,
    record_error,
    record_first_token,
    record_status_event,
    set_intent,
    trace_context,
)

app = FastAPI(title="a31-assistance")
app.add_middleware(CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=["POST"], allow_headers=["Content-Type"])
sessions: dict[UUID, float] = {}
model_lock = asyncio.Lock()
rate_limiter = RateLimiter()
SESSION_TTL_SECONDS = 60 * 60
MAX_SESSIONS = 100
MODEL_UNAVAILABLE = "The model or website search is unavailable. Please retry."
MODEL_BUSY = "The model is busy. Please retry shortly."


def enforce_rate_limit(request: Request, endpoint: str) -> None:
    client = request.client.host if request.client else "unknown"
    if endpoint == "/leads":
        limit = positive_int("LEAD_RATE_LIMIT", 5)
        window = positive_int("LEAD_RATE_WINDOW_SECONDS", 3600)
    else:
        limit = positive_int("CHAT_RATE_LIMIT", 30)
        window = positive_int("CHAT_RATE_WINDOW_SECONDS", 60)
    retry_after = rate_limiter.check(f"{endpoint}:{client}", limit, window)
    if retry_after is not None:
        record_error("rate_limited")
        raise HTTPException(429, "Too many requests. Please retry later.",
                            headers={"Retry-After": str(retry_after)})


def reject_if_model_busy() -> None:
    if model_lock.locked():
        record_error("model_busy")
        raise HTTPException(429, MODEL_BUSY)


def ndjson_event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}) + "\n"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None
    page_path: str = Field(default="", max_length=300, pattern=r"^(?:/[A-Za-z0-9/_-]*)?$")


class ChatResponse(BaseModel):
    answer: str
    session_id: UUID


def get_session(request: ChatRequest) -> tuple[UUID, list[dict]]:
    for key, updated in list(sessions.items()):
        if time.monotonic() - updated > SESSION_TTL_SECONDS:
            forget(key)
            del sessions[key]
    session_id = request.session_id or uuid4()
    if request.session_id and session_id not in sessions:
        raise HTTPException(404, "Session expired. Start a new conversation.")
    if session_id not in sessions and len(sessions) >= MAX_SESSIONS:
        raise HTTPException(429, "Too many conversations. Please retry later.")
    sessions[session_id] = time.monotonic()
    return session_id, load_history(session_id)


def remember(session_id: UUID, history: list[dict], message: str, answer: str) -> None:
    save_history(session_id, history + [
        {"role": "user", "content": message}, {"role": "assistant", "content": answer},
    ])
    sessions[session_id] = time.monotonic()


@app.post("/chat", response_model=ChatResponse)
async def ask(payload: ChatRequest, response: Response, http_request: Request):
    trace = new_trace("/chat", get_privacy_mode().value)
    response.headers["X-Request-ID"] = trace.request_id
    with trace_context(trace):
        try:
            enforce_rate_limit(http_request, "/chat")
            reject_if_model_busy()
            async with model_lock:
                session_id, history = get_session(payload)
                timeout = positive_int("CHAT_REQUEST_TIMEOUT_SECONDS", 180)
                answer = await asyncio.wait_for(
                    chat(payload.message, history, payload.page_path), timeout=timeout
                )
                remember(session_id, history, payload.message, answer)
                return ChatResponse(answer=answer, session_id=session_id)
        except HTTPException as error:
            if trace.error_category is None:
                record_error(f"http_{error.status_code}")
            raise
        except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as error:
            record_error(type(error).__name__)
            raise HTTPException(503, MODEL_UNAVAILABLE) from None
        finally:
            finish_trace(trace)


@app.post("/chat/stream")
async def ask_stream(payload: ChatRequest, http_request: Request):
    trace = new_trace("/chat/stream", get_privacy_mode().value)
    with trace_context(trace):
        try:
            enforce_rate_limit(http_request, "/chat/stream")
            reject_if_model_busy()
            session_id, history = get_session(payload)
        except HTTPException as error:
            if trace.error_category is None:
                record_error(f"http_{error.status_code}")
            finish_trace(trace)
            raise

    async def events():
        with trace_context(trace):
            try:
                # Another request can acquire the lock after the preflight check.
                if model_lock.locked():
                    record_error("model_busy")
                    yield ndjson_event("error", message=MODEL_BUSY)
                    return
                async with model_lock:
                    yield ndjson_event("session", session_id=str(session_id))
                    record_status_event()
                    yield ndjson_event("status", status="thinking", request_id=trace.request_id)
                    answer = []
                    try:
                        timeout = positive_int("CHAT_REQUEST_TIMEOUT_SECONDS", 180)
                        deadline = time.monotonic() + timeout
                        stream = stream_chat(
                            payload.message, history, payload.page_path
                        ).__aiter__()
                        while True:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise asyncio.TimeoutError
                            try:
                                delta = await asyncio.wait_for(
                                    stream.__anext__(), timeout=remaining
                                )
                            except StopAsyncIteration:
                                break
                            if not delta:
                                continue
                            record_first_token()
                            answer.append(delta)
                            yield ndjson_event("delta", text=delta)
                        remember(session_id, history, payload.message, "".join(answer))
                        yield ndjson_event("done")
                    except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as error:
                        # A partial or interrupted answer is not saved to conversation memory.
                        record_error(type(error).__name__)
                        yield ndjson_event(
                            "error", message="The answer could not finish. Please retry."
                        )
            except asyncio.CancelledError:
                record_error("client_cancelled")
                raise
            finally:
                finish_trace(trace)

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no",
                                      "X-Request-ID": trace.request_id})


@app.post("/leads")
async def submit_demo(lead: DemoRequest, response: Response, http_request: Request):
    trace = new_trace("/leads", get_privacy_mode().value)
    response.headers["X-Request-ID"] = trace.request_id
    with trace_context(trace):
        set_intent("demo")
        try:
            enforce_rate_limit(http_request, "/leads")
            timeout = positive_int("LEAD_REQUEST_TIMEOUT_SECONDS", 10)
            return await asyncio.wait_for(asyncio.to_thread(save_demo, lead), timeout=timeout)
        except ValueError as exc:
            record_error("duplicate_request_conflict")
            raise HTTPException(409, str(exc))
        except (sqlite3.Error, OSError, asyncio.TimeoutError) as error:
            record_error(type(error).__name__)
            raise HTTPException(503, "Could not save the request. Please retry.") from None
        finally:
            finish_trace(trace)
