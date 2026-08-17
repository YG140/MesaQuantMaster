from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.agent import AIAgent
from app.ai.exceptions import AIAgentError
from app.ai.tools import AIToolRegistry
from app.api.deps import get_current_active_user
from app.api.intelligence import get_service as get_intelligence_service
from app.api.investor_profile import get_service as get_investor_profile_service
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.providers.openai_provider import OpenAIProvider
from app.schemas.ai_agent import AIAgentChatRequest, AIAgentChatResponse
from app.services.ai_agent_service import AIAgentService

router = APIRouter(prefix="/ai-agent", tags=["Agente de IA"])


def get_ai_agent_service(db: Session = Depends(get_db)) -> AIAgentService:
    if not settings.AI_AGENT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agente de IA não está disponível.",
        )
    try:
        provider = OpenAIProvider(
            api_key=settings.OPENAI_API_KEY,
            timeout_seconds=settings.AI_AGENT_TIMEOUT_SECONDS,
        )
    except (ImportError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agente de IA não está configurado.",
        ) from exc

    intelligence = get_intelligence_service(db)
    registry = AIToolRegistry(
        market_intelligence=intelligence.market_intelligence_service,
        portfolio_intelligence=intelligence,
        investor_profile=get_investor_profile_service(db),
        max_compare_assets=settings.AI_AGENT_MAX_COMPARE_ASSETS,
    )
    agent = AIAgent(
        provider=provider,
        registry=registry,
        model=settings.OPENAI_MODEL,
        max_iterations=settings.AI_AGENT_MAX_ITERATIONS,
        max_tool_calls=settings.AI_AGENT_MAX_TOOL_CALLS,
        max_output_tokens=settings.AI_AGENT_MAX_OUTPUT_TOKENS,
    )
    return AIAgentService(
        agent=agent,
        max_message_length=settings.AI_AGENT_MAX_MESSAGE_LENGTH,
    )


@router.post("/chat", response_model=AIAgentChatResponse)
def chat(
    data: AIAgentChatRequest,
    current_user: User = Depends(get_current_active_user),
    service: AIAgentService = Depends(get_ai_agent_service),
):
    try:
        return service.chat(user_id=current_user.id, message=data.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AIAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
