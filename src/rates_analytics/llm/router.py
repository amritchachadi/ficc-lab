"""OpenRouter chat client with task-based model routing.

One API key, three model slots: ``research`` (long-context reasoning and
paper synthesis), ``code`` (generation and review) and ``fast`` (cheap
drafts and classification). Slot assignments live in the environment, so
swapping providers or model generations never touches call sites.

The client is deliberately thin: retries with exponential backoff on
transient failures, app attribution headers, and typed results. It knows
nothing about finance -- callers bring their own prompts.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import requests

from rates_analytics.config import Settings

Task = Literal["research", "code", "fast"]

#: HTTP statuses worth retrying: timeouts, rate limits and server errors.
_TRANSIENT_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})

Message = Mapping[str, str]


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter requests fail, after any retries."""


@dataclass(frozen=True)
class ChatResponse:
    """A single chat completion.

    Attributes
    ----------
    content : str
        Assistant message text.
    model : str
        Model that actually served the request, as reported by OpenRouter.
    usage : dict[str, int]
        Token accounting (``prompt_tokens``, ``completion_tokens``, ...).

    """

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _Attempt:
    """Outcome of one HTTP attempt, successful or not."""

    response: requests.Response | None = None
    exception: Exception | None = None

    @property
    def transient(self) -> bool:
        """Whether a retry could plausibly help."""
        if self.exception is not None:
            return True
        assert self.response is not None
        return self.response.status_code in _TRANSIENT_STATUSES


class OpenRouterClient:
    """Chat completions against the OpenRouter API.

    Parameters
    ----------
    settings : Settings
        Configuration including the API key and model slots.
    timeout : float
        Per-request timeout in seconds.

    Raises
    ------
    OpenRouterError
        At construction time, when no API key is configured.

    """

    def __init__(self, settings: Settings, timeout: float = 120.0) -> None:
        if not settings.has_openrouter:
            msg = (
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and "
                "add a key from https://openrouter.ai/keys"
            )
            raise OpenRouterError(msg)
        self.settings = settings
        self.timeout = timeout

    def model_for(self, task: Task) -> str:
        """Return the model assigned to ``task``."""
        return str(getattr(self.settings, f"{task}_model"))

    def chat(
        self,
        messages: Sequence[Message],
        task: Task = "research",
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        retries: int = 3,
    ) -> ChatResponse:
        """Send a chat completion request, retrying transient failures.

        Parameters
        ----------
        messages : Sequence[Message]
            OpenAI-style message dicts (``role``, ``content``).
        task : Task
            Routing slot used to pick the model unless ``model`` is given.
        model : str | None
            Explicit model override.
        temperature : float
            Sampling temperature.
        max_tokens : int | None
            Optional cap on completion tokens.
        retries : int
            Maximum number of attempts.

        Returns
        -------
        ChatResponse
            The completion.

        Raises
        ------
        OpenRouterError
            On a non-transient HTTP error, or when all attempts fail.

        """
        chosen = model if model is not None else self.model_for(task)
        payload: dict[str, Any] = {
            "model": chosen,
            "messages": [dict(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        last_failure: _Attempt | None = None
        for attempt_index in range(max(1, retries)):
            attempt = self._attempt_once(payload)
            if attempt.response is not None and attempt.response.status_code == 200:
                return self._parse(attempt.response, chosen)
            if not attempt.transient:
                raise self._error(attempt, fatal=True)
            last_failure = attempt
            time.sleep(2**attempt_index)
        assert last_failure is not None
        raise self._error(last_failure, fatal=False)

    def complete(self, prompt: str, task: Task = "research", **kwargs: Any) -> str:
        """Return the assistant text for a single user prompt."""
        response = self.chat([{"role": "user", "content": prompt}], task=task, **kwargs)
        return response.content

    def _attempt_once(self, payload: Mapping[str, Any]) -> _Attempt:
        """Perform one POST, converting network exceptions into outcomes."""
        url = f"{self.settings.openrouter_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_app_url,
            "X-Title": self.settings.openrouter_app_title,
        }
        try:
            return _Attempt(
                response=requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            )
        except requests.RequestException as exc:
            return _Attempt(exception=exc)

    @staticmethod
    def _parse(response: requests.Response, requested_model: str) -> ChatResponse:
        """Extract a typed completion from a 200 response body."""
        body: dict[str, Any] = response.json()
        try:
            content = body["choices"][0]["message"]["content"]
            model = body.get("model", requested_model)
            raw_usage = dict(body.get("usage", {}))
            usage = {k: int(v) for k, v in raw_usage.items() if isinstance(v, (int, float))}
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            msg = f"Malformed OpenRouter response: {exc}"
            raise OpenRouterError(msg) from exc
        return ChatResponse(content=str(content), model=str(model), usage=usage)

    @staticmethod
    def _error(attempt: _Attempt, *, fatal: bool) -> OpenRouterError:
        """Build the exception for a failed attempt."""
        if attempt.response is not None:
            detail = f"HTTP {attempt.response.status_code}: {attempt.response.text[:300]}"
        else:
            detail = str(attempt.exception)
        kind = "error" if fatal else "failed after retries"
        return OpenRouterError(f"OpenRouter request {kind} ({detail})")
