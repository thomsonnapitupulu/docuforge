import time

import anthropic
import httpx
import pytest

from graph import nodes


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    """The retry decorator uses exponential backoff (up to 20s) — skip real
    sleeps so these tests run fast."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


def _request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _response(status_code: int):
    return httpx.Response(status_code, request=_request())


def _fake_llm_response(text: str):
    class FakeBlock:
        def __init__(self, text):
            self.text = text

    class FakeResponse:
        def __init__(self, text):
            self.content = [FakeBlock(text)]

    return FakeResponse(text)


def test_llm_retries_and_succeeds_after_transient_connection_errors(monkeypatch):
    calls = {"n": 0}

    def flaky_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise anthropic.APIConnectionError(request=_request())
        return _fake_llm_response("ok")

    monkeypatch.setattr(nodes._client.messages, "create", flaky_create)

    result = nodes._llm("prompt")
    assert result == "ok"
    assert calls["n"] == 3


def test_llm_does_not_retry_non_transient_errors(monkeypatch):
    calls = {"n": 0}

    def bad_request(*args, **kwargs):
        calls["n"] += 1
        raise anthropic.BadRequestError(
            "invalid request", response=_response(400), body=None
        )

    monkeypatch.setattr(nodes._client.messages, "create", bad_request)

    with pytest.raises(anthropic.BadRequestError):
        nodes._llm("prompt")
    assert calls["n"] == 1  # no retries — fails immediately


def test_llm_reraises_after_exhausting_retries(monkeypatch):
    calls = {"n": 0}

    def always_rate_limited(*args, **kwargs):
        calls["n"] += 1
        raise anthropic.RateLimitError(
            "rate limited", response=_response(429), body=None
        )

    monkeypatch.setattr(nodes._client.messages, "create", always_rate_limited)

    with pytest.raises(anthropic.RateLimitError):
        nodes._llm("prompt")
    assert calls["n"] == 4  # stop_after_attempt(4)
