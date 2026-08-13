from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.ai.exceptions import (
    AILimitExceededError,
    AIProviderUnavailableError,
    AIToolExecutionError,
    AIToolValidationError,
)
from app.ai.prompts import SYSTEM_PROMPT
from app.ai.tools import AIToolRegistry
from app.providers.ai_provider import AIProvider


@dataclass
class AIAgentResult:
    answer: str
    tools_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_quality_notes: list[str] = field(default_factory=list)


class AIAgent:
    def __init__(
        self,
        *,
        provider: AIProvider,
        registry: AIToolRegistry,
        model: str,
        max_iterations: int,
        max_tool_calls: int,
        max_output_tokens: int = 1200,
    ):
        self.provider = provider
        self.registry = registry
        self.model = model
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.max_output_tokens = max_output_tokens

    def run(self, message: str, user_id) -> AIAgentResult:
        input_items: list[dict[str, Any]] = [{"role": "user", "content": message}]
        tools_used: list[str] = []
        quality_notes: list[str] = []

        for _iteration in range(self.max_iterations):
            try:
                response = self.provider.create_response(
                    model=self.model,
                    instructions=SYSTEM_PROMPT,
                    input_items=input_items,
                    tools=self.registry.definitions,
                    max_output_tokens=self.max_output_tokens,
                )
            except Exception as exc:
                raise AIProviderUnavailableError(
                    "Provedor de IA temporariamente indisponível."
                ) from exc

            if not response.tool_calls:
                answer = response.output_text.strip()
                if not answer:
                    raise AIProviderUnavailableError(
                        "Resposta inválida do provedor de IA."
                    )
                return AIAgentResult(
                    answer=answer,
                    tools_used=tools_used,
                    data_quality_notes=_unique(quality_notes),
                )

            if len(tools_used) + len(response.tool_calls) > self.max_tool_calls:
                raise AILimitExceededError("Limite de ferramentas do agente excedido.")

            input_items.extend(response.output_items)
            for call in response.tool_calls:
                if not response.output_items:
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                    )
                try:
                    arguments = json.loads(call.arguments)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise AIToolValidationError(
                        "JSON de argumentos da ferramenta inválido."
                    ) from exc
                if not isinstance(arguments, dict):
                    raise AIToolValidationError(
                        "Argumentos da ferramenta devem ser um objeto."
                    )
                try:
                    result = self.registry.execute(call.name, arguments, user_id)
                except AIToolValidationError:
                    raise
                except Exception as exc:
                    raise AIToolExecutionError(
                        "Não foi possível consultar os dados solicitados."
                    ) from exc
                tools_used.append(call.name)
                quality_notes.extend(_quality_notes(result))
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(
                            result, ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                )

        raise AILimitExceededError("Limite de iterações do agente excedido.")


def _quality_notes(value: Any) -> list[str]:
    notes: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"missing_data", "warning_reasons", "anomaly_flags"}:
                if isinstance(item, list):
                    notes.extend(str(entry) for entry in item if entry)
            elif key == "confidence" and str(item).lower() in {
                "insufficient",
                "low",
                "baixa",
            }:
                notes.append(f"Confiança dos dados: {item}.")
            else:
                notes.extend(_quality_notes(item))
    elif isinstance(value, list):
        for item in value:
            notes.extend(_quality_notes(item))
    return notes


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
