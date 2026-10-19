"""Small dependency-free API protections for the local/prototype deployment."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock
from urllib.parse import urlsplit


def cors_origins() -> list[str]:
    configured = os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:3000,http://localhost:5173"
    )
    origins = []
    for value in configured.split(","):
        origin = value.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (origin == "*" or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
            raise ValueError("FRONTEND_ORIGINS must contain explicit HTTP(S) origins")
        origins.append(origin)
    if not origins:
        raise ValueError("FRONTEND_ORIGINS must contain at least one origin")
    return list(dict.fromkeys(origins))


def positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


class RateLimiter:
    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= window_seconds:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (now - events[0]) + 0.999))
            events.append(now)
            return None

