import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from paperrule.providers import OpenAIAPIProvider, ProviderUnavailable


def transport(monkeypatch, body):
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = body if isinstance(body, bytes) else json.dumps(body).encode()
    opener = MagicMock()
    opener.open.return_value = response
    factory = MagicMock(return_value=opener)
    monkeypatch.setattr("urllib.request.build_opener", factory)
    return factory, opener, response


def provider():
    return OpenAIAPIProvider(
        base_url="https://synthetic.invalid/v1", model="deepseek-synthetic",
        api_key="synthetic-test-credential",
    )


def test_compatible_gateway_preserves_model_and_avoids_forced_parameters(monkeypatch):
    factory, opener, response = transport(monkeypatch, {
        "choices": [{"finish_reason": "stop", "message": {"content": "Synthetic reply"}}],
    })
    result = provider().chat([{"role": "user", "content": "Synthetic evidence"}], timeout=7)
    assert result.text == "Synthetic reply"
    assert result.model == "deepseek-synthetic"
    request = opener.open.call_args.args[0]
    assert request.full_url == "https://synthetic.invalid/v1/chat/completions"
    assert request.get_header("User-agent") == "Mozilla/5.0"
    assert request.get_header("Authorization") == "Bearer synthetic-test-credential"
    assert json.loads(request.data) == {
        "model": "deepseek-synthetic",
        "messages": [{"role": "user", "content": "Synthetic evidence"}],
    }
    assert opener.open.call_args.kwargs["timeout"] == 7
    response.read.assert_called_once_with(2_000_001)
    redirect_handler = factory.call_args.args[0]
    assert redirect_handler.redirect_request(
        request, None, 302, "redirect", {}, "https://other.invalid",
    ) is None


@pytest.mark.parametrize("message,finish_reason", [
    ({"content": None}, "stop"),
    ({"content": "  "}, "stop"),
    ({"content": ["not a text message"]}, "stop"),
    ({"content": "Truncated text"}, "length"),
    ({"content": "Text", "tool_calls": [{"id": "synthetic"}]}, "stop"),
    ({"content": "Text", "refusal": "Synthetic refusal"}, "stop"),
])
def test_nontext_or_incomplete_replies_are_unavailable(monkeypatch, message, finish_reason):
    transport(monkeypatch, {"choices": [{"message": message, "finish_reason": finish_reason}]})
    with pytest.raises(ProviderUnavailable):
        provider().chat([])


@pytest.mark.parametrize(
    "body", [b"not-json", b"{}", b"x" * 2_000_001],
    ids=["malformed-json", "missing-chat-message", "oversized-response"],
)
def test_malformed_and_oversized_replies_are_unavailable(monkeypatch, body):
    transport(monkeypatch, body)
    with pytest.raises(ProviderUnavailable):
        provider().chat([])


def test_raw_gateway_errors_do_not_enter_public_error_message(monkeypatch):
    _, opener, _ = transport(monkeypatch, {})
    opener.open.side_effect = urllib.error.URLError("synthetic-test-credential")
    with pytest.raises(ProviderUnavailable) as error:
        provider().chat([])
    assert "synthetic-test-credential" not in str(error.value)
    assert error.value.__suppress_context__
