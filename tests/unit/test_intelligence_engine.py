from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.engines.intelligence_engine import (
    PortfolioBuilderEngine,
    PortfolioIntelligenceEngine,
)
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    PortfolioPolicyAllocationRead,
    PortfolioPolicyRead,
)
from app.schemas.portfolio import PortfolioPosition, PortfolioSummary


def make_policy(
    *,
    monthly_contribution: Decimal = Decimal("900"),
) -> PortfolioPolicyRead:
    now = datetime(2026, 7, 16, tzinfo=timezone.utc)
    return PortfolioPolicyRead(
        id=uuid4(),
        user_id=uuid4(),
        name="Minha estratégia",
        objective="crescimento patrimonial",
        risk_profile="moderado",
        investment_horizon="longo prazo",
        monthly_contribution=monthly_contribution,
        liquidity_need="média",
        income_need=False,
        emergency_reserve_months=6,
        maximum_weight_per_asset=Decimal("20"),
        maximum_weight_per_sector=Decimal("30"),
        maximum_weight_per_issuer=Decimal("30"),
        rebalance_tolerance=Decimal("2"),
        allocations=[
            PortfolioPolicyAllocationRead(
                id=uuid4(),
                asset_class="Ações",
                target_percentage=Decimal("60"),
                minimum_percentage=Decimal("50"),
                maximum_percentage=Decimal("70"),
                enabled=True,
            ),
            PortfolioPolicyAllocationRead(
                id=uuid4(),
                asset_class="Tesouro Direto",
                target_percentage=Decimal("40"),
                minimum_percentage=Decimal("30"),
                maximum_percentage=Decimal("50"),
                enabled=True,
            ),
        ],
        created_at=now,
        updated_at=now,
    )


def make_portfolio(
    positions: list[PortfolioPosition],
    *,
    market_data_status: str = "live",
    unpriced_symbols: list[str] | None = None,
) -> PortfolioSummary:
    return PortfolioSummary(
        total_invested=sum((item.invested_amount for item in positions), Decimal("0")),
        total_market_value=sum(
            (item.market_value or Decimal("0") for item in positions), Decimal("0")
        ),
        total_profit=sum(
            (item.unrealized_profit or Decimal("0") for item in positions), Decimal("0")
        ),
        profitability=Decimal("0"),
        allocation=[],
        valuation_basis="market_value",
        market_data_status=market_data_status,
        quote_updated_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
        unpriced_symbols=unpriced_symbols or [],
        positions=positions,
    )


def make_position(
    *,
    ticker: str = "PETR4",
    asset_type: str | None = "STOCK",
    invested_amount: Decimal = Decimal("600"),
    market_value: Decimal | None = Decimal("600"),
    allocation: Decimal | None = Decimal("60"),
    current_price: Decimal | None = Decimal("60"),
    quote_updated_at: datetime | None = datetime(2026, 7, 16, tzinfo=timezone.utc),
) -> PortfolioPosition:
    return PortfolioPosition(
        asset_id=uuid4(),
        ticker=ticker,
        asset_name=ticker,
        asset_type=asset_type,
        quantity=Decimal("10"),
        average_price=invested_amount / Decimal("10"),
        invested_amount=invested_amount,
        current_price=current_price,
        market_value=market_value,
        unrealized_profit=(
            (market_value - invested_amount) if market_value is not None else None
        ),
        unrealized_profit_percent=Decimal("0") if market_value is not None else None,
        allocation=allocation,
        weight=allocation,
        valuation_basis="market_value" if market_value is not None else None,
        valuation_status="live" if current_price is not None else "unpriced",
        quote_updated_at=quote_updated_at,
    )


def test_intelligence_without_policy_has_no_implicit_targets():
    result = PortfolioIntelligenceEngine.build(
        make_portfolio([make_position()]),
        policy=None,
    )

    assert result.policy is None
    assert result.recommendations == []
    assert result.rebalancing == []
    assert "Configure sua estratégia" in result.diagnosis.warnings[0]


def test_intelligence_calculates_distribution_by_class_from_policy():
    result = PortfolioIntelligenceEngine.build(
        make_portfolio(
            [
                make_position(
                    ticker="PETR4", asset_type="STOCK", market_value=Decimal("600")
                ),
                make_position(
                    ticker="TESOURO",
                    asset_type="TREASURY",
                    invested_amount=Decimal("400"),
                    market_value=Decimal("400"),
                    allocation=Decimal("40"),
                    current_price=Decimal("40"),
                ),
            ]
        ),
        policy=make_policy(),
    )

    by_class = {item.asset_class: item for item in result.diagnosis.class_allocations}
    assert by_class["Ações"].current_percentage == Decimal("60.00")
    assert by_class["Tesouro Direto"].current_percentage == Decimal("40.00")
    assert all(
        item.valuation_status == "Dados insuficientes"
        for item in result.recommendations
    )
    assert result.rebalancing[0].target_percentage in {Decimal("60"), Decimal("40")}


def test_intelligence_tracks_unclassified_assets():
    result = PortfolioIntelligenceEngine.build(
        make_portfolio([make_position(asset_type=None)]),
        policy=make_policy(),
    )

    assert "PETR4" in result.diagnosis.unclassified_assets
    assert any(
        item.asset_class == "Classe não identificada"
        for item in result.diagnosis.class_allocations
    )
    assert any(
        item.recommendation == "Revisar classificação"
        for item in result.recommendations
    )


def test_rebalance_next_contribution_is_proportional_to_deficit():
    policy = make_policy(monthly_contribution=Decimal("900"))
    result = PortfolioIntelligenceEngine.build(
        make_portfolio(
            [
                make_position(
                    ticker="TESOURO",
                    asset_type="TREASURY",
                    market_value=Decimal("9000"),
                    invested_amount=Decimal("9000"),
                    allocation=Decimal("100"),
                    current_price=Decimal("900"),
                ),
            ],
        ),
        policy=policy,
    )

    by_class = {item.asset_class: item for item in result.rebalancing}
    assert by_class["Ações"].suggested_contribution == Decimal("900.00")
    assert by_class["Tesouro Direto"].suggested_contribution == Decimal("0")


def test_portfolio_builder_uses_policy_percentages_not_equal_split():
    result = PortfolioBuilderEngine.build(
        BuildPortfolioRequest(
            available_amount=Decimal("10000"),
            objective="crescimento patrimonial",
            horizon="médio prazo",
            risk_profile="moderado",
            allowed_classes=["Ações", "Tesouro Direto"],
        ),
        policy=make_policy(),
    )

    by_class = {item.asset_class: item for item in result.class_allocations}
    assert by_class["Ações"].amount == Decimal("6000.00")
    assert by_class["Tesouro Direto"].amount == Decimal("4000.00")
    assert result.selections[0].data_status == "indisponível"
