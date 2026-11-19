from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import AIProvider, AIResponse


class ProviderUnavailable(RuntimeError):
    "Provider is unavailable or not configured."

    def __init__(self, message: str, *, code: str = "unavailable",
                 http_status: int | None = None):
        super().__init__(message)
        allowed = {
            "unavailable", "not_configured", "http_error", "timeout", "network_error",
            "invalid_json", "invalid_encoding", "response_too_large",
            "response_shape_invalid", "response_content_invalid", "incomplete_response",
        }
        self.code = code if code in allowed else "unavailable"
        self.http_status = (
            http_status if type(http_status) is int and http_status in range(100, 600) else None
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a Bearer credential to a redirect destination.
        return None


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
            raise ProviderUnavailable(
                "OPENAI_API_KEY is not configured; draft remains local", code="not_configured",
            )
        # Model names are opaque: compatible gateways may serve other vendors.
        # Do not force generation parameters that some models do not support.
        payload = json.dumps({"model": self.model, "messages": messages}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload, method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Some compatible gateways reject urllib's default agent.
                "User-Agent": "Mozilla/5.0",
            },
        )
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ProviderUnavailable(
                        "AI response exceeded the size limit", code="response_too_large",
                    )
                body = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderUnavailable(
                "AI service returned an HTTP error", code="http_error", http_status=exc.code,
            ) from None
        except TimeoutError:
            raise ProviderUnavailable("AI request timed out", code="timeout") from None
        except urllib.error.URLError as exc:
            code = "timeout" if isinstance(exc.reason, TimeoutError) else "network_error"
            raise ProviderUnavailable(
                "AI request failed; check connection and provider settings", code=code,
            ) from None
        except OSError:
            raise ProviderUnavailable("AI connection failed", code="network_error") from None
        except UnicodeError:
            raise ProviderUnavailable(
                "AI response encoding was invalid", code="invalid_encoding",
            ) from None
        except ValueError:
            raise ProviderUnavailable(
                "AI response was not valid JSON", code="invalid_json",
            ) from None
        try:
            choice = body["choices"][0]
            message = choice["message"]
            content = message["content"]
            valid = (
                isinstance(content, str) and bool(content.strip())
                and choice.get("finish_reason") in {None, "stop"}
                and not message.get("tool_calls") and not message.get("refusal")
                and not body.get("error")
            )
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable(
                "AI response did not contain a chat message", code="response_shape_invalid",
            ) from None
        if not valid:
            code = (
                "incomplete_response" if choice.get("finish_reason") not in {None, "stop"}
                else "response_content_invalid"
            )
            raise ProviderUnavailable(
                "AI response did not contain completed nonempty text", code=code,
            )
        return AIResponse(text=content, provider=self.name, model=self.model, structured=body)

