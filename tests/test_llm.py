from __future__ import annotations

from types import SimpleNamespace

import pytest

from reaper.llm import GrokDraftingClient


def test_grok_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="XAI_API_KEY"):
        GrokDraftingClient()


def test_grok_client_returns_typed_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(
                content=(
                    '{"subject":"APR review","body":"Hello",'
                    '"factual_basis":["APR 26.99%"],"missing_fields":[]}'
                )
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr("reaper.llm.OpenAI", FakeOpenAI)
    client = GrokDraftingClient(api_key="key", model="grok-test")
    draft = client.draft(
        objective="Request APR review",
        facts=["APR 26.99%"],
        constraints=["Do not authorize account closure"],
    )
    assert draft.subject == "APR review"
    assert captured["model"] == "grok-test"
    assert captured["client"]["base_url"] == "https://api.x.ai/v1"
