from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import AIProvider, AIResponse


class ProviderUnavailable(RuntimeError):
    "Provider is unavailable or not configured."


class OpenAIAPIProvider(AIProvider):
    """Small dependency-free OpenAI-compatible chat adapter.

    The key is read at call time from ``OPENAI_API_KEY`` and is never stored in a
    PaperRule record. Structured responses are optional and remain untrusted until
    the caller validates them with a Pydantic model.
    """

    name = "openai_api"

    def __init__(self, *, model: str | None = None, base_url: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("PAPERRULE_OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self._api_key or os.environ.get("OPENAI_API_KEY"))

    def chat(self, messages: list[dict[str, str]], *, timeout: float = 30) -> AIResponse:
        key = self._api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured; draft remains local")
        payload = json.dumps({"model": self.model, "messages": messages, "temperature": 0.2}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload, method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable("OpenAI request failed; check connection and provider settings") from exc
        try:
            message = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable("OpenAI response did not contain a chat message") from exc
        return AIResponse(text=str(message), provider=self.name, model=self.model, structured=body)

