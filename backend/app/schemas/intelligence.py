from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


INVESTMENT_CLASSES = [
    "Caixa",
    "Reserva de emergência",
    "Tesouro Direto",
    "Renda fixa bancária",
    "Crédito privado",
    "Fundos de investimento",
    "Ações",
    "FIIs",
    "ETFs",
    "BDRs",
    "Ativos internacionais",
    "Criptomoedas",
    "Outros",
]


class IndicatorStatus(BaseModel):
    name: str
    status: str
    value: str | Decimal | None = None
    explanation: str


class Recommendation(BaseModel):
    asset_id: UUID | None = None
    symbol: str
    name: str
    asset_class: str
    recommendation: str
    valuation_status: str
    confidence: str
    current_weight: Decimal | None = None
    target_weight: Decimal | None = None
    current_value: Decimal | None = None
    suggested_value: Decimal | None = None
    positive_reasons: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    indicators: list[IndicatorStatus] = Field(default_factory=list)
    generated_at: datetime
    data_updated_at: datetime | None = None


class ClassAllocationDiagnosis(BaseModel):
    asset_class: str
    current_value: Decimal | None = None
    current_percentage: Decimal | None = None
    target_percentage: Decimal | None = None
    minimum_percentage: Decimal | None = None
    maximum_percentage: Decimal | None = None
    difference_percentage: Decimal | None = None
    status: str


class PortfolioDiagnosis(BaseModel):
    portfolio_score: Decimal | None = None
    risk_level: str
    diversification_score: Decimal | None = None
    concentration_score: Decimal | None = None
    liquidity_score: Decimal | None = None
    income_score: Decimal | None = None
    data_quality: str
    warnings: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    class_allocations: list[ClassAllocationDiagnosis] = Field(default_factory=list)
    unclassified_assets: list[str] = Field(default_factory=list)
    calculated_at: datetime


class AllocationSuggestion(BaseModel):
    asset_class: str
    current_percentage: Decimal
    target_percentage: Decimal
    difference_percentage: Decimal
    current_value: Decimal
    target_value: Decimal
    suggested_contribution: Decimal
    missing_value: Decimal = Decimal("0")
    excess_value: Decimal = Decimal("0")
    status: str = "Dados insuficientes"
    explanation: str


class PortfolioOverview(BaseModel):
    current_equity: Decimal | None = None
    total_invested: Decimal | None = None
    profit_loss: Decimal | None = None
    profitability: Decimal | None = None
    received_income: Decimal | None = None
    investments_count: int
    fixed_income_percentage: Decimal | None = None
    variable_income_percentage: Decimal | None = None
    portfolio_classification: str
    risk_level: str
    data_quality: str
    last_updated_at: datetime | None = None
    market_data_status: str
    insufficient_data_message: str = "Dados insuficientes para calcular."


class BuildPortfolioRequest(BaseModel):
    available_amount: Decimal = Field(gt=0)
    objective: str
    horizon: str
    risk_profile: str
    needs_emergency_reserve: bool = True
    emergency_months: int = 6
    monthly_contribution: Decimal = Decimal("0")
    needs_income: bool = False
    needs_liquidity: bool = True
    volatility_tolerance: str = "moderada"
    max_percentage_per_asset: Decimal = Decimal("20")
    max_percentage_per_class: Decimal = Decimal("40")
    max_percentage_per_sector: Decimal = Decimal("30")
    allowed_classes: list[str] = Field(default_factory=list)
    prohibited_classes: list[str] = Field(default_factory=list)
    max_assets: int = Field(default=10, ge=1, le=50)
    net_monthly_income: Decimal | None = Field(default=None, ge=0)
    income_type: str | None = None
    essential_monthly_expenses: Decimal | None = Field(default=None, ge=0)
    total_monthly_expenses: Decimal | None = Field(default=None, ge=0)
    emergency_reserve: Decimal | None = Field(default=None, ge=0)
    high_cost_debt: Decimal | None = Field(default=None, ge=0)
    dependents: int | None = Field(default=None, ge=0)
    current_financial_assets: Decimal | None = Field(default=None, ge=0)
    annual_contribution_growth: Decimal | None = None
    desired_monthly_income: Decimal | None = Field(default=None, ge=0)
    preserve_principal: bool = True
    projection_years: int = Field(default=20, ge=1, le=60)
    inflation_rate: Decimal | None = Field(default=None, ge=-20, le=100)
    annual_cost_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    withdrawal_rate: Decimal = Field(default=Decimal("4"), gt=0, le=100)
    safety_margin: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    reinvest_income: bool = True

    @model_validator(mode="after")
    def validate_builder_limits(self):
        percentage_limits = (
            self.max_percentage_per_asset,
            self.max_percentage_per_class,
            self.max_percentage_per_sector,
        )
        if any(value <= 0 or value > 100 for value in percentage_limits):
            raise ValueError("Limites percentuais devem estar entre 0 e 100.")
        overlap = set(self.allowed_classes) & set(self.prohibited_classes)
        if overlap:
            raise ValueError(
                "Uma classe não pode ser permitida e proibida ao mesmo tempo."
            )
        if self.monthly_contribution < 0:
            raise ValueError("Aporte mensal não pode ser negativo.")
        return self


class BuildPortfolioClassAllocation(BaseModel):
    asset_class: str
    percentage: Decimal
    amount: Decimal
    explanation: str
    # Aditivos, opcionais: só preenchidos quando a carteira foi montada sob
    # uma PortfolioPolicy confirmada (ver SmartPortfolioEngine.build/
    # PortfolioStrategy) -- None no modo legado (sem policy), nunca quebra
    # clientes existentes que não conhecem esses campos.
    target_percentage: Decimal | None = None
    minimum_percentage: Decimal | None = None
    maximum_percentage: Decimal | None = None
    gap_percentage: Decimal | None = None
    gap_reason: str | None = None


class BuildPortfolioSelection(BaseModel):
    asset_class: str
    message: str
    data_status: str


class BuildPortfolioIndicator(BaseModel):
    key: str
    label: str
    value: Decimal | str | None = None
    source: str
    source_type: str
    reference_date: datetime | None = None
    valid_until: datetime | None = None
    freshness_status: str
    unit: str | None = None
    status: str = "available"
    unavailable_reason: str | None = None


class BuildPortfolioAsset(BaseModel):
    symbol: str
    name: str | None = None
    asset_class: str
    sector: str | None = None
    issuer: str | None = None
    recommended_percentage: Decimal
    recommended_amount: Decimal
    score: Decimal
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    indicators_used: list[BuildPortfolioIndicator] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    confidence: str
    reference_price: Decimal | None = None
    executable_quantity: Decimal | None = None
    executable_amount: Decimal = Decimal("0")
    effective_percentage: Decimal = Decimal("0")
    target_gap: Decimal = Decimal("0")
    execution_impediments: list[str] = Field(default_factory=list)
    trading_symbol: str | None = None
    economic_identity: str | None = None
    market_segment: str | None = None
    quantity_step: Decimal | None = None
    # Contexto vindo exclusivamente das operações autenticadas do usuário.
    existing_quantity: Decimal = Decimal("0")
    existing_value: Decimal = Decimal("0")
    post_purchase_weight: Decimal | None = None
    allocation_note: str | None = None


class ExistingHoldingAssessment(BaseModel):
    symbol: str
    quantity: Decimal
    estimated_value: Decimal
    estimated_weight: Decimal
    valuation_basis: str
    recommendation: str
    confidence: str
    overall_score: Decimal | None = None
    rationale: str
    alerts: list[str] = Field(default_factory=list)


class BuildPortfolioExclusion(BaseModel):
    symbol: str
    asset_class: str
    reasons: list[str]


class BuildPortfolioPreflight(BaseModel):
    """Diagnóstico estrutural do universo/elegibilidade (P2), aditivo e compatível."""

    universe_total: int = 0
    universe_considered: int = 0
    universe_truncated: bool = False
    batch_size: int = 0
    batch_count: int = 0
    snapshots_received: int = 0
    assets_with_valid_price: int = 0
    required_complete_count: int = 0
    confidence_high_count: int = 0
    confidence_medium_count: int = 0
    confidence_low_count: int = 0
    confidence_insufficient_count: int = 0
    eligible_count: int = 0
    excluded_count: int = 0
    provider_error_count: int = 0
    class_counts: dict[str, int] = Field(default_factory=dict)
    exclusion_reason_counts: dict[str, int] = Field(default_factory=dict)
    # Aditivo (P4): agregado a partir de resolution_summary (P4) /
    # resolution_attempts (P3) de cada candidato — diagnóstico de fallback,
    # nunca gate de elegibilidade.
    provider_failure_reason_counts: dict[str, int] = Field(default_factory=dict)
    fallback_success_count: int = 0
    unresolved_after_fallback_count: int = 0
    stale_assets_count: int = 0


class FinancialDiagnosis(BaseModel):
    phase: str
    estimated_monthly_capacity: Decimal | None = None
    reserve_months_covered: Decimal | None = None
    reserve_target: Decimal | None = None
    debt_alerts: list[str] = Field(default_factory=list)
    liquidity_assessment: str
    missing_data: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    confidence: str


class ContributionPriority(BaseModel):
    priority: int
    symbol: str
    asset_class: str
    suggested_amount: Decimal
    reason: str
    uses_income: bool = False


class ProjectionScenario(BaseModel):
    name: str
    annual_appreciation_rate: Decimal
    annual_income_rate: Decimal
    total_contributed: Decimal
    projected_wealth: Decimal
    estimated_appreciation: Decimal
    estimated_income: Decimal
    estimated_periodic_income: Decimal
    real_projected_wealth: Decimal | None = None
    projected_without_reinvestment: Decimal


class FinancialFreedomGoal(BaseModel):
    desired_monthly_income: Decimal | None = None
    required_wealth: Decimal | None = None
    current_wealth: Decimal | None = None
    gap: Decimal | None = None
    achieved_percentage: Decimal | None = None
    estimated_years: int | None = None
    withdrawal_rate: Decimal
    safety_margin: Decimal
    risks: list[str] = Field(default_factory=list)
    improvement_actions: list[str] = Field(default_factory=list)
    confidence: str


class BuildPortfolioResponse(BaseModel):
    class_allocations: list[BuildPortfolioClassAllocation]
    selections: list[BuildPortfolioSelection]
    assets: list[BuildPortfolioAsset] = Field(default_factory=list)
    exclusions: list[BuildPortfolioExclusion] = Field(default_factory=list)
    total_allocated_percentage: Decimal = Decimal("0")
    total_allocated_amount: Decimal = Decimal("0")
    unallocated_amount: Decimal = Decimal("0")
    confidence: str = "insufficient"
    status: str = "unavailable"
    missing_data: list[str] = Field(default_factory=list)
    preflight: BuildPortfolioPreflight = Field(default_factory=BuildPortfolioPreflight)
    strategy_summary: str = ""
    # Aditivos: transparência sobre a origem do envelope estratégico
    # efetivamente usado (ver SmartPortfolioEngine.build/PortfolioStrategy).
    # "request_legacy" preserva o comportamento anterior a esta mudança
    # (nenhuma PortfolioPolicy encontrada para o usuário) -- nunca quebra
    # clientes que ainda não conhecem "investor_profile_policy".
    policy_source: str = "request_legacy"
    policy_id: UUID | None = None
    existing_portfolio_value: Decimal = Decimal("0")
    existing_positions_count: int = 0
    existing_holdings_assessments: list[ExistingHoldingAssessment] = Field(default_factory=list)
    holdings_warnings: list[str] = Field(default_factory=list)
    diagnosis: FinancialDiagnosis
    contribution_plan: list[ContributionPriority] = Field(default_factory=list)
    projections: list[ProjectionScenario] = Field(default_factory=list)
    freedom_goal: FinancialFreedomGoal
    disclaimer: str = (
        "Simulação educacional, não constitui ordem de compra e não garante retorno."
    )
    generated_at: datetime


class Opportunity(BaseModel):
    asset_class: str
    classification: str
    indicators: list[IndicatorStatus] = Field(default_factory=list)
    highlight_reason: str
    risks: list[str] = Field(default_factory=list)
    confidence: str
    updated_at: datetime | None = None


class PortfolioPolicyAllocationBase(BaseModel):
    asset_class: str
    target_percentage: Decimal
    minimum_percentage: Decimal
    maximum_percentage: Decimal
    enabled: bool = True


class PortfolioPolicyAllocationRead(PortfolioPolicyAllocationBase):
    id: UUID | None = None


class PortfolioPolicyUpsert(BaseModel):
    name: str = "Minha estratégia"
    objective: str
    risk_profile: str
    investment_horizon: str
    monthly_contribution: Decimal = Decimal("0")
    liquidity_need: str
    income_need: bool = False
    emergency_reserve_months: int = 6
    maximum_weight_per_asset: Decimal = Decimal("20")
    maximum_weight_per_sector: Decimal = Decimal("30")
    maximum_weight_per_issuer: Decimal = Decimal("30")
    rebalance_tolerance: Decimal = Decimal("5")
    allocations: list[PortfolioPolicyAllocationBase]

    @model_validator(mode="after")
    def validate_policy(self):
        if self.monthly_contribution < 0:
            raise ValueError("Aporte mensal não pode ser negativo.")
        if self.emergency_reserve_months < 0:
            raise ValueError("Meses de reserva não pode ser negativo.")

        enabled = [item for item in self.allocations if item.enabled]
        if not enabled:
            raise ValueError("Habilite pelo menos uma classe.")

        classes = [item.asset_class for item in self.allocations]
        if len(classes) != len(set(classes)):
            raise ValueError("Classes duplicadas não são permitidas.")

        total = sum((item.target_percentage for item in enabled), Decimal("0"))
        if total != Decimal("100"):
            raise ValueError("A soma das classes habilitadas deve ser exatamente 100%.")

        for item in self.allocations:
            values = [
                item.target_percentage,
                item.minimum_percentage,
                item.maximum_percentage,
            ]
            if any(value < 0 for value in values):
                raise ValueError("Percentuais não podem ser negativos.")
            if item.minimum_percentage > item.target_percentage:
                raise ValueError("O mínimo não pode ser maior que o alvo.")
            if item.target_percentage > item.maximum_percentage:
                raise ValueError("O alvo não pode ser maior que o máximo.")
        return self


class PortfolioPolicyRead(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    objective: str
    risk_profile: str
    investment_horizon: str
    monthly_contribution: Decimal
    liquidity_need: str
    income_need: bool
    emergency_reserve_months: int
    maximum_weight_per_asset: Decimal
    maximum_weight_per_sector: Decimal
    maximum_weight_per_issuer: Decimal
    rebalance_tolerance: Decimal
    allocations: list[PortfolioPolicyAllocationRead]
    created_at: datetime
    updated_at: datetime


class PortfolioIntelligenceResponse(BaseModel):
    overview: PortfolioOverview
    diagnosis: PortfolioDiagnosis
    recommendations: list[Recommendation]
    rebalancing: list[AllocationSuggestion]
    opportunities: list[Opportunity]
    policy: PortfolioPolicyRead | None = None
    available_indicators: dict[str, list[str]]
    unavailable_indicators: dict[str, list[str]]
    generated_at: datetime
