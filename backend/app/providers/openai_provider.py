from __future__ import annotations

from typing import Any

from app.providers.ai_provider import AIToolCall, AIProviderResponse


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str, timeout_seconds: float):
        if not api_key:
            raise ValueError("OPENAI_API_KEY não configurada.")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    def create_response(
        self,
        *,
        model: str,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> AIProviderResponse:
        response = self._client.responses.create(
            model=model,
            instructions=instructions,
            input=input_items,
            tools=tools,
            max_output_tokens=max_output_tokens,
            store=False,
        )
        output_items = [item.model_dump(mode="json") for item in response.output]
        calls = [
            AIToolCall(item.call_id, item.name, item.arguments)
            for item in response.output
            if item.type == "function_call"
        ]
        return AIProviderResponse(
            output_text=response.output_text or "",
            tool_calls=calls,
            output_items=output_items,
        )
