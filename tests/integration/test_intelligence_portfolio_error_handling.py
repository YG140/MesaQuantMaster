from datetime import date

import pytest

from app.api.intelligence import get_portfolio_intelligence


def test_intelligence_portfolio_stays_200_for_a_valid_portfolio(
    client, asset_factory, operation_factory
):
    """Regressao (Correcao interface): carteira valida continua funcionando
    normalmente apos o tratamento do ValueError de dominio."""
    asset = asset_factory()
    operation_factory(asset, "BUY", date(2026, 7, 1), "10", "30")

    response = client.get("/intelligence/portfolio")

    assert response.status_code == 200
    assert response.json()["overview"]["investments_count"] == 1


def test_intelligence_portfolio_sell_above_accumulated_returns_422_never_500(
    client, asset_factory, operation_factory
):
    """Bug real identificado na auditoria: uma venda registrada acima da
    quantidade acumulada comprada levantava ValueError sem tratamento em
    toda a cadeia (PortfolioEngine.calculate_positions ->
    PortfolioService.calculate -> IntelligenceService.get_portfolio_intelligence
    -> router), virando 500 generico. Nunca deve virar 500 -- e uma
    inconsistencia de dados do usuario, nao um erro interno."""
    asset = asset_factory()
    operation_factory(asset, "BUY", date(2026, 7, 1), "10", "30")
    operation_factory(asset, "SELL", date(2026, 7, 2), "15", "35")

    response = client.get("/intelligence/portfolio")

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "venda" in detail.lower()
    # Nunca expor stack trace/detalhe interno na mensagem.
    assert "Traceback" not in detail
    assert "File \"" not in detail


def test_intelligence_diagnosis_sell_above_accumulated_also_returns_422(
    client, asset_factory, operation_factory
):
    """O endpoint /intelligence/diagnosis usa exatamente a mesma chamada de
    servico que /intelligence/portfolio -- precisa do mesmo tratamento,
    nunca 500."""
    asset = asset_factory()
    operation_factory(asset, "BUY", date(2026, 7, 1), "10", "30")
    operation_factory(asset, "SELL", date(2026, 7, 2), "15", "35")

    response = client.get("/intelligence/diagnosis")

    assert response.status_code == 422


def test_intelligence_portfolio_router_never_converts_unrelated_internal_errors_to_422(
    monkeypatch, db_session, active_user
):
    """Erros internos genuinos (nao ValueError de dominio) NUNCA podem ser
    indevidamente rotulados como 422 -- o except no router e escopado
    estritamente a ValueError, entao qualquer outra excecao (ex.: um bug
    real/erro de infraestrutura) deve continuar propagando sem virar uma
    resposta "erro do cliente" enganosa. Chamada direta da funcao do router
    (sem TestClient) para observar a excecao propagada sem interferencia do
    tratamento de erro padrao do FastAPI/Starlette."""
    from app.services.intelligence_service import PortfolioIntelligenceService

    def _raise_runtime_error(self, user_id):
        raise RuntimeError("falha interna genuina, nao relacionada a dominio")

    monkeypatch.setattr(
        PortfolioIntelligenceService,
        "get_portfolio_intelligence",
        _raise_runtime_error,
    )

    with pytest.raises(RuntimeError):
        get_portfolio_intelligence(db=db_session, current_user=active_user)
