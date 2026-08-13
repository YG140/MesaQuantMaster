from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AIToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class AIProviderResponse:
    output_text: str = ""
    tool_calls: list[AIToolCall] = field(default_factory=list)
    output_items: list[dict[str, Any]] = field(default_factory=list)


class AIProvider(Protocol):
    name: str

    def create_response(
        self,
        *,
        model: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> AIProviderResponse: ...
