from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class AIResponse:
    text: str
    provider: str
    model: str
    structured: dict | None = None

class AIProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], *, timeout: float = 30) -> AIResponse: ...

class FakeProvider(AIProvider):
    """Deterministic offline provider for demos and tests; never claims semantic validation."""
    name = "fake"
    def chat(self, messages: list[dict[str, str]], *, timeout: float = 30) -> AIResponse:
        latest = messages[-1]["content"] if messages else ""
        return AIResponse(
            text=f"已记录讨论意见（离线 FakeProvider）：{latest}",
            provider=self.name, model="deterministic",
        )

