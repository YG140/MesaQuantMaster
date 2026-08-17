from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.engines.investor_profile_engine import InvestorProfileEngine
from app.models.investor_profile import InvestorProfile
from app.repositories.investor_profile_repository import InvestorProfileRepository
from app.schemas.intelligence import PortfolioPolicyUpsert
from app.schemas.investor_profile import (
    ContributionAnswer,
    DimensionExplanationRead,
    FinancialSituationAnswer,
    HorizonAnswer,
    HorizonBucket,
    IncomeNeedAnswer,
    InvestorProfileAnswers,
    InvestorProfileDimensions,
    InvestorProfileEvaluationResponse,
    InvestorProfileRead,
    InvestorProfileStatusResponse,
    LiquidityAnswer,
    LiquidityNeed,
    ObjectivesAnswer,
    OnboardingStatus,
    PolicyPreview,
    PrimaryObjective,
    RestrictionsAnswer,
)
from app.services.intelligence_service import PortfolioIntelligenceService

# Estados a partir dos quais confirm() é permitido: uma avaliação precisa
# existir (pending_confirmation) ou o usuário pediu para revisar um perfil
# já concluído (needs_review). Nunca confirmar a partir de needs_onboarding
# ou in_progress — isso pularia a etapa de revisão obrigatória (seção 15).
CONFIRMABLE_STATUSES = {
    OnboardingStatus.PENDING_CONFIRMATION.value,
    OnboardingStatus.NEEDS_REVIEW.value,
}

# Mapeamento best-effort de horizonte textual legado (PortfolioPolicy) para
# o bucket canônico do onboarding — usado apenas para pré-preencher, nunca
# para inferir dimensões psicológicas/de conhecimento.
LEGACY_HORIZON_ALIASES: dict[str, HorizonBucket] = {
    "curto prazo": "menos_1_ano",
    "médio prazo": "3_a_5_anos",
    "medio prazo": "3_a_5_anos",
    "longo prazo": "mais_10_anos",
}
LEGACY_LIQUIDITY_ALIASES: dict[str, LiquidityNeed] = {
    "baixa": "baixa",
    "média": "moderada",
    "media": "moderada",
    "alta": "alta",
}
LEGACY_OBJECTIVE_ALIASES: dict[str, PrimaryObjective] = {
    "crescimento patrimonial": "crescimento_patrimonial",
    "renda passiva": "renda_passiva",
    "aposentadoria": "aposentadoria",
    "preservação de capital": "preservacao",
    "preservacao de capital": "preservacao",
}


class InvestorProfileService:
    def __init__(
        self,
        repository: InvestorProfileRepository,
        policy_service: PortfolioIntelligenceService,
    ):
        self.repository = repository
        self.policy_service = policy_service

    # -- leitura -----------------------------------------------------------

    def get_status(self, user_id: UUID) -> InvestorProfileStatusResponse:
        profile = self.repository.get_by_user(user_id)
        if profile is None:
            return InvestorProfileStatusResponse(
                status=OnboardingStatus.NEEDS_ONBOARDING, version=1
            )
        return InvestorProfileStatusResponse(
            status=OnboardingStatus(profile.status),
            version=profile.version,
            last_reviewed_at=_aware(profile.last_reviewed_at),
            confirmed_at=_aware(profile.confirmed_at),
            updated_at=_aware(profile.updated_at),
        )

    def get_profile(self, user_id: UUID) -> InvestorProfileRead:
        profile = self._get_or_create(user_id)
        return self._to_schema(profile)

    # -- escrita -------------------------------------------------------------

    def save_answers(
        self, user_id: UUID, answers: InvestorProfileAnswers
    ) -> InvestorProfileRead:
        profile = self._get_or_create(user_id)
        current = InvestorProfileAnswers.model_validate(profile.answers or {})
        merged = _merge_answers(current, answers)
        self._apply_answers_to_columns(profile, merged)
        profile.answers = merged.model_dump(mode="json")
        if profile.status == OnboardingStatus.NEEDS_ONBOARDING.value:
            profile.status = OnboardingStatus.IN_PROGRESS.value
        profile.updated_at = datetime.now(timezone.utc)
        saved = self.repository.save(profile)
        return self._to_schema(saved)

    def evaluate(self, user_id: UUID) -> InvestorProfileEvaluationResponse:
        profile = self._get_or_create(user_id)
        answers = InvestorProfileAnswers.model_validate(profile.answers or {})
        missing = InvestorProfileEngine.missing_required_sections(answers)
        if missing:
            raise ValueError(
                "Seções obrigatórias ausentes para avaliar o perfil: "
                + ", ".join(missing)
            )

        evaluation = InvestorProfileEngine.evaluate(answers)
        policy_dict, policy_explanations = InvestorProfileEngine.derive_policy(evaluation, answers)

        now = datetime.now(timezone.utc)
        profile.risk_tolerance_score = evaluation.risk_tolerance_score
        profile.risk_capacity_score = evaluation.risk_capacity_score
        profile.horizon_score = evaluation.horizon_score
        profile.liquidity_need_score = evaluation.liquidity_need_score
        profile.income_need_score = evaluation.income_need_score
        profile.knowledge_score = evaluation.knowledge_score
        profile.emergency_reserve_adequacy_score = evaluation.emergency_reserve_adequacy_score
        profile.overall_classification = evaluation.overall_classification
        profile.dimension_explanations = [
            {
                "dimension": item.dimension,
                "rule": item.rule,
                "result": item.result,
                "message": item.message,
            }
            for item in (*evaluation.explanations, *policy_explanations)
        ]
        profile.policy_preview = _json_safe(policy_dict)
        profile.status = OnboardingStatus.PENDING_CONFIRMATION.value
        profile.evaluated_at = now
        profile.updated_at = now
        saved = self.repository.save(profile)

        return InvestorProfileEvaluationResponse(
            dimensions=_dimensions_from_profile(saved),
            explanations=[
                DimensionExplanationRead(**item) for item in saved.dimension_explanations
            ],
            policy_preview=PolicyPreview.model_validate(saved.policy_preview),
            missing_sections=[],
        )

    def confirm(self, user_id: UUID) -> InvestorProfileRead:
        profile = self.repository.get_by_user(user_id)
        if profile is None or profile.status not in CONFIRMABLE_STATUSES:
            raise ValueError(
                "Não há avaliação pendente de confirmação. Responda o questionário "
                "e calcule o preview antes de confirmar."
            )
        if not profile.policy_preview:
            raise ValueError("Nenhuma política proposta encontrada para confirmar.")

        # Tenta a operação mais arriscada (persistir a PortfolioPolicy) ANTES
        # de marcar o perfil como concluído. Se falhar, o perfil permanece em
        # pending_confirmation/needs_review — nunca "complete" com uma política
        # que não foi de fato salva (consistência sem unit-of-work novo, ver
        # auditoria: repositórios deste projeto sempre comitam por conta própria).
        policy_payload = PortfolioPolicyUpsert(**profile.policy_preview)
        self.policy_service.save_policy(user_id, policy_payload)

        now = datetime.now(timezone.utc)
        profile.status = OnboardingStatus.COMPLETE.value
        profile.confirmed_at = now
        profile.updated_at = now
        saved = self.repository.save(profile)
        return self._to_schema(saved)

    def review(self, user_id: UUID) -> InvestorProfileRead:
        profile = self.repository.get_by_user(user_id)
        if profile is None:
            raise ValueError("Perfil do investidor ainda não foi iniciado.")
        now = datetime.now(timezone.utc)
        profile.status = OnboardingStatus.IN_PROGRESS.value
        profile.last_reviewed_at = now
        profile.updated_at = now
        saved = self.repository.save(profile)
        return self._to_schema(saved)

    # -- internos ------------------------------------------------------------

    def _get_or_create(self, user_id: UUID) -> InvestorProfile:
        profile = self.repository.get_by_user(user_id)
        if profile is not None:
            return profile

        now = datetime.now(timezone.utc)
        profile = InvestorProfile(
            user_id=user_id,
            status=OnboardingStatus.NEEDS_ONBOARDING.value,
            version=1,
            created_at=now,
            updated_at=now,
        )
        existing_policy = self.policy_service.get_policy(user_id)
        if existing_policy is not None:
            prefill = _prefill_from_legacy_policy(existing_policy)
            self._apply_answers_to_columns(profile, prefill)
            profile.answers = prefill.model_dump(mode="json")
        return self.repository.save(profile)

    @staticmethod
    def _apply_answers_to_columns(profile: InvestorProfile, answers: InvestorProfileAnswers) -> None:
        if answers.objectives is not None:
            profile.primary_objective = answers.objectives.primary_objective
            profile.secondary_objectives = list(answers.objectives.secondary_objectives)
        if answers.horizon is not None:
            profile.horizon = answers.horizon.horizon
        if answers.contribution is not None:
            profile.initial_contribution = answers.contribution.initial_contribution
            profile.monthly_contribution = answers.contribution.monthly_contribution
            profile.contribution_stability = answers.contribution.contribution_stability
        if answers.financial_situation is not None:
            profile.income_range = answers.financial_situation.income_range
            profile.investable_net_worth_range = answers.financial_situation.investable_net_worth_range
            profile.emergency_reserve_months = answers.financial_situation.emergency_reserve_months
            profile.has_relevant_debt = answers.financial_situation.has_relevant_debt
            profile.dependents = answers.financial_situation.dependents
        if answers.liquidity is not None:
            profile.liquidity_need = answers.liquidity.liquidity_need
        if answers.income_need is not None:
            profile.income_need = answers.income_need.income_need
        if answers.restrictions is not None:
            profile.allowed_classes = list(answers.restrictions.allowed_classes)
            profile.restricted_classes = list(answers.restrictions.restricted_classes)

    @staticmethod
    def _to_schema(profile: InvestorProfile) -> InvestorProfileRead:
        dimensions = None
        if profile.overall_classification is not None:
            dimensions = _dimensions_from_profile(profile)
        explanations = None
        if profile.dimension_explanations is not None:
            explanations = [
                DimensionExplanationRead(**item) for item in profile.dimension_explanations
            ]
        policy_preview = None
        if profile.policy_preview is not None:
            policy_preview = PolicyPreview.model_validate(profile.policy_preview)

        return InvestorProfileRead(
            id=profile.id,
            user_id=profile.user_id,
            status=OnboardingStatus(profile.status),
            version=profile.version,
            primary_objective=profile.primary_objective,
            secondary_objectives=profile.secondary_objectives,
            horizon=profile.horizon,
            initial_contribution=profile.initial_contribution,
            monthly_contribution=profile.monthly_contribution,
            contribution_stability=profile.contribution_stability,
            income_range=profile.income_range,
            investable_net_worth_range=profile.investable_net_worth_range,
            emergency_reserve_months=profile.emergency_reserve_months,
            has_relevant_debt=profile.has_relevant_debt,
            dependents=profile.dependents,
            liquidity_need=profile.liquidity_need,
            income_need=profile.income_need,
            allowed_classes=profile.allowed_classes,
            restricted_classes=profile.restricted_classes,
            dimensions=dimensions,
            explanations=explanations,
            policy_preview=policy_preview,
            evaluated_at=_aware(profile.evaluated_at),
            confirmed_at=_aware(profile.confirmed_at),
            last_reviewed_at=_aware(profile.last_reviewed_at),
            created_at=_aware(profile.created_at),
            updated_at=_aware(profile.updated_at),
        )


def _dimensions_from_profile(profile: InvestorProfile) -> InvestorProfileDimensions:
    return InvestorProfileDimensions(
        risk_tolerance_score=profile.risk_tolerance_score,
        risk_capacity_score=profile.risk_capacity_score,
        horizon_score=profile.horizon_score,
        liquidity_need_score=profile.liquidity_need_score,
        income_need_score=profile.income_need_score,
        knowledge_score=profile.knowledge_score,
        emergency_reserve_adequacy_score=profile.emergency_reserve_adequacy_score,
        overall_classification=profile.overall_classification,
    )


def _merge_answers(
    current: InvestorProfileAnswers, incoming: InvestorProfileAnswers
) -> InvestorProfileAnswers:
    data = current.model_dump()
    incoming_data = incoming.model_dump(exclude_unset=True)
    for section, value in incoming_data.items():
        if value is not None:
            data[section] = value
    return InvestorProfileAnswers.model_validate(data)


def _prefill_from_legacy_policy(policy) -> InvestorProfileAnswers:
    """Pré-preenche apenas fatos estruturais comprovadamente equivalentes de
    uma PortfolioPolicy antiga. Nunca infere tolerância psicológica,
    capacidade financeira ou conhecimento — essas dimensões exigem respostas
    reais do questionário multidimensional (seção 10 do prompt)."""
    objective = LEGACY_OBJECTIVE_ALIASES.get(str(policy.objective).strip().lower())
    horizon = LEGACY_HORIZON_ALIASES.get(str(policy.investment_horizon).strip().lower())
    liquidity = LEGACY_LIQUIDITY_ALIASES.get(str(policy.liquidity_need).strip().lower())
    allowed_classes = [item.asset_class for item in policy.allocations if item.enabled]

    return InvestorProfileAnswers(
        objectives=ObjectivesAnswer(primary_objective=objective) if objective else None,
        horizon=HorizonAnswer(horizon=horizon) if horizon else None,
        contribution=ContributionAnswer(monthly_contribution=policy.monthly_contribution),
        financial_situation=FinancialSituationAnswer(
            emergency_reserve_months=policy.emergency_reserve_months
        ),
        liquidity=LiquidityAnswer(liquidity_need=liquidity) if liquidity else None,
        income_need=IncomeNeedAnswer(
            income_need="complemento" if policy.income_need else "nenhuma"
        ),
        restrictions=RestrictionsAnswer(allowed_classes=allowed_classes) if allowed_classes else None,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
