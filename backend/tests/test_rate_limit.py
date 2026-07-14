import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.rate_limit import RateLimiter


def test_allows_requests_under_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.check("client-a")  # must not raise


def test_blocks_requests_over_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        limiter.check("client-a")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("client-a")
    assert exc_info.value.status_code == 429


def test_limits_are_tracked_independently_per_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.check("client-a")
    limiter.check("client-b")  # different key — must not raise


def test_old_hits_fall_out_of_the_sliding_window(monkeypatch):
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake_now["t"])

    limiter.check("client-a")
    with pytest.raises(HTTPException):
        limiter.check("client-a")

    fake_now["t"] += 11  # past the 10s window
    limiter.check("client-a")  # must not raise — old hit expired


def test_generate_endpoint_returns_429_once_rate_limit_exceeded(monkeypatch):
    from api import main as main_module

    monkeypatch.setattr(main_module, "generate_limiter", RateLimiter(max_requests=2, window_seconds=60))
    monkeypatch.setattr(main_module.vector_store, "collection_stats", lambda: {"child_chunks": 5, "parent_chunks": 1})

    async def noop_generation(job_id, artifact_type):
        pass  # avoid a real LangGraph/Anthropic call — this test is about rate limiting, not generation

    monkeypatch.setattr(main_module, "_run_generation", noop_generation)

    client = TestClient(main_module.app)
    payload = {"artifact_type": "BRD"}

    for _ in range(2):
        resp = client.post("/generate", json=payload)
        assert resp.status_code == 200

    resp = client.post("/generate", json=payload)
    assert resp.status_code == 429


def test_ingest_endpoint_returns_429_once_rate_limit_exceeded(monkeypatch):
    from api import main as main_module

    monkeypatch.setattr(main_module, "ingest_limiter", RateLimiter(max_requests=1, window_seconds=60))

    client = TestClient(main_module.app)
    files = {"file": ("doc.txt", b"hello world reference content", "text/plain")}

    resp = client.post("/ingest", files=files)
    assert resp.status_code == 200

    resp = client.post("/ingest", files=files)
    assert resp.status_code == 429
