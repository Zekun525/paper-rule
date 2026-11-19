import json
import urllib.error
from types import SimpleNamespace

import pytest

from paperrule.domain.models import RuleRecord
from paperrule.governance.discussion import discuss_with_provider
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, OpenAIAPIProvider, ProviderUnavailable


@pytest.mark.parametrize("failure,code,status", [
    (urllib.error.HTTPError("https://synthetic.invalid", 429,
                           "synthetic-private-message", {}, None), "http_error", 429),
    (urllib.error.URLError("synthetic-private-message"), "network_error", None),
    (TimeoutError("synthetic-private-message"), "timeout", None),
    (urllib.error.URLError(TimeoutError("synthetic-private-message")), "timeout", None),
], ids=["http", "network", "timeout", "wrapped-timeout"])
def test_transport_failure_categories_do_not_expose_raw_errors(
    monkeypatch, failure, code, status,
):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(
        "urllib.request.build_opener", lambda *args: SimpleNamespace(open=fail),
    )
    provider = OpenAIAPIProvider(
        base_url="https://synthetic.invalid/v1", model="synthetic-model",
        api_key="synthetic-test-credential",
    )
    with pytest.raises(ProviderUnavailable) as error:
        provider.chat([])
    assert error.value.code == code
    assert error.value.http_status == status
    assert "synthetic-private-message" not in str(error.value)
    assert error.value.__suppress_context__


def test_only_allowlisted_failure_metadata_is_retained():
    error = ProviderUnavailable(
        "Synthetic failure", code="synthetic-private-message", http_status="private-status",
    )
    assert error.code == "unavailable"
    assert error.http_status is None


@pytest.mark.parametrize("failure_kind,expected", [
    ("transport", "provider_http_error_429"),
    ("schema", "response_schema_invalid"),
    ("binding", "response_binding_invalid"),
])
def test_failed_discussion_retains_draft_and_safe_diagnostic(
    tmp_path, monkeypatch, failure_kind, expected,
):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    gov = Governance(store)
    proposal = gov.propose(RuleRecord(
        id="G-SYNTHETIC-DIAGNOSTIC", short_title="Synthetic diagnostic",
        statement="Initial synthetic draft",
    ))
    initial_head = gov.git.head()

    def chat(self, messages, **kwargs):
        if failure_kind == "transport":
            raise ProviderUnavailable(
                "synthetic-private-message", code="http_error", http_status=429,
            )
        rule = proposal.after.model_dump(mode="json")
        rule["id"] = "G-SYNTHETIC-WRONG"
        return AIResponse(
            text="not-json" if failure_kind == "schema" else json.dumps({
                "reply": "Synthetic reply", "rule": rule,
            }),
            provider="openai_api", model="synthetic-model",
        )

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    updated = discuss_with_provider(gov, proposal.proposal_id, "Synthetic correction")
    assert updated.after == proposal.after
    assert updated.chat[-1].error == expected
    assert updated.chat[-1].user_text == "Synthetic correction"
    assert "synthetic-private-message" not in updated.model_dump_json()
    assert store.rules() == []
    assert store.decision_count(proposal.proposal_id) == 0
    assert gov.git.head() == initial_head
