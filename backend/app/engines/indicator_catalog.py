from __future__ import annotations

from decimal import Decimal

from app.schemas.market_intelligence import (
    CoverageBreakdown,
    IndicatorCatalogEntry,
    IndicatorDirection,
    IndicatorImportance,
    IndicatorLayer,
    IndicatorPillar,
    IndicatorStatus,
    InvestmentClass,
    MacroIndicatorDefinition,
    NormalizedIndicator,
)


PRICE_MARKET = "preço e mercado"
VALUATION = "valuation"
DEBT = "endividamento"
EFFICIENCY = "eficiência"
PROFITABILITY = "rentabilidade"
GROWTH = "crescimento"
INCOME = "renda"
RISK = "risco"
LIQUIDITY = "liquidez"
STRUCTURE = "estrutura patrimonial"
DATA_QUALITY = "qualidade dos dados"


ALL_MARKET_CLASSES = [
    InvestmentClass.STOCK,
    InvestmentClass.FII,
    InvestmentClass.ETF,
    InvestmentClass.TREASURY,
]
PRIVATE_FIXED_INCOME_CLASSES = [
    InvestmentClass.CDB,
    InvestmentClass.LCI,
    InvestmentClass.LCA,
    InvestmentClass.DEBENTURE,
]


def catalog_entry(
    key: str,
    label: str,
    category: str,
    applicable_classes: list[InvestmentClass],
    *,
    description: str | None = None,
    formula_or_origin: str = "Provider de mercado",
    unit: str = "ratio",
    layer: IndicatorLayer = IndicatorLayer.FUNDAMENTAL,
    direction: IndicatorDirection = IndicatorDirection.INFORMATIONAL,
    plausible_min: str | None = None,
    plausible_max: str | None = None,
    requires_history: bool = False,
    temporal_validity_days: int | None = 2,
    required: bool = False,
    default_weight: str = "1",
    sector_comparable: bool = False,
    history_comparable: bool = False,
    excluded_sectors: list[str] | None = None,
    source: str = "BRAPI",
    availability: IndicatorStatus = IndicatorStatus.UNAVAILABLE,
    importance: IndicatorImportance | str | None = None,
) -> IndicatorCatalogEntry:
    resolved_importance = (
        IndicatorImportance(str(importance))
        if importance is not None
        else (IndicatorImportance.REQUIRED if required else IndicatorImportance.OPTIONAL)
    )
    return IndicatorCatalogEntry(
        key=key,
        label=label,
        description=description or label,
        formula_or_origin=formula_or_origin,
        unit=unit,
        category=category,
        layer=layer,
        applicable_classes=applicable_classes,
        excluded_sectors=excluded_sectors or [],
        direction=direction,
        plausible_min=Decimal(plausible_min) if plausible_min is not None else None,
        plausible_max=Decimal(plausible_max) if plausible_max is not None else None,
        requires_history=requires_history,
        temporal_validity_days=temporal_validity_days,
        required=required,
        importance=resolved_importance,
        default_weight=Decimal(default_weight),
        sector_comparable=sector_comparable,
        history_comparable=history_comparable,
        source=source,
        availability=availability,
    )


PROVIDER_AVAILABLE_KEYS = {
    "current_price",
    "daily_change",
    "volume",
    "liquidity",
    "market_cap",
    "previous_close",
    "day_low",
    "day_high",
    "day_range",
}


def macro_entry(
    key: str,
    label: str,
    region: str,
    *,
    unit: str = "percent",
    frequency: str = "mensal",
    source: str = "Provedor macroeconômico ainda não integrado",
    description: str | None = None,
) -> MacroIndicatorDefinition:
    return MacroIndicatorDefinition(
        key=key,
        label=label,
        description=description or label,
        region=region,
        unit=unit,
        frequency=frequency,
        source=source,
    )


STOCK_INDICATORS = [
    catalog_entry(
        "current_price",
        "Preço atual",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        required=True,
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "daily_change",
        "Variação diária",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="percent",
        plausible_min="-100",
        plausible_max="1000",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "twelve_month_return",
        "Valorização em 12 meses",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="percent",
        requires_history=True,
        history_comparable=True,
    ),
    catalog_entry(
        "month_low",
        "Mínima do mês",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        requires_history=True,
    ),
    catalog_entry(
        "month_high",
        "Máxima do mês",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        requires_history=True,
    ),
    catalog_entry(
        "week_52_low",
        "Mínima de 52 semanas",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        requires_history=True,
    ),
    catalog_entry(
        "week_52_high",
        "Máxima de 52 semanas",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        requires_history=True,
    ),
    catalog_entry(
        "day_low",
        "Mínima do dia",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "day_high",
        "Máxima do dia",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "day_range",
        "Faixa do dia",
        RISK,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.LOWER_IS_BETTER,
        plausible_min="0",
        plausible_max="100",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "volume",
        "Volume negociado",
        LIQUIDITY,
        [InvestmentClass.STOCK],
        unit="quantity",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
        plausible_min="0",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "liquidity",
        "Liquidez estimada com dados limitados",
        LIQUIDITY,
        [InvestmentClass.STOCK],
        unit="currency",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
        plausible_min="0",
        availability=IndicatorStatus.AVAILABLE,
        description="Estimativa calculada com o preço atual e o volume informado pelo provedor; não representa média histórica.",
    ),
    catalog_entry(
        "market_cap",
        "Valor de mercado",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
        plausible_min="0",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "enterprise_value",
        "Valor da firma",
        PRICE_MARKET,
        [InvestmentClass.STOCK],
        unit="currency",
    ),
    catalog_entry(
        "shares_count",
        "Quantidade de ações",
        STRUCTURE,
        [InvestmentClass.STOCK],
        unit="quantity",
    ),
    catalog_entry(
        "free_float", "Free float", STRUCTURE, [InvestmentClass.STOCK], unit="percent"
    ),
    catalog_entry(
        "dividend_yield",
        "Dividend Yield",
        INCOME,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.CONTEXT_DEPENDENT,
        required=True,
        history_comparable=True,
    ),
    catalog_entry(
        "price_earnings",
        "P/L",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.IDEAL_RANGE,
        required=True,
        sector_comparable=True,
        history_comparable=True,
    ),
    catalog_entry(
        "peg_ratio",
        "PEG Ratio",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.IDEAL_RANGE,
        sector_comparable=True,
    ),
    catalog_entry(
        "price_book",
        "P/VP",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.IDEAL_RANGE,
        required=True,
        sector_comparable=True,
        history_comparable=True,
    ),
    catalog_entry(
        "ev_ebitda",
        "EV/EBITDA",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.IDEAL_RANGE,
        excluded_sectors=["bancos", "seguradoras"],
        sector_comparable=True,
    ),
    catalog_entry(
        "ev_ebit",
        "EV/EBIT",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.IDEAL_RANGE,
        excluded_sectors=["bancos", "seguradoras"],
        sector_comparable=True,
    ),
    catalog_entry(
        "price_ebitda",
        "P/EBITDA",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "price_ebit",
        "P/EBIT",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "book_value_per_share",
        "VPA",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="currency",
    ),
    catalog_entry(
        "earnings_per_share", "LPA", VALUATION, [InvestmentClass.STOCK], unit="currency"
    ),
    catalog_entry(
        "price_assets", "P/Ativos", VALUATION, [InvestmentClass.STOCK], unit="ratio"
    ),
    catalog_entry(
        "price_sales", "P/SR", VALUATION, [InvestmentClass.STOCK], unit="ratio"
    ),
    catalog_entry(
        "price_working_capital",
        "P/Capital de Giro",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
    ),
    catalog_entry(
        "price_net_current_assets",
        "P/Ativo Circulante Líquido",
        VALUATION,
        [InvestmentClass.STOCK],
        unit="ratio",
    ),
    catalog_entry(
        "gross_debt",
        "Dívida bruta",
        DEBT,
        [InvestmentClass.STOCK],
        unit="currency",
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "cash_and_equivalents",
        "Disponibilidade",
        DEBT,
        [InvestmentClass.STOCK],
        unit="currency",
    ),
    catalog_entry(
        "net_debt",
        "Dívida líquida",
        DEBT,
        [InvestmentClass.STOCK],
        unit="currency",
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "net_debt_equity",
        "Dívida líquida/PL",
        DEBT,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.LOWER_IS_BETTER,
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "net_debt_ebitda",
        "Dívida líquida/EBITDA",
        DEBT,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.LOWER_IS_BETTER,
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "net_debt_ebit",
        "Dívida líquida/EBIT",
        DEBT,
        [InvestmentClass.STOCK],
        unit="ratio",
        direction=IndicatorDirection.LOWER_IS_BETTER,
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "equity_assets", "PL/Ativos", DEBT, [InvestmentClass.STOCK], unit="percent"
    ),
    catalog_entry(
        "liabilities_assets",
        "Passivos/Ativos",
        DEBT,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.LOWER_IS_BETTER,
    ),
    catalog_entry(
        "current_liquidity",
        "Liquidez corrente",
        DEBT,
        [InvestmentClass.STOCK],
        unit="ratio",
    ),
    catalog_entry(
        "gross_margin",
        "Margem bruta",
        EFFICIENCY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
    ),
    catalog_entry(
        "ebitda_margin",
        "Margem EBITDA",
        EFFICIENCY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
        excluded_sectors=["bancos", "seguradoras"],
    ),
    catalog_entry(
        "ebit_margin",
        "Margem EBIT",
        EFFICIENCY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
    ),
    catalog_entry(
        "net_margin",
        "Margem líquida",
        EFFICIENCY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
    ),
    catalog_entry(
        "roe",
        "ROE",
        PROFITABILITY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
        required=True,
        sector_comparable=True,
    ),
    catalog_entry(
        "roa",
        "ROA",
        PROFITABILITY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
        sector_comparable=True,
    ),
    catalog_entry(
        "roic",
        "ROIC",
        PROFITABILITY,
        [InvestmentClass.STOCK],
        unit="percent",
        direction=IndicatorDirection.HIGHER_IS_BETTER,
        excluded_sectors=["bancos", "seguradoras"],
        sector_comparable=True,
    ),
    catalog_entry(
        "asset_turnover",
        "Giro dos ativos",
        PROFITABILITY,
        [InvestmentClass.STOCK],
        unit="ratio",
    ),
    catalog_entry(
        "revenue_cagr_3y",
        "CAGR de receitas em 3 anos",
        GROWTH,
        [InvestmentClass.STOCK],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "revenue_cagr_5y",
        "CAGR de receitas em 5 anos",
        GROWTH,
        [InvestmentClass.STOCK],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "earnings_cagr_3y",
        "CAGR de lucros em 3 anos",
        GROWTH,
        [InvestmentClass.STOCK],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "earnings_cagr_5y",
        "CAGR de lucros em 5 anos",
        GROWTH,
        [InvestmentClass.STOCK],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "equity",
        "Patrimônio líquido",
        STRUCTURE,
        [InvestmentClass.STOCK],
        unit="currency",
    ),
    catalog_entry(
        "assets", "Ativos", STRUCTURE, [InvestmentClass.STOCK], unit="currency"
    ),
    catalog_entry(
        "current_assets",
        "Ativo circulante",
        STRUCTURE,
        [InvestmentClass.STOCK],
        unit="currency",
    ),
    catalog_entry(
        "sector",
        "Setor",
        STRUCTURE,
        [InvestmentClass.STOCK],
        unit="text",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "subsector",
        "Subsetor",
        STRUCTURE,
        [InvestmentClass.STOCK],
        unit="text",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "segment", "Segmento", STRUCTURE, [InvestmentClass.STOCK], unit="text"
    ),
    catalog_entry(
        "governance_level",
        "Nível de governança",
        STRUCTURE,
        [InvestmentClass.STOCK],
        unit="text",
    ),
    catalog_entry(
        "dividend_history",
        "Histórico de proventos",
        INCOME,
        [InvestmentClass.STOCK],
        unit="text",
        requires_history=True,
    ),
]


FII_INDICATORS = [
    catalog_entry(
        "current_price",
        "Preço atual",
        PRICE_MARKET,
        [InvestmentClass.FII],
        unit="currency",
        required=True,
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "daily_change",
        "Variação",
        PRICE_MARKET,
        [InvestmentClass.FII],
        unit="percent",
        plausible_min="-100",
        plausible_max="1000",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "twelve_month_return",
        "Valorização em 12 meses",
        PRICE_MARKET,
        [InvestmentClass.FII],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "day_low",
        "Mínima",
        PRICE_MARKET,
        [InvestmentClass.FII],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "day_high",
        "Máxima",
        PRICE_MARKET,
        [InvestmentClass.FII],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "dividend_yield",
        "Dividend Yield",
        INCOME,
        [InvestmentClass.FII],
        unit="percent",
        required=True,
    ),
    catalog_entry(
        "income_12m",
        "Rendimento dos últimos 12 meses",
        INCOME,
        [InvestmentClass.FII],
        unit="currency",
        requires_history=True,
    ),
    catalog_entry(
        "last_income",
        "Último rendimento",
        INCOME,
        [InvestmentClass.FII],
        unit="currency",
    ),
    catalog_entry(
        "next_distribution",
        "Próxima distribuição conhecida",
        INCOME,
        [InvestmentClass.FII],
        unit="currency",
    ),
    catalog_entry("base_date", "Data-base", INCOME, [InvestmentClass.FII], unit="date"),
    catalog_entry(
        "payment_date", "Data de pagamento", INCOME, [InvestmentClass.FII], unit="date"
    ),
    catalog_entry(
        "base_quote", "Cotação-base", INCOME, [InvestmentClass.FII], unit="currency"
    ),
    catalog_entry(
        "price_book",
        "P/VP",
        VALUATION,
        [InvestmentClass.FII],
        unit="ratio",
        required=True,
    ),
    catalog_entry(
        "book_value_per_share",
        "Valor patrimonial por cota",
        VALUATION,
        [InvestmentClass.FII],
        unit="currency",
    ),
    catalog_entry(
        "equity",
        "Patrimônio líquido",
        STRUCTURE,
        [InvestmentClass.FII],
        unit="currency",
    ),
    catalog_entry(
        "segment",
        "Natureza do fundo (tijolo/papel/híbrido)",
        STRUCTURE,
        [InvestmentClass.FII],
        unit="text",
        description=(
            "Classificação real do fundo (ex.: segmentType da BRAPI, "
            "derivado do próprio provedor/CVM) -- nunca inferida pelo "
            "ticker. Usada para decidir dinamicamente quais indicadores "
            "de segment_risk são aplicáveis a este FII."
        ),
    ),
    catalog_entry(
        "market_cap",
        "Valor de mercado",
        PRICE_MARKET,
        [InvestmentClass.FII],
        unit="currency",
        plausible_min="0",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "shareholders_count",
        "Número de cotistas",
        STRUCTURE,
        [InvestmentClass.FII],
        unit="quantity",
    ),
    catalog_entry(
        "shares_count",
        "Quantidade de cotas",
        STRUCTURE,
        [InvestmentClass.FII],
        unit="quantity",
    ),
    catalog_entry(
        "liquidity",
        "Liquidez estimada com dados limitados",
        LIQUIDITY,
        [InvestmentClass.FII],
        unit="currency",
        plausible_min="0",
        availability=IndicatorStatus.AVAILABLE,
        description="Estimativa calculada com o preço atual e o volume informado pelo provedor; não representa média histórica.",
    ),
    catalog_entry(
        "volume",
        "Volume negociado",
        LIQUIDITY,
        [InvestmentClass.FII],
        unit="quantity",
        plausible_min="0",
        availability=IndicatorStatus.AVAILABLE,
        description="Volume informado pelo provedor na cotação atual.",
    ),
    catalog_entry(
        "cash_percentage",
        "Percentual em caixa",
        STRUCTURE,
        [InvestmentClass.FII],
        unit="percent",
    ),
    catalog_entry(
        "income_cagr_3y",
        "CAGR dos rendimentos em 3 anos",
        GROWTH,
        [InvestmentClass.FII],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "income_cagr_5y",
        "CAGR dos rendimentos em 5 anos",
        GROWTH,
        [InvestmentClass.FII],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "quote_cagr_3y",
        "CAGR do valor da cota em 3 anos",
        GROWTH,
        [InvestmentClass.FII],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "quote_cagr_5y",
        "CAGR do valor da cota em 5 anos",
        GROWTH,
        [InvestmentClass.FII],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "physical_vacancy",
        "Vacância física",
        RISK,
        [InvestmentClass.FII],
        unit="percent",
        required=True,
    ),
    catalog_entry(
        "financial_vacancy",
        "Vacância financeira",
        RISK,
        [InvestmentClass.FII],
        unit="percent",
    ),
    catalog_entry(
        "delinquency", "Inadimplência", RISK, [InvestmentClass.FII], unit="percent"
    ),
    catalog_entry(
        "property_concentration",
        "Concentração de imóveis",
        RISK,
        [InvestmentClass.FII],
        unit="percent",
    ),
    catalog_entry(
        "tenant_concentration",
        "Concentração de locatários",
        RISK,
        [InvestmentClass.FII],
        unit="percent",
    ),
    catalog_entry(
        "debtor_concentration",
        "Concentração de devedores",
        RISK,
        [InvestmentClass.FII],
        unit="percent",
    ),
    catalog_entry(
        "contract_average_term",
        "Prazo médio dos contratos",
        RISK,
        [InvestmentClass.FII],
        unit="months",
    ),
    catalog_entry("indexers", "Indexadores", RISK, [InvestmentClass.FII], unit="text"),
    catalog_entry("debt", "Endividamento", DEBT, [InvestmentClass.FII], unit="percent"),
    catalog_entry(
        "property_quality",
        "Qualidade dos imóveis",
        DATA_QUALITY,
        [InvestmentClass.FII],
        unit="text",
    ),
    catalog_entry(
        "receivable_quality",
        "Qualidade dos recebíveis",
        DATA_QUALITY,
        [InvestmentClass.FII],
        unit="text",
    ),
    catalog_entry(
        "credit_risk", "Risco de crédito", RISK, [InvestmentClass.FII], unit="text"
    ),
    catalog_entry(
        "relevant_issuances",
        "Emissões e amortizações relevantes",
        STRUCTURE,
        [InvestmentClass.FII],
        unit="text",
        requires_history=True,
    ),
]


ETF_INDICATORS = [
    catalog_entry(
        "current_price",
        "Preço atual",
        PRICE_MARKET,
        [InvestmentClass.ETF],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "daily_change",
        "Variação diária",
        PRICE_MARKET,
        [InvestmentClass.ETF],
        unit="percent",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "tracked_index",
        "Índice acompanhado",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="text",
        required=True,
    ),
    catalog_entry(
        "management_fee",
        "Taxa de administração",
        EFFICIENCY,
        [InvestmentClass.ETF],
        unit="percent",
        required=True,
    ),
    catalog_entry(
        "equity", "Patrimônio", STRUCTURE, [InvestmentClass.ETF], unit="currency"
    ),
    catalog_entry(
        "liquidity",
        "Liquidez estimada com dados limitados",
        LIQUIDITY,
        [InvestmentClass.ETF],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
        description="Estimativa calculada com o preço atual e o volume informado pelo provedor; não representa média histórica.",
    ),
    catalog_entry(
        "volume",
        "Volume negociado",
        LIQUIDITY,
        [InvestmentClass.ETF],
        unit="quantity",
        availability=IndicatorStatus.AVAILABLE,
        description="Volume informado pelo provedor na cotação atual.",
    ),
    catalog_entry(
        "tracking_error",
        "Tracking error",
        RISK,
        [InvestmentClass.ETF],
        unit="percent",
        requires_history=True,
    ),
    catalog_entry(
        "concentration", "Concentração", RISK, [InvestmentClass.ETF], unit="percent"
    ),
    catalog_entry(
        "sector_exposure",
        "Exposição setorial",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="text",
    ),
    catalog_entry(
        "geographic_exposure",
        "Exposição geográfica",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="text",
    ),
    catalog_entry(
        "currency_exposure",
        "Exposição cambial",
        RISK,
        [InvestmentClass.ETF],
        unit="text",
    ),
    catalog_entry(
        "premium_discount",
        "Prêmio ou desconto",
        VALUATION,
        [InvestmentClass.ETF],
        unit="percent",
    ),
]


TREASURY_INDICATORS = [
    catalog_entry(
        "current_price",
        "Preço atual",
        PRICE_MARKET,
        [InvestmentClass.TREASURY],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "treasury_title",
        "Título",
        STRUCTURE,
        [InvestmentClass.TREASURY],
        unit="text",
        required=True,
    ),
    catalog_entry(
        "indexer",
        "Indexador",
        STRUCTURE,
        [InvestmentClass.TREASURY],
        unit="text",
        required=True,
    ),
    catalog_entry(
        "treasury_rate",
        "Taxa atual",
        INCOME,
        [InvestmentClass.TREASURY],
        unit="percent",
        required=True,
    ),
    catalog_entry(
        "real_rate", "Taxa real", INCOME, [InvestmentClass.TREASURY], unit="percent"
    ),
    catalog_entry(
        "maturity_date",
        "Vencimento",
        RISK,
        [InvestmentClass.TREASURY],
        unit="date",
        required=True,
    ),
    catalog_entry(
        "duration", "Duration", RISK, [InvestmentClass.TREASURY], unit="years"
    ),
    catalog_entry(
        "liquidity", "Liquidez", LIQUIDITY, [InvestmentClass.TREASURY], unit="text"
    ),
    catalog_entry(
        "interest_sensitivity",
        "Sensibilidade aos juros",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
    ),
    catalog_entry(
        "mark_to_market",
        "Marcação a mercado",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
    ),
    catalog_entry(
        "term_fit", "Adequação ao prazo", RISK, [InvestmentClass.TREASURY], unit="text"
    ),
    catalog_entry(
        "objective_fit",
        "Adequação ao objetivo",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
    ),
]


PRIVATE_FIXED_INCOME_INDICATORS = [
    catalog_entry(
        "issuer",
        "Emissor",
        STRUCTURE,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        required=True,
    ),
    catalog_entry(
        "indexer",
        "Indexador",
        STRUCTURE,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        required=True,
    ),
    catalog_entry(
        "cdi_percentage",
        "Percentual do CDI",
        INCOME,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
    ),
    catalog_entry(
        "fixed_rate",
        "Taxa prefixada",
        INCOME,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
    ),
    catalog_entry(
        "real_rate", "Taxa real", INCOME, PRIVATE_FIXED_INCOME_CLASSES, unit="percent"
    ),
    catalog_entry(
        "maturity_date", "Vencimento", RISK, PRIVATE_FIXED_INCOME_CLASSES, unit="date"
    ),
    catalog_entry(
        "lockup", "Carência", RISK, PRIVATE_FIXED_INCOME_CLASSES, unit="days"
    ),
    catalog_entry(
        "liquidity", "Liquidez", LIQUIDITY, PRIVATE_FIXED_INCOME_CLASSES, unit="text"
    ),
    catalog_entry(
        "tax", "Imposto", INCOME, PRIVATE_FIXED_INCOME_CLASSES, unit="percent"
    ),
    catalog_entry(
        "net_return",
        "Rentabilidade líquida",
        INCOME,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
    ),
    catalog_entry(
        "fgc_coverage",
        "Cobertura do FGC",
        RISK,
        [InvestmentClass.CDB, InvestmentClass.LCI, InvestmentClass.LCA],
        unit="text",
    ),
    catalog_entry(
        "issuer_exposure",
        "Exposição acumulada ao emissor",
        RISK,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
    ),
]


OTHER_CLASS_INDICATORS = [
    catalog_entry(
        "current_price",
        "Preço atual",
        PRICE_MARKET,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL, InvestmentClass.CRYPTO],
        unit="currency",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "daily_change",
        "Variação diária",
        PRICE_MARKET,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL, InvestmentClass.CRYPTO],
        unit="percent",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "volume",
        "Volume",
        LIQUIDITY,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL, InvestmentClass.CRYPTO],
        unit="quantity",
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "fund_strategy",
        "Estratégia do fundo",
        STRUCTURE,
        [InvestmentClass.INVESTMENT_FUND],
        unit="text",
    ),
    catalog_entry(
        "management_fee",
        "Taxa de administração",
        EFFICIENCY,
        [InvestmentClass.INVESTMENT_FUND],
        unit="percent",
    ),
    catalog_entry(
        "redemption_term",
        "Prazo de resgate",
        LIQUIDITY,
        [InvestmentClass.INVESTMENT_FUND],
        unit="days",
    ),
]


ADVANCED_ETF_INDICATORS = [
    catalog_entry(
        "tracking_difference",
        "Diferença de tracking",
        RISK,
        [InvestmentClass.ETF],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
        requires_history=True,
    ),
    catalog_entry(
        "assets_under_management",
        "Patrimônio sob gestão",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "average_daily_volume",
        "Volume médio diário",
        LIQUIDITY,
        [InvestmentClass.ETF],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
        requires_history=True,
    ),
    catalog_entry(
        "bid_ask_spread",
        "Spread entre compra e venda",
        LIQUIDITY,
        [InvestmentClass.ETF, InvestmentClass.BDR, InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
        direction=IndicatorDirection.LOWER_IS_BETTER,
    ),
    catalog_entry(
        "holdings_count",
        "Quantidade de ativos",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="quantity",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "top_holdings_concentration",
        "Concentração nas maiores posições",
        RISK,
        [InvestmentClass.ETF],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
        direction=IndicatorDirection.LOWER_IS_BETTER,
    ),
    catalog_entry(
        "currency_hedged",
        "Proteção cambial",
        RISK,
        [InvestmentClass.ETF],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "historical_return",
        "Retorno histórico",
        GROWTH,
        [InvestmentClass.ETF],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
        requires_history=True,
    ),
    catalog_entry(
        "volatility",
        "Volatilidade",
        RISK,
        [InvestmentClass.ETF, InvestmentClass.TREASURY, InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
        requires_history=True,
    ),
    catalog_entry(
        "maximum_drawdown",
        "Queda máxima",
        RISK,
        [InvestmentClass.ETF, InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
        requires_history=True,
    ),
    catalog_entry(
        "dividend_distribution",
        "Distribuição de rendimentos",
        INCOME,
        [InvestmentClass.ETF],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "fund_domicile",
        "Domicílio do fundo",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "replication_method",
        "Método de replicação",
        STRUCTURE,
        [InvestmentClass.ETF],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
]


ADVANCED_TREASURY_INDICATORS = [
    catalog_entry(
        "bond_type",
        "Tipo do título",
        STRUCTURE,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "current_rate",
        "Taxa atual",
        INCOME,
        [InvestmentClass.TREASURY],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "modified_duration",
        "Duration modificada",
        RISK,
        [InvestmentClass.TREASURY],
        unit="years",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "convexity",
        "Convexidade",
        RISK,
        [InvestmentClass.TREASURY],
        unit="ratio",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "coupon_type",
        "Tipo de cupom",
        INCOME,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "coupon_frequency",
        "Frequência do cupom",
        INCOME,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "market_price",
        "Preço de mercado",
        PRICE_MARKET,
        [InvestmentClass.TREASURY],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "face_value",
        "Valor de face",
        PRICE_MARKET,
        [InvestmentClass.TREASURY],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "accrued_interest",
        "Juros acumulados",
        INCOME,
        [InvestmentClass.TREASURY],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "interest_rate_sensitivity",
        "Sensibilidade à taxa de juros",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "gross_return",
        "Rentabilidade bruta",
        INCOME,
        [InvestmentClass.TREASURY, *PRIVATE_FIXED_INCOME_CLASSES],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "estimated_net_return",
        "Rentabilidade líquida estimada",
        INCOME,
        [InvestmentClass.TREASURY, *PRIVATE_FIXED_INCOME_CLASSES],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "taxation",
        "Tributação",
        INCOME,
        [InvestmentClass.TREASURY, *PRIVATE_FIXED_INCOME_CLASSES, InvestmentClass.BDR],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "inflation_reference",
        "Referência de inflação",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "selic_reference",
        "Referência Selic",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "yield_curve_position",
        "Posição na curva de juros",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "objective_suitability",
        "Adequação ao objetivo",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "horizon_suitability",
        "Adequação ao horizonte",
        RISK,
        [InvestmentClass.TREASURY],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
]


ADVANCED_FIXED_INCOME_INDICATORS = [
    catalog_entry(
        "product_type",
        "Tipo do produto",
        STRUCTURE,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "issuer_type",
        "Tipo do emissor",
        STRUCTURE,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "inflation_spread",
        "Spread sobre inflação",
        INCOME,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "issue_date",
        "Data de emissão",
        STRUCTURE,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="date",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "grace_period",
        "Carência",
        LIQUIDITY,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="days",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "early_redemption",
        "Resgate antecipado",
        LIQUIDITY,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "credit_rating",
        "Rating de crédito",
        RISK,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "rating_agency",
        "Agência de rating",
        RISK,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "rating_date",
        "Data do rating",
        RISK,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="date",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "fgc_eligible",
        "Elegível ao FGC",
        RISK,
        [InvestmentClass.CDB, InvestmentClass.LCI, InvestmentClass.LCA],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "fgc_covered_amount",
        "Valor coberto pelo FGC",
        RISK,
        [InvestmentClass.CDB, InvestmentClass.LCI, InvestmentClass.LCA],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "financial_group_exposure",
        "Exposição ao grupo financeiro",
        RISK,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "benchmark_spread",
        "Spread sobre benchmark",
        INCOME,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "minimum_investment",
        "Investimento mínimo",
        PRICE_MARKET,
        PRIVATE_FIXED_INCOME_CLASSES,
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
]


BDR_INDICATORS = [
    catalog_entry(
        "underlying_symbol",
        "Ticker do ativo subjacente",
        STRUCTURE,
        [InvestmentClass.BDR],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
        required=True,
    ),
    catalog_entry(
        "underlying_company",
        "Empresa subjacente",
        STRUCTURE,
        [InvestmentClass.BDR],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "underlying_exchange",
        "Bolsa do ativo subjacente",
        STRUCTURE,
        [InvestmentClass.BDR],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "country",
        "País",
        STRUCTURE,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "currency",
        "Moeda",
        RISK,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "bdr_ratio",
        "Paridade do BDR",
        STRUCTURE,
        [InvestmentClass.BDR],
        unit="ratio",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "underlying_price",
        "Preço do ativo subjacente",
        PRICE_MARKET,
        [InvestmentClass.BDR],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "exchange_rate",
        "Taxa de câmbio",
        RISK,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL],
        unit="currency",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "currency_risk",
        "Risco cambial",
        RISK,
        [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "bdr_liquidity",
        "Liquidez do BDR",
        LIQUIDITY,
        [InvestmentClass.BDR],
        unit="currency",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "fees",
        "Custos e taxas",
        EFFICIENCY,
        [InvestmentClass.BDR],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "debt_metrics",
        "Indicadores de dívida",
        DEBT,
        [InvestmentClass.BDR],
        unit="text",
        layer=IndicatorLayer.FUNDAMENTAL,
    ),
]


CRYPTO_INDICATORS = [
    catalog_entry(
        "price",
        "Preço",
        PRICE_MARKET,
        [InvestmentClass.CRYPTO],
        unit="currency",
        layer=IndicatorLayer.FUNDAMENTAL,
        availability=IndicatorStatus.AVAILABLE,
    ),
    catalog_entry(
        "fully_diluted_valuation",
        "Valor totalmente diluído",
        PRICE_MARKET,
        [InvestmentClass.CRYPTO],
        unit="currency",
        layer=IndicatorLayer.FUNDAMENTAL,
    ),
    catalog_entry(
        "circulating_supply",
        "Oferta circulante",
        STRUCTURE,
        [InvestmentClass.CRYPTO],
        unit="quantity",
        layer=IndicatorLayer.FUNDAMENTAL,
    ),
    catalog_entry(
        "maximum_supply",
        "Oferta máxima",
        STRUCTURE,
        [InvestmentClass.CRYPTO],
        unit="quantity",
        layer=IndicatorLayer.FUNDAMENTAL,
    ),
    catalog_entry(
        "market_dominance",
        "Dominância de mercado",
        PRICE_MARKET,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "correlation",
        "Correlação",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="ratio",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "rsi",
        "RSI",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="ratio",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "moving_average_short",
        "Média móvel curta",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="currency",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "moving_average_long",
        "Média móvel longa",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="currency",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "trend",
        "Tendência",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "relative_strength",
        "Força relativa",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="ratio",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "volume_trend",
        "Tendência do volume",
        LIQUIDITY,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "distance_from_high",
        "Distância da máxima",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "distance_from_low",
        "Distância da mínima",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "mvrv",
        "MVRV",
        VALUATION,
        [InvestmentClass.CRYPTO],
        unit="ratio",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "nvt",
        "NVT",
        VALUATION,
        [InvestmentClass.CRYPTO],
        unit="ratio",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "active_addresses",
        "Endereços ativos",
        LIQUIDITY,
        [InvestmentClass.CRYPTO],
        unit="quantity",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "exchange_inflows",
        "Entradas em corretoras",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="quantity",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "exchange_outflows",
        "Saídas de corretoras",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="quantity",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "holder_concentration",
        "Concentração de detentores",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "network_activity",
        "Atividade da rede",
        LIQUIDITY,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "staking_ratio",
        "Percentual em staking",
        INCOME,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "issuance_rate",
        "Taxa de emissão",
        INCOME,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "token_unlocks",
        "Desbloqueios de tokens",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.TECHNICAL_ALTERNATIVE,
    ),
    catalog_entry(
        "custody_risk",
        "Risco de custódia",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "protocol_risk",
        "Risco de protocolo",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "regulatory_risk",
        "Risco regulatório",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.MACRO_MARKET,
    ),
    catalog_entry(
        "smart_contract_risk",
        "Risco de contrato inteligente",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "concentration_risk",
        "Risco de concentração",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "stablecoin_dependency",
        "Dependência de stablecoins",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="text",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
    catalog_entry(
        "maximum_portfolio_weight",
        "Peso máximo na carteira",
        RISK,
        [InvestmentClass.CRYPTO],
        unit="percent",
        layer=IndicatorLayer.CLASS_SPECIFIC,
    ),
]


MACRO_INDICATOR_REGISTRY = [
    macro_entry("selic", "Selic", "Brasil"),
    macro_entry("cdi", "CDI", "Brasil"),
    macro_entry("ipca", "IPCA", "Brasil"),
    macro_entry("igpm", "IGP-M", "Brasil"),
    macro_entry(
        "brazil_yield_curve",
        "Curva de juros",
        "Brasil",
        unit="text",
        frequency="diária",
    ),
    macro_entry("usd_brl", "Dólar", "Brasil", unit="currency", frequency="diária"),
    macro_entry("ibovespa", "Ibovespa", "Brasil", unit="points", frequency="diária"),
    macro_entry("ifix", "IFIX", "Brasil", unit="points", frequency="diária"),
    macro_entry("fixed_income_indexes", "Índices de renda fixa", "Brasil", unit="text"),
    macro_entry("cpi", "CPI", "Exterior"),
    macro_entry("fed_policy_rate", "Juros do Federal Reserve", "Exterior"),
    macro_entry(
        "treasury_yields",
        "Treasury yields",
        "Exterior",
        unit="percent",
        frequency="diária",
    ),
    macro_entry("sp500", "S&P 500", "Exterior", unit="points", frequency="diária"),
    macro_entry("nasdaq", "Nasdaq", "Exterior", unit="points", frequency="diária"),
    macro_entry(
        "sector_indexes",
        "Índices setoriais",
        "Exterior",
        unit="text",
        frequency="diária",
    ),
    macro_entry("dxy", "Dólar", "Exterior", unit="points", frequency="diária"),
    macro_entry(
        "vix", "Índice de volatilidade", "Exterior", unit="points", frequency="diária"
    ),
    macro_entry(
        "country_risk", "Risco-país", "Exterior", unit="points", frequency="diária"
    ),
]


# Indicadores financeiros de empresas estrangeiras e dos subjacentes de
# BDRs. Só serão AVAILABLE se o provedor entregar os dados de verdade; a
# classe não herda dados da ação brasileira pelo nome do ticker.
GLOBAL_EQUITY_SCORING_KEYS = {
    "roe", "roa", "roic", "price_earnings", "price_book", "ev_ebitda",
    "net_debt_equity", "net_debt_ebitda", "liabilities_assets",
    "current_liquidity", "revenue_cagr_3y", "revenue_cagr_5y",
    "earnings_cagr_3y", "earnings_cagr_5y", "dividend_yield",
}
GLOBAL_EQUITY_INDICATORS = [
    item.model_copy(update={
        "applicable_classes": [InvestmentClass.BDR, InvestmentClass.INTERNATIONAL],
        "required": False,
    })
    for item in STOCK_INDICATORS
    if item.key in GLOBAL_EQUITY_SCORING_KEYS
]


ALL_INDICATORS = [
    *STOCK_INDICATORS,
    *GLOBAL_EQUITY_INDICATORS,
    *FII_INDICATORS,
    *ETF_INDICATORS,
    *TREASURY_INDICATORS,
    *PRIVATE_FIXED_INCOME_INDICATORS,
    *OTHER_CLASS_INDICATORS,
    *ADVANCED_ETF_INDICATORS,
    *ADVANCED_TREASURY_INDICATORS,
    *ADVANCED_FIXED_INCOME_INDICATORS,
    *BDR_INDICATORS,
    *CRYPTO_INDICATORS,
]

INDICATOR_CATALOG: dict[str, IndicatorCatalogEntry] = {}
for item in ALL_INDICATORS:
    INDICATOR_CATALOG.setdefault(item.key, item)


SCORING_CATEGORIES: dict[str, list[str]] = {
    "quality": [
        "roe",
        "roa",
        "roic",
        "property_quality",
        "receivable_quality",
        "tracked_index",
    ],
    "valuation": [
        "price_earnings",
        "price_book",
        "dividend_yield",
        "ev_ebitda",
        "premium_discount",
        "treasury_rate",
    ],
    "debt": [
        "net_debt_equity",
        "net_debt_ebitda",
        "liabilities_assets",
        "debt",
        "fgc_coverage",
    ],
    "income": [
        "dividend_yield",
        "income_12m",
        "last_income",
        "treasury_rate",
        "net_return",
    ],
    "growth": [
        "revenue_cagr_3y",
        "revenue_cagr_5y",
        "earnings_cagr_3y",
        "earnings_cagr_5y",
        "twelve_month_return",
    ],
    "risk": [
        "day_range",
        "physical_vacancy",
        "financial_vacancy",
        "credit_risk",
        "duration",
        "interest_sensitivity",
    ],
    "liquidity": ["volume", "liquidity", "current_liquidity", "redemption_term"],
}


SCORING_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "balanced": {
        "quality": Decimal("25"),
        "valuation": Decimal("20"),
        "debt": Decimal("15"),
        "growth": Decimal("15"),
        "risk": Decimal("10"),
        "liquidity": Decimal("5"),
        "income": Decimal("10"),
    },
    "dividends": {
        "quality": Decimal("20"),
        "valuation": Decimal("15"),
        "debt": Decimal("10"),
        "growth": Decimal("5"),
        "risk": Decimal("10"),
        "liquidity": Decimal("10"),
        "income": Decimal("30"),
    },
    "quality": {
        "quality": Decimal("40"),
        "valuation": Decimal("15"),
        "debt": Decimal("15"),
        "growth": Decimal("10"),
        "risk": Decimal("10"),
        "liquidity": Decimal("5"),
        "income": Decimal("5"),
    },
}


SECTOR_RULES = {
    "banks": {
        "labels": ["banco", "bancos", "financeiro", "instituição financeira"],
        "blocked_indicators": ["ev_ebitda", "net_debt_ebitda", "roic", "ebitda_margin"],
        "message": "Modelo específico para instituições financeiras ainda não disponível.",
    },
    "insurance": {
        "labels": ["seguradora", "seguros"],
        "blocked_indicators": ["ev_ebitda", "net_debt_ebitda", "roic", "ebitda_margin"],
        "message": "Modelo específico para seguradoras ainda não disponível.",
    },
    "holding": {
        "labels": ["holding"],
        "blocked_indicators": ["gross_margin", "ebitda_margin", "asset_turnover"],
        "message": "Modelo específico para holdings ainda não disponível.",
    },
    "industrial": {"labels": ["industrial", "indústria"], "blocked_indicators": []},
    "energy": {"labels": ["energia", "elétrica"], "blocked_indicators": []},
    "commodities": {
        "labels": ["petróleo", "mineração", "commodities"],
        "blocked_indicators": [],
    },
    "technology": {"labels": ["tecnologia"], "blocked_indicators": []},
    "recovery": {"labels": ["recuperação judicial"], "blocked_indicators": []},
    "brick_fii": {"labels": ["tijolo"], "blocked_indicators": []},
    "paper_fii": {"labels": ["papel"], "blocked_indicators": []},
    "hybrid_fii": {"labels": ["híbrido"], "blocked_indicators": []},
    "fiagro": {"labels": ["fiagro"], "blocked_indicators": []},
    "etf": {"labels": ["etf"], "blocked_indicators": []},
    "fixed_income": {"labels": ["renda fixa"], "blocked_indicators": []},
}


def indicators_for_class(asset_class: InvestmentClass) -> list[IndicatorCatalogEntry]:
    return [item for item in ALL_INDICATORS if asset_class in item.applicable_classes]


def keys_for_class(asset_class: InvestmentClass) -> set[str]:
    return {item.key for item in indicators_for_class(asset_class)}


def _pillar(
    key: str,
    *,
    indicator_keys: list[str],
    requirement_mode: str = "ALL_OF",
    importance: IndicatorImportance = IndicatorImportance.REQUIRED,
    applicability: str | None = None,
    description: str | None = None,
) -> IndicatorPillar:
    return IndicatorPillar(
        key=key,
        importance=importance,
        requirement_mode=requirement_mode,
        indicator_keys=indicator_keys,
        applicability=applicability,
        description=description,
    )


def canonical_pillars_for_class(asset_class: InvestmentClass) -> list[IndicatorPillar]:
    if asset_class == InvestmentClass.STOCK:
        return [
            _pillar("price", indicator_keys=["current_price"], requirement_mode="ALL_OF"),
            _pillar(
                "liquidity",
                indicator_keys=["volume", "liquidity"],
                requirement_mode="ANY_OF",
                description="Volume ou liquidez disponível.",
            ),
            _pillar(
                "valuation",
                indicator_keys=["price_earnings", "price_book", "ev_ebitda"],
                requirement_mode="ANY_OF",
                description="Pelo menos um múltiplo de valuation aplicável e disponível.",
            ),
            _pillar(
                "profitability_result",
                indicator_keys=["roe", "roa", "net_margin"],
                requirement_mode="ANY_OF",
                description="Rentabilidade ou margem operacional disponível.",
            ),
            _pillar(
                "capital_structure",
                indicator_keys=["net_debt_equity", "liabilities_assets"],
                requirement_mode="ANY_OF",
                description="Estrutura de capital ou alavancagem disponível.",
            ),
        ]
    if asset_class == InvestmentClass.FII:
        return [
            _pillar("price", indicator_keys=["current_price"], requirement_mode="ALL_OF"),
            _pillar(
                "liquidity",
                indicator_keys=["volume", "liquidity"],
                requirement_mode="ANY_OF",
                description="Liquidez do FII disponível.",
            ),
            _pillar(
                "income",
                indicator_keys=["dividend_yield", "income_12m", "last_income"],
                requirement_mode="ANY_OF",
                description="Rendimento do FII disponível.",
            ),
            _pillar(
                "patrimonial",
                indicator_keys=["price_book", "book_value_per_share"],
                requirement_mode="ANY_OF",
                description="Indicador patrimonial disponível.",
            ),
            _pillar(
                "segment_risk",
                indicator_keys=[
                    "physical_vacancy",
                    "financial_vacancy",
                    "credit_risk",
                    "debtor_concentration",
                ],
                requirement_mode="ANY_OF",
                description=(
                    "Indicador de risco do segmento disponível -- aplicável "
                    "conforme a natureza real do fundo (tijolo: vacância; "
                    "papel: concentração de devedores/emissores)."
                ),
            ),
        ]
    if asset_class == InvestmentClass.ETF:
        return [
            _pillar("price", indicator_keys=["current_price"], requirement_mode="ALL_OF"),
            _pillar(
                "liquidity",
                indicator_keys=["volume", "liquidity"],
                requirement_mode="ANY_OF",
                description="Volume ou liquidez do ETF.",
            ),
            _pillar(
                "strategy",
                indicator_keys=["tracked_index", "fund_strategy"],
                requirement_mode="ANY_OF",
                description="Índice ou estratégia do ETF informados.",
            ),
            _pillar(
                "management_fee",
                indicator_keys=["management_fee"],
                requirement_mode="ALL_OF",
                importance=IndicatorImportance.RECOMMENDED,
                description="Taxa de administração quando publicada.",
            ),
        ]
    if asset_class == InvestmentClass.TREASURY:
        return [
            _pillar("title", indicator_keys=["treasury_title"], requirement_mode="ALL_OF"),
            _pillar("indexer", indicator_keys=["indexer"], requirement_mode="ALL_OF"),
            _pillar("rate", indicator_keys=["treasury_rate"], requirement_mode="ALL_OF"),
            _pillar("maturity", indicator_keys=["maturity_date"], requirement_mode="ALL_OF"),
            _pillar("execution_price", indicator_keys=["current_price"], requirement_mode="ALL_OF"),
        ]
    if asset_class in {InvestmentClass.CDB, InvestmentClass.LCI, InvestmentClass.LCA, InvestmentClass.DEBENTURE}:
        return [
            _pillar("issuer", indicator_keys=["issuer"], requirement_mode="ALL_OF"),
            _pillar(
                "income_model",
                indicator_keys=["indexer", "cdi_percentage", "fixed_rate", "real_rate"],
                requirement_mode="ANY_OF",
            ),
            _pillar("maturity", indicator_keys=["maturity_date"], requirement_mode="ALL_OF"),
            _pillar(
                "liquidity",
                indicator_keys=["liquidity", "lockup"],
                requirement_mode="ANY_OF",
            ),
        ]
    if asset_class == InvestmentClass.BDR:
        return [
            _pillar("price", indicator_keys=["current_price"], requirement_mode="ALL_OF"),
            _pillar(
                "liquidity",
                indicator_keys=["volume", "bdr_liquidity"],
                requirement_mode="ANY_OF",
            ),
            _pillar("underlying", indicator_keys=["underlying_symbol"], requirement_mode="ALL_OF"),
        ]
    if asset_class == InvestmentClass.CRYPTO:
        return [
            _pillar("price", indicator_keys=["price"], requirement_mode="ALL_OF"),
            _pillar(
                "liquidity",
                indicator_keys=["volume", "active_addresses", "network_activity"],
                requirement_mode="ANY_OF",
            ),
            _pillar(
                "risk_history",
                indicator_keys=["volatility", "historical_return", "maximum_drawdown"],
                requirement_mode="ANY_OF",
                description="Histórico suficiente para risco/volatilidade.",
            ),
        ]
    return []


def indicator_temporal_validity_days(key: str) -> int | None:
    market_price = {"current_price", "daily_change", "volume", "liquidity"}
    treasury_market_rate = {"treasury_rate", "real_rate", "current_rate"}
    fundamental_quarterly = {
        "price_earnings",
        "price_book",
        "dividend_yield",
        "roe",
        "roa",
        "roic",
        "ebitda_margin",
        "net_margin",
    }
    fundamental_annual = {
        "revenue_cagr_3y",
        "earnings_cagr_3y",
        "income_cagr_3y",
        "quote_cagr_3y",
        "revenue_cagr_5y",
        "earnings_cagr_5y",
        "income_cagr_5y",
        "quote_cagr_5y",
    }
    structural = {"sector", "subsector", "segment", "governance_level", "country", "currency", "indexers"}
    registration = {"treasury_title", "indexer", "maturity_date"}
    if key in market_price:
        return 2
    if key in treasury_market_rate:
        return 2
    if key in fundamental_quarterly:
        return 90
    if key in fundamental_annual:
        return 365
    if key in registration:
        return 3650
    if key in structural:
        return 3650
    return None


def evaluate_indicator_pillar(pillar: IndicatorPillar, indicators: list) -> dict:
    lookup = {item.key: item for item in indicators if getattr(item, "key", None)}
    declared = list(pillar.indicator_keys)
    available = []
    effective = []
    missing = []
    not_applicable = []
    applicable = []

    for indicator_key in declared:
        item = lookup.get(indicator_key)
        if item is not None and item.status == IndicatorStatus.NOT_APPLICABLE:
            not_applicable.append(indicator_key)
            continue

        applicable.append(indicator_key)

        if item is None:
            missing.append(indicator_key)
            continue

        effective.append(indicator_key)
        if item.status == IndicatorStatus.AVAILABLE:
            available.append(indicator_key)
        else:
            missing.append(indicator_key)

    if pillar.requirement_mode == "ALL_OF":
        satisfied = bool(applicable) and all(key in available for key in applicable)
    else:
        satisfied = bool(applicable) and bool(available)

    return {
        "key": pillar.key,
        "requirement_mode": pillar.requirement_mode,
        "available": available,
        "effective_indicators": effective,
        "missing_indicators": missing,
        "not_applicable_indicators": not_applicable,
        "satisfied": satisfied,
        "coverage": Decimal("100") if satisfied else Decimal("0"),
    }


def _pillar_applicable_count(pillar: IndicatorPillar, evaluation: dict) -> int:
    return len(pillar.indicator_keys) - len(evaluation["not_applicable_indicators"])


def pillar_group_coverage(
    pillars: list[IndicatorPillar], indicators: list[NormalizedIndicator]
) -> tuple[Decimal | None, int, int]:
    """Cobertura de um grupo de pilares: satisfeitos / aplicáveis.

    Um pilar cujos membros declarados são todos NOT_APPLICABLE para o ativo
    não entra no denominador (não é "aplicável"). Retorna (None, 0, 0)
    quando nenhum pilar do grupo é aplicável, nunca 0/0.
    """
    total = 0
    satisfied = 0
    for pillar in pillars:
        evaluation = evaluate_indicator_pillar(pillar, indicators)
        if _pillar_applicable_count(pillar, evaluation) <= 0:
            continue
        total += 1
        if evaluation["satisfied"]:
            satisfied += 1
    if total == 0:
        return None, satisfied, total
    coverage = (Decimal(satisfied) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))
    return coverage, satisfied, total


def scoring_coverage_for_indicators(
    indicators: list[NormalizedIndicator],
    *,
    asset_class: InvestmentClass | None = None,
) -> tuple[Decimal | None, int, int]:
    """Cobertura restrita aos indicadores/categorias que alimentam o score financeiro.

    Não considera nome, ticker, descrição ou metadados de apresentação: apenas
    chaves declaradas em SCORING_CATEGORIES. NOT_APPLICABLE é excluído do denominador.
    """
    # Classes globais não devem medir confiança por categorias domésticas.
    if asset_class in {
        InvestmentClass.BDR, InvestmentClass.INTERNATIONAL,
        InvestmentClass.CRYPTO, InvestmentClass.ETF,
    }:
        from app.engines.multimarket_scoring import specialized_categories
        mapping = specialized_categories(asset_class)
        scoring_keys = {key for keys in mapping.values() for key in keys}
    else:
        scoring_keys = {key for keys in SCORING_CATEGORIES.values() for key in keys}
    relevant = [
        item
        for item in indicators
        if item.key in scoring_keys and item.status != IndicatorStatus.NOT_APPLICABLE
    ]
    if not relevant:
        return None, 0, 0
    available = sum(1 for item in relevant if item.status == IndicatorStatus.AVAILABLE)
    coverage = (Decimal(available) / Decimal(len(relevant)) * Decimal("100")).quantize(Decimal("0.01"))
    return coverage, available, len(relevant)


def provider_coverage_for_indicators(
    indicators: list[NormalizedIndicator],
) -> tuple[Decimal | None, int, int]:
    """Diagnóstico de resolução: quantos indicadores solicitados o provedor devolveu.

    Diferente de required/recommended/total_coverage: conta STALE como resolvido
    (o provedor entregou algo, mesmo que hoje esteja desatualizado). NUNCA deve
    ser usado sozinho para bloquear uma análise — é apenas diagnóstico.
    """
    requested = [item for item in indicators if item.status != IndicatorStatus.NOT_APPLICABLE]
    if not requested:
        return None, 0, 0
    resolved = sum(
        1
        for item in requested
        if item.status in {IndicatorStatus.AVAILABLE, IndicatorStatus.STALE}
    )
    coverage = (Decimal(resolved) / Decimal(len(requested)) * Decimal("100")).quantize(Decimal("0.01"))
    return coverage, resolved, len(requested)


def coverage_breakdown_for_asset(
    asset_class: InvestmentClass, indicators: list[NormalizedIndicator]
) -> CoverageBreakdown:
    """Constrói a cobertura desmembrada (P1) para um ativo, sem alterar coverage_percentage legado."""
    pillars = canonical_pillars_for_class(asset_class)
    required_pillars = [p for p in pillars if p.importance == IndicatorImportance.REQUIRED]
    recommended_pillars = [p for p in pillars if p.importance == IndicatorImportance.RECOMMENDED]
    optional_pillars = [p for p in pillars if p.importance == IndicatorImportance.OPTIONAL]
    # EXPERIMENTAL é deliberadamente excluído de total_coverage: não deve
    # reduzir a cobertura normal exibida ao usuário.
    total_pillars = required_pillars + recommended_pillars + optional_pillars

    required_coverage, required_satisfied, required_total = pillar_group_coverage(
        required_pillars, indicators
    )
    recommended_coverage, recommended_satisfied, recommended_total = pillar_group_coverage(
        recommended_pillars, indicators
    )
    total_coverage, total_available, total_applicable = pillar_group_coverage(
        total_pillars, indicators
    )
    scoring_coverage, scoring_available, scoring_total = scoring_coverage_for_indicators(
        indicators, asset_class=asset_class
    )
    provider_coverage, provider_resolved, provider_requested = provider_coverage_for_indicators(
        indicators
    )

    return CoverageBreakdown(
        required_coverage=required_coverage,
        required_satisfied=required_satisfied,
        required_total=required_total,
        recommended_coverage=recommended_coverage,
        recommended_satisfied=recommended_satisfied,
        recommended_total=recommended_total,
        scoring_coverage=scoring_coverage,
        scoring_available=scoring_available,
        scoring_total=scoring_total,
        total_coverage=total_coverage,
        total_available=total_available,
        total_applicable=total_applicable,
        provider_coverage=provider_coverage,
        provider_resolved=provider_resolved,
        provider_requested=provider_requested,
    )


def is_indicator_not_applicable(key: str, *, sector: str | None = None, asset_class: InvestmentClass | None = None) -> bool:
    if sector is not None:
        key_profile = ascii_key(sector)
        if key_profile and key in {"ev_ebitda", "net_debt_ebitda", "roic", "ebitda_margin"}:
            if "banco" in key_profile or "segur" in key_profile:
                return True
    return False


def ascii_key(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return text
