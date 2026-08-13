from app.api.ai_agent import get_ai_agent_service
from app.core.config import settings
from app.main import app
from app.schemas.ai_agent import AIAgentChatResponse


class CapturingAgentService:
    def __init__(self):
        self.calls = []

    def chat(self, *, user_id, message):
        self.calls.append((user_id, message))
        return AIAgentChatResponse(
            answer="Resposta segura.",
            tools_used=["analyze_portfolio"],
        )


def test_ai_agent_is_disabled_by_default(client):
    response = client.post("/ai-agent/chat", json={"message": "Analise PETR4"})

    assert response.status_code == 503
    assert "não está disponível" in response.json()["detail"]


def test_ai_agent_endpoint_uses_authenticated_user(client, active_user):
    service = CapturingAgentService()
    app.dependency_overrides[get_ai_agent_service] = lambda: service
    try:
        response = client.post(
            "/ai-agent/chat", json={"message": "Analise minha carteira"}
        )
    finally:
        app.dependency_overrides.pop(get_ai_agent_service, None)

    assert response.status_code == 200
    assert service.calls == [(active_user.id, "Analise minha carteira")]
    assert response.json()["tools_used"] == ["analyze_portfolio"]


def test_ai_agent_request_rejects_user_id(client):
    service = CapturingAgentService()
    app.dependency_overrides[get_ai_agent_service] = lambda: service
    try:
        response = client.post(
            "/ai-agent/chat",
            json={"message": "Analise minha carteira", "user_id": "outro"},
        )
    finally:
        app.dependency_overrides.pop(get_ai_agent_service, None)

    assert response.status_code == 422
    assert service.calls == []


def test_ai_agent_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.post(
        "/ai-agent/chat", json={"message": "Analise PETR4"}
    )

    assert response.status_code == 401


def test_application_starts_and_health_works_without_openai_when_disabled(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "AI_AGENT_ENABLED", False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_enabled_without_api_key_is_controlled_and_other_routes_work(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "AI_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    agent_response = client.post("/ai-agent/chat", json={"message": "Analise PETR4"})
    health_response = client.get("/health")

    assert agent_response.status_code == 503
    assert agent_response.json()["detail"] == "Agente de IA não está configurado."
    assert health_response.status_code == 200
