"""Tests for the OpenRouter client: routing, retries and error handling."""

from __future__ import annotations

import json
from typing import Any

import pytest

from rates_analytics.config import Settings
from rates_analytics.llm.router import OpenRouterClient, OpenRouterError


class _FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    def json(self) -> dict[str, Any]:
        return self._body


def _ok_body(content: str = "hello") -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "model": "fake/model",
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }


def _settings(**env: str) -> Settings:
    return Settings.from_env({"OPENROUTER_API_KEY": "test-key", **env})


def test_settings_read_env_overrides() -> None:
    settings = Settings.from_env(
        {
            "OPENROUTER_API_KEY": "k",
            "FICC_LAB_RESEARCH_MODEL": "m/research",
            "FICC_LAB_CODE_MODEL": "m/code",
            "FICC_LAB_FAST_MODEL": "m/fast",
        }
    )
    assert settings.research_model == "m/research"
    assert settings.code_model == "m/code"
    assert settings.fast_model == "m/fast"
    assert settings.has_openrouter


def test_settings_defaults_without_key() -> None:
    settings = Settings.from_env({})
    assert not settings.has_openrouter
    assert settings.research_model  # a sensible default always exists


def test_client_requires_key() -> None:
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(Settings.from_env({}))


def test_model_for_routes_by_task() -> None:
    client = OpenRouterClient(_settings())
    assert client.model_for("research") == client.settings.research_model
    assert client.model_for("code") == client.settings.code_model
    assert client.model_for("fast") == client.settings.fast_model


def test_chat_returns_parsed_content(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any:
        captured.update(url=url, headers=headers, payload=json)
        return _FakeResponse(200, _ok_body("answer"))

    monkeypatch.setattr("rates_analytics.llm.router.requests.post", fake_post)
    client = OpenRouterClient(_settings())
    response = client.chat([{"role": "user", "content": "q"}], task="code")

    assert response.content == "answer"
    assert response.model == "fake/model"
    assert response.usage["completion_tokens"] == 2
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == client.settings.code_model


def test_chat_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_post(url: str, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any:
        calls.append(1)
        if len(calls) < 3:
            return _FakeResponse(429)
        return _FakeResponse(200, _ok_body("ok"))

    monkeypatch.setattr("rates_analytics.llm.router.requests.post", fake_post)
    monkeypatch.setattr("rates_analytics.llm.router.time.sleep", lambda _: None)
    client = OpenRouterClient(_settings())
    assert client.complete("q", task="fast") == "ok"
    assert len(calls) == 3


def test_chat_raises_immediately_on_non_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_post(url: str, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any:
        calls.append(1)
        return _FakeResponse(401, {"error": {"message": "bad key"}})

    monkeypatch.setattr("rates_analytics.llm.router.requests.post", fake_post)
    client = OpenRouterClient(_settings())
    with pytest.raises(OpenRouterError, match="HTTP 401"):
        client.complete("q")
    assert len(calls) == 1


def test_chat_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_post(url: str, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any:
        calls.append(1)
        return _FakeResponse(503)

    monkeypatch.setattr("rates_analytics.llm.router.requests.post", fake_post)
    monkeypatch.setattr("rates_analytics.llm.router.time.sleep", lambda _: None)
    client = OpenRouterClient(_settings())
    with pytest.raises(OpenRouterError, match="failed after retries"):
        client.complete("q", retries=3)
    assert len(calls) == 3
