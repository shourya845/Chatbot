"""Content-free request tracing for chat, search and model performance."""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator
from uuid import uuid4


logger = logging.getLogger("a31.telemetry")
_current_trace: ContextVar["RequestTrace | None"] = ContextVar(
    "a31_request_trace", default=None
)


def _milliseconds(seconds: float) -> float:
    return round(seconds * 1000, 2)


@dataclass
class RequestTrace:
    """Mutable metrics for one API request; never stores message or lead content."""

    endpoint: str
    privacy_mode: str = "cloud_allowed"
    request_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: float = field(default_factory=time.perf_counter)
    intent: str = "unknown"
    selected_provider: str | None = None
    selected_model: str | None = None
    provider_attempts: list[dict[str, str]] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    search_calls: int = 0
    search_duration_ms: float = 0.0
    retrieval_sources: list[str] = field(default_factory=list)
    evidence_status: str | None = None
    evidence_result_count: int = 0
    model_load_duration_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    first_status_ms: float | None = None
    ttft_ms: float | None = None
    generation_started_at: float | None = None
    generation_duration_ms: float | None = None
    total_duration_ms: float | None = None
    error_category: str | None = None
    completed: bool = False

    @property
    def cache_status(self) -> str:
        if self.cache_hits and self.cache_misses:
            return "mixed"
        if self.cache_hits:
            return "hit"
        if self.cache_misses:
            return "miss"
        return "not_used"

    def as_log_record(self) -> dict[str, Any]:
        """Return the allowlisted fields emitted to structured logs."""
        return {
            "event": "a31_request",
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "intent": self.intent,
            "provider": self.selected_provider,
            "model": self.selected_model,
            "privacy_mode": self.privacy_mode,
            "provider_attempts": self.provider_attempts,
            "cache_status": self.cache_status,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "search_calls": self.search_calls,
            "search_duration_ms": round(self.search_duration_ms, 2),
            "retrieval_sources": self.retrieval_sources,
            "evidence_status": self.evidence_status,
            "evidence_result_count": self.evidence_result_count,
            "model_load_duration_ms": self.model_load_duration_ms,
            "first_status_ms": self.first_status_ms,
            "ttft_ms": self.ttft_ms,
            "generation_duration_ms": self.generation_duration_ms,
            "total_duration_ms": self.total_duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "error_category": self.error_category,
        }


def new_trace(endpoint: str, privacy_mode: str = "cloud_allowed") -> RequestTrace:
    return RequestTrace(endpoint=endpoint, privacy_mode=privacy_mode)


@contextmanager
def trace_context(trace: RequestTrace) -> Iterator[RequestTrace]:
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(token)


def current_trace() -> RequestTrace | None:
    return _current_trace.get()


def set_intent(intent: str) -> None:
    trace = current_trace()
    if trace:
        trace.intent = intent


def record_status_event() -> None:
    trace = current_trace()
    if trace and trace.first_status_ms is None:
        trace.first_status_ms = _milliseconds(time.perf_counter() - trace.started_at)


def record_first_token() -> None:
    trace = current_trace()
    if trace and trace.ttft_ms is None:
        trace.ttft_ms = _milliseconds(time.perf_counter() - trace.started_at)


def record_generation_start() -> None:
    trace = current_trace()
    if trace and trace.generation_started_at is None:
        trace.generation_started_at = time.perf_counter()


def record_generation_end() -> None:
    trace = current_trace()
    if trace and trace.generation_started_at is not None:
        trace.generation_duration_ms = _milliseconds(
            time.perf_counter() - trace.generation_started_at
        )


def record_provider_attempt(
    provider: str, model: str, outcome: str, error_category: str | None = None
) -> None:
    trace = current_trace()
    if not trace:
        return
    attempt = {"provider": provider, "model": model, "outcome": outcome}
    if error_category:
        attempt["error_category"] = error_category
    trace.provider_attempts.append(attempt)
    if outcome == "success":
        trace.selected_provider = provider
        trace.selected_model = model


def record_search(cache_hit: bool | None, started_at: float, source: str) -> None:
    trace = current_trace()
    if not trace:
        return
    trace.search_calls += 1
    if cache_hit is not None:
        trace.cache_hits += int(cache_hit)
        trace.cache_misses += int(not cache_hit)
    if source not in trace.retrieval_sources:
        trace.retrieval_sources.append(source)
    trace.search_duration_ms += _milliseconds(time.perf_counter() - started_at)


def record_model_metadata(message: Any) -> None:
    """Collect provider-reported timing and token counts when supplied."""
    trace = current_trace()
    if not trace:
        return
    usage = getattr(message, "usage_metadata", None) or {}
    metadata = getattr(message, "response_metadata", None) or {}
    input_tokens = usage.get("input_tokens", metadata.get("prompt_eval_count"))
    output_tokens = usage.get("output_tokens", metadata.get("eval_count"))
    if isinstance(input_tokens, int):
        trace.input_tokens = (trace.input_tokens or 0) + input_tokens
    if isinstance(output_tokens, int):
        trace.output_tokens = (trace.output_tokens or 0) + output_tokens
    load_duration = metadata.get("load_duration")
    if isinstance(load_duration, (int, float)):
        # Ollama reports this duration in nanoseconds.
        load_ms = round(load_duration / 1_000_000, 2)
        trace.model_load_duration_ms = round(
            (trace.model_load_duration_ms or 0.0) + load_ms, 2
        )


def record_evidence(status: str, result_count: int) -> None:
    trace = current_trace()
    if trace:
        trace.evidence_status = status
        trace.evidence_result_count = result_count


def record_error(category: str) -> None:
    trace = current_trace()
    if trace:
        trace.error_category = category


def finish_trace(trace: RequestTrace) -> dict[str, Any]:
    if not trace.completed:
        trace.total_duration_ms = _milliseconds(time.perf_counter() - trace.started_at)
        trace.completed = True
        logger.info(json.dumps(trace.as_log_record(), separators=(",", ":")))
    return trace.as_log_record()
