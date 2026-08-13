from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.exceptions import AIToolValidationError
from app.schemas.intelligence import BuildPortfolioRequest
from app.schemas.market_intelligence import AnalyzeAssetsRequest
from app.services.intelligence_service import PortfolioIntelligenceService
from app.services.market_intelligence_service import MarketIntelligenceService


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _normalize_symbol(value: str) -> str:
    symbol = value.strip().upper()
    if not 2 <= len(symbol) <= 15 or not symbol.isalnum():
        raise ValueError("Ticker inválido; use apenas letras e números.")
    return symbol


class AnalyzeAssetArguments(ToolArguments):
    symbol: str

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return _normalize_symbol(value)


class CompareAssetsArguments(ToolArguments):
    symbols: list[str] = Field(min_length=2, max_length=50)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_symbol(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Tickers duplicados não são permitidos.")
        return normalized


class AnalyzePortfolioArguments(ToolArguments):
    pass


class GetPortfolioPolicyArguments(ToolArguments):
    pass


class BuildPortfolioSuggestionArguments(ToolArguments):
    available_amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)


TOOL_MODELS: dict[str, type[ToolArguments]] = {
    "analyze_asset": AnalyzeAssetArguments,
    "compare_assets": CompareAssetsArguments,
    "analyze_portfolio": AnalyzePortfolioArguments,
    "get_portfolio_policy": GetPortfolioPolicyArguments,
    "build_portfolio_suggestion": BuildPortfolioSuggestionArguments,
}

TOOL_DESCRIPTIONS = {
    "analyze_asset": "Analisa um ativo com os motores quantitativos existentes.",
    "compare_assets": "Analisa ativos em lote para comparação sem N+1.",
    "analyze_portfolio": "Obtém análise da carteira do usuário autenticado.",
    "get_portfolio_policy": "Obtém a política real do usuário autenticado.",
    "build_portfolio_suggestion": (
        "Calcula uma sugestão educacional read-only usando a política e os motores."
    ),
}


def tool_definitions(max_compare_assets: int = 10) -> list[dict[str, Any]]:
    definitions = []
    for name, model in TOOL_MODELS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        if name == "compare_assets":
            schema["properties"]["symbols"]["maxItems"] = max_compare_assets
        definitions.append(
            {
                "type": "function",
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "strict": True,
                "parameters": schema,
            }
        )
    return definitions


class AIToolRegistry:
    def __init__(
        self,
        *,
        market_intelligence: MarketIntelligenceService,
        portfolio_intelligence: PortfolioIntelligenceService,
        max_compare_assets: int = 10,
    ):
        self.market_intelligence = market_intelligence
        self.portfolio_intelligence = portfolio_intelligence
        self.max_compare_assets = max_compare_assets

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return tool_definitions(self.max_compare_assets)

    def execute(self, name: str, arguments: dict[str, Any], user_id) -> dict[str, Any]:
        model = TOOL_MODELS.get(name)
        if model is None:
            raise AIToolValidationError(f"Ferramenta não permitida: {name}.")
        try:
            parsed = model.model_validate(arguments)
        except Exception as exc:
            raise AIToolValidationError("Argumentos de ferramenta inválidos.") from exc

        if name == "analyze_asset":
            result = self.market_intelligence.analyze_asset(parsed.symbol, user_id)
        elif name == "compare_assets":
            if len(parsed.symbols) > self.max_compare_assets:
                raise AIToolValidationError("Limite de ativos excedido.")
            result = self.market_intelligence.analyze_assets(
                AnalyzeAssetsRequest(symbols=parsed.symbols), user_id
            )
        elif name == "analyze_portfolio":
            result = self.portfolio_intelligence.get_portfolio_intelligence(user_id)
        elif name == "get_portfolio_policy":
            result = self.portfolio_intelligence.get_policy(user_id)
            if result is None:
                return _json_data(name, {"status": "insufficient_data", "policy": None})
        else:
            result = self._build_suggestion(parsed.available_amount, user_id)

        return _json_data(name, result)

    def _build_suggestion(self, amount: Decimal, user_id):
        policy = self.portfolio_intelligence.get_policy(user_id)
        if policy is None:
            return {
                "status": "insufficient_data",
                "missing_data": ["Política de investimento não cadastrada."],
            }
        data = BuildPortfolioRequest(
            available_amount=amount,
            objective=policy.objective,
            horizon=policy.investment_horizon,
            risk_profile=policy.risk_profile,
            monthly_contribution=policy.monthly_contribution,
            needs_emergency_reserve=policy.emergency_reserve_months > 0,
            emergency_months=policy.emergency_reserve_months,
            needs_income=policy.income_need,
            needs_liquidity=policy.liquidity_need.lower() not in {"baixa", "nenhuma"},
            volatility_tolerance=policy.risk_profile,
            max_percentage_per_asset=policy.maximum_weight_per_asset,
            max_percentage_per_sector=policy.maximum_weight_per_sector,
            allowed_classes=[
                item.asset_class for item in policy.allocations if item.enabled
            ],
        )
        return self.portfolio_intelligence.build_portfolio(user_id, data)


def _json_data(tool_name: str, value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
    elif isinstance(value, dict):
        data = value
    else:
        raise TypeError("Resultado de ferramenta não serializável.")
    compact = _compact_tool_data(tool_name, data)
    return {"untrusted_tool_data": _sanitize_for_provider(compact)}


def _compact_tool_data(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Seleciona somente campos necessários à explicação da tool atual."""
    if tool_name == "analyze_asset":
        return _compact_asset(data)
    if tool_name == "compare_assets":
        return {
            "snapshots": [_compact_asset(item) for item in data.get("snapshots", [])],
            "errors": data.get("errors", []),
            "calculated_at": data.get("calculated_at"),
        }
    if tool_name == "analyze_portfolio":
        return _select(
            data,
            "overview",
            "diagnosis",
            "recommendations",
            "rebalancing",
            "policy",
            "generated_at",
        )
    if tool_name == "get_portfolio_policy":
        return _select(
            data,
            "status",
            "policy",
            "name",
            "objective",
            "risk_profile",
            "investment_horizon",
            "monthly_contribution",
            "liquidity_need",
            "income_need",
            "emergency_reserve_months",
            "maximum_weight_per_asset",
            "maximum_weight_per_sector",
            "maximum_weight_per_issuer",
            "rebalance_tolerance",
            "allocations",
        )
    return _select(
        data,
        "class_allocations",
        "assets",
        "exclusions",
        "total_allocated_percentage",
        "total_allocated_amount",
        "unallocated_amount",
        "confidence",
        "status",
        "missing_data",
        "strategy_summary",
        "diagnosis",
        "contribution_plan",
        "disclaimer",
        "generated_at",
    )


def _compact_asset(data: dict[str, Any]) -> dict[str, Any]:
    compact = _select(
        data,
        "symbol",
        "name",
        "asset_class",
        "current_price",
        "currency",
        "market_updated_at",
        "indicators",
        "quality_score",
        "valuation_score",
        "income_score",
        "growth_score",
        "debt_score",
        "risk_score",
        "liquidity_score",
        "data_quality_score",
        "strategy_fit_score",
        "overall_score",
        "recommendation",
        "valuation_status",
        "valuation",
        "confidence",
        "coverage_percentage",
        "anomaly_flags",
        "data_quality",
        "positive_reasons",
        "warning_reasons",
        "missing_data",
        "calculated_at",
    )
    compact["indicators"] = [
        _select(
            item,
            "key",
            "label",
            "value",
            "unit",
            "status",
            "source",
            "source_type",
            "reference_date",
            "valid_until",
            "freshness_status",
        )
        for item in compact.get("indicators", [])
    ]
    return compact


def _select(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: data[key] for key in keys if key in data}


def _sanitize_for_provider(value: Any) -> Any:
    """Remove identificadores internos e limita texto antes de enviar ao LLM."""
    if isinstance(value, dict):
        blocked_keys = {"id", "user_id", "asset_id", "policy_id"}
        return {
            key: _sanitize_for_provider(item)
            for key, item in value.items()
            if key not in blocked_keys
        }
    if isinstance(value, list):
        return [_sanitize_for_provider(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:2000]
    return value


ALLOWED_TOOLS = frozenset(TOOL_MODELS)
