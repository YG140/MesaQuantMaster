from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OnboardingStatus(StrEnum):
    NEEDS_ONBOARDING = "needs_onboarding"
    IN_PROGRESS = "in_progress"
    PENDING_CONFIRMATION = "pending_confirmation"
    COMPLETE = "complete"
    NEEDS_REVIEW = "needs_review"


PrimaryObjective = Literal[
    "crescimento_patrimonial",
    "renda_passiva",
    "aposentadoria",
    "preservacao",
    "compra_futura",
    "formacao_patrimonio",
]
HorizonBucket = Literal["menos_1_ano", "1_a_3_anos", "3_a_5_anos", "5_a_10_anos", "mais_10_anos"]
ContributionStability = Literal["fixo", "variavel"]
IncomeRange = Literal["ate_3000", "3000_a_8000", "8000_a_20000", "acima_20000"]
NetWorthRange = Literal["ate_10000", "10000_a_50000", "50000_a_200000", "acima_200000"]
LiquidityNeed = Literal["baixa", "moderada", "alta"]
IncomeNeed = Literal["nenhuma", "complemento", "renda_passiva", "dependencia"]
RiskScenarioChoice = Literal["venderia_tudo", "venderia_parte", "manteria", "compraria_mais"]
KnowledgeChoice = Literal["a", "b", "c", "d"]


class ObjectivesAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_objective: PrimaryObjective | None = None
    secondary_objectives: list[PrimaryObjective] = Field(default_factory=list, max_length=5)


class HorizonAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horizon: HorizonBucket | None = None


class ContributionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_contribution: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000"))
    monthly_contribution: Decimal | None = Field(default=None, ge=0, le=Decimal("1000000000"))
    contribution_stability: ContributionStability | None = None


class FinancialSituationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    income_range: IncomeRange | None = None
    investable_net_worth_range: NetWorthRange | None = None
    emergency_reserve_months: int | None = Field(default=None, ge=0, le=60)
    has_relevant_debt: bool | None = None
    dependents: int | None = Field(default=None, ge=0, le=20)


class LiquidityAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    liquidity_need: LiquidityNeed | None = None


class IncomeNeedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    income_need: IncomeNeed | None = None


class KnowledgeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, KnowledgeChoice] = Field(default_factory=dict, max_length=10)


class RiskToleranceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenarios: dict[str, RiskScenarioChoice] = Field(default_factory=dict, max_length=10)


class RestrictionsAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    restricted_classes: list[str] = Field(default_factory=list, max_length=13)
    allowed_classes: list[str] = Field(default_factory=list, max_length=13)


class InvestorProfileAnswers(BaseModel):
    """Payload de PUT /investor-profile/answers. Cada seção é opcional para
    permitir salvar progresso parcial; evaluate() exige o conjunto mínimo.
    `extra="forbid"` em todos os níveis bloqueia mass assignment."""

    model_config = ConfigDict(extra="forbid")

    objectives: ObjectivesAnswer | None = None
    horizon: HorizonAnswer | None = None
    contribution: ContributionAnswer | None = None
    financial_situation: FinancialSituationAnswer | None = None
    liquidity: LiquidityAnswer | None = None
    income_need: IncomeNeedAnswer | None = None
    knowledge: KnowledgeAnswer | None = None
    risk_tolerance: RiskToleranceAnswer | None = None
    restrictions: RestrictionsAnswer | None = None


class DimensionExplanationRead(BaseModel):
    dimension: str
    rule: str
    result: int | str
    message: str


class InvestorProfileDimensions(BaseModel):
    risk_tolerance_score: int
    risk_capacity_score: int
    horizon_score: int
    liquidity_need_score: int
    income_need_score: int
    knowledge_score: int
    emergency_reserve_adequacy_score: int
    overall_classification: str


class PolicyPreviewAllocation(BaseModel):
    asset_class: str
    target_percentage: Decimal
    minimum_percentage: Decimal
    maximum_percentage: Decimal
    enabled: bool = True


class PolicyPreview(BaseModel):
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
    allocations: list[PolicyPreviewAllocation]


class InvestorProfileEvaluationResponse(BaseModel):
    """Resposta de POST /investor-profile/evaluate — preview, nada persistido
    em PortfolioPolicy ainda."""

    dimensions: InvestorProfileDimensions
    explanations: list[DimensionExplanationRead]
    policy_preview: PolicyPreview
    missing_sections: list[str] = Field(default_factory=list)


class InvestorProfileStatusResponse(BaseModel):
    status: OnboardingStatus
    version: int
    last_reviewed_at: datetime | None = None
    confirmed_at: datetime | None = None
    updated_at: datetime | None = None


class InvestorProfileRead(BaseModel):
    id: UUID
    user_id: UUID
    status: OnboardingStatus
    version: int

    primary_objective: str | None = None
    secondary_objectives: list[str] | None = None
    horizon: str | None = None
    initial_contribution: Decimal | None = None
    monthly_contribution: Decimal | None = None
    contribution_stability: str | None = None
    income_range: str | None = None
    investable_net_worth_range: str | None = None
    emergency_reserve_months: int | None = None
    has_relevant_debt: bool | None = None
    dependents: int | None = None
    liquidity_need: str | None = None
    income_need: str | None = None
    allowed_classes: list[str] | None = None
    restricted_classes: list[str] | None = None

    dimensions: InvestorProfileDimensions | None = None
    explanations: list[DimensionExplanationRead] | None = None
    policy_preview: PolicyPreview | None = None

    evaluated_at: datetime | None = None
    confirmed_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
