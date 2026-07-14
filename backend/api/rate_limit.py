"""
In-memory sliding-window rate limiter, keyed by client IP.

Single-instance only — no shared backend (Redis, etc.) is used, since this
app runs as one process (see CLAUDE.md's architecture principle: fewest
moving parts, no extra service unless the scale genuinely demands it). If
DocuForge ever runs multiple backend workers/instances behind a load
balancer, this stops being accurate per-client and a shared store would be
needed instead.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Raises HTTPException(429) if `key` has exceeded the limit within
        the current window; otherwise records this call and allows it."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            raise HTTPException(
                429,
                f"Rate limit exceeded: max {self.max_requests} requests per "
                f"{int(self.window_seconds)}s. Please slow down.",
            )
        hits.append(now)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"
