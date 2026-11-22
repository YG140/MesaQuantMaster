"""Motor determinístico de indicadores derivados de componentes financeiros
já apurados (hoje, CVM DFP/ITR via CvmFinancialEngine).

Puro: não acessa banco, rede ou relógio. Cada cálculo exige TODOS os
componentes necessários, no MESMO período de referência — nunca mistura
períodos incompatíveis, nunca divide por zero, nunca transforma ausência em
zero. Se um componente estiver ausente, o indicador permanece indisponível
(retorna None) em vez de aproximar ou inventar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class DerivedIndicatorResult:
    key: str
    value: Decimal
    unit: str
    formula: str
    components: dict[str, Decimal]


class DerivedIndicatorEngine:
    """Calcula razões financeiras clássicas a partir de valores brutos já
    normalizados (ex.: por CvmFinancialEngine.aggregate())."""

    @staticmethod
    def _safe_ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or denominator is None or denominator == 0:
            return None
        try:
            return numerator / denominator
        except (InvalidOperation, ZeroDivisionError):
            return None

    @classmethod
    def roe(cls, *, net_income: Decimal, equity: Decimal) -> DerivedIndicatorResult | None:
        ratio = cls._safe_ratio(net_income, equity)
        if ratio is None:
            return None
        return DerivedIndicatorResult(
            key="roe",
            value=(ratio * Decimal("100")).quantize(Decimal("0.01")),
            unit="percent",
            formula="lucro líquido / patrimônio líquido",
            components={"net_income": net_income, "equity": equity},
        )

    @classmethod
    def roa(cls, *, net_income: Decimal, assets: Decimal) -> DerivedIndicatorResult | None:
        ratio = cls._safe_ratio(net_income, assets)
        if ratio is None:
            return None
        return DerivedIndicatorResult(
            key="roa",
            value=(ratio * Decimal("100")).quantize(Decimal("0.01")),
            unit="percent",
            formula="lucro líquido / ativos totais",
            components={"net_income": net_income, "assets": assets},
        )

    @classmethod
    def net_debt(
        cls, *, gross_debt: Decimal, cash_and_equivalents: Decimal
    ) -> DerivedIndicatorResult | None:
        if gross_debt is None or cash_and_equivalents is None:
            return None
        value = gross_debt - cash_and_equivalents
        return DerivedIndicatorResult(
            key="net_debt",
            value=value,
            unit="currency",
            formula="dívida bruta - caixa e equivalentes",
            components={"gross_debt": gross_debt, "cash_and_equivalents": cash_and_equivalents},
        )

    @classmethod
    def net_debt_equity(cls, *, net_debt: Decimal, equity: Decimal) -> DerivedIndicatorResult | None:
        ratio = cls._safe_ratio(net_debt, equity)
        if ratio is None:
            return None
        return DerivedIndicatorResult(
            key="net_debt_equity",
            value=ratio.quantize(Decimal("0.0001")),
            unit="ratio",
            formula="dívida líquida / patrimônio líquido",
            components={"net_debt": net_debt, "equity": equity},
        )

    @classmethod
    def liabilities_assets(
        cls, *, total_liabilities: Decimal, assets: Decimal
    ) -> DerivedIndicatorResult | None:
        ratio = cls._safe_ratio(total_liabilities, assets)
        if ratio is None:
            return None
        return DerivedIndicatorResult(
            key="liabilities_assets",
            value=(ratio * Decimal("100")).quantize(Decimal("0.01")),
            unit="percent",
            formula="passivo exigível / ativos totais",
            components={"total_liabilities": total_liabilities, "assets": assets},
        )

    @classmethod
    def current_liquidity(
        cls, *, current_assets: Decimal, current_liabilities: Decimal
    ) -> DerivedIndicatorResult | None:
        ratio = cls._safe_ratio(current_assets, current_liabilities)
        if ratio is None:
            return None
        return DerivedIndicatorResult(
            key="current_liquidity",
            value=ratio.quantize(Decimal("0.0001")),
            unit="ratio",
            formula="ativo circulante / passivo circulante",
            components={
                "current_assets": current_assets,
                "current_liabilities": current_liabilities,
            },
        )
