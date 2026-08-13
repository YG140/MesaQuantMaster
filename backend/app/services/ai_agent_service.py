from __future__ import annotations

import logging
import time
from uuid import uuid4

from app.ai.agent import AIAgent
from app.schemas.ai_agent import AIAgentChatResponse

logger = logging.getLogger(__name__)


class AIAgentService:
    def __init__(self, *, agent: AIAgent, max_message_length: int):
        self.agent = agent
        self.max_message_length = max_message_length

    def chat(self, *, user_id, message: str) -> AIAgentChatResponse:
        normalized = message.strip()
        if not normalized:
            raise ValueError("A mensagem não pode estar vazia.")
        if len(normalized) > self.max_message_length:
            raise ValueError("A mensagem excede o limite permitido.")

        request_id = str(uuid4())
        started = time.monotonic()
        status_name = "success"
        error_type = None
        tools_used: list[str] = []
        try:
            result = self.agent.run(normalized, user_id)
            tools_used = result.tools_used
            return AIAgentChatResponse(
                answer=result.answer,
                tools_used=result.tools_used,
                warnings=result.warnings,
                data_quality_notes=result.data_quality_notes,
            )
        except Exception as exc:
            status_name = "error"
            error_type = type(exc).__name__
            raise
        finally:
            # Nunca registrar mensagem, prompt, payload financeiro, token ou chave.
            logger.info(
                "ai_agent request_id=%s duration_ms=%d provider=%s "
                "model=%s tools=%s tool_calls=%d status=%s error_type=%s",
                request_id,
                round((time.monotonic() - started) * 1000),
                self.agent.provider.name,
                self.agent.model,
                tools_used,
                len(tools_used),
                status_name,
                error_type,
            )
