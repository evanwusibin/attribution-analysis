"""LLM 边界；领域层只依赖这个最小协议。"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    provider: str


class LLMPort(Protocol):
    def complete(self, messages: tuple[LLMMessage, ...]) -> LLMResponse:
        """Generate one response without exposing transport details."""
