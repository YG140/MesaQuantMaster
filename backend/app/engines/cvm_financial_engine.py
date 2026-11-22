from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.providers.cvm_open_data_provider import CvmRawAccount


class CvmFinancialEngine:
    """Mapeamento explícito de contas fixas CVM; não acessa banco ou rede."""

    # Chaves alinhadas ao contrato canônico de app.engines.indicator_catalog:
    # itens de balanço/DRE que possuem indicador de catálogo correspondente
    # usam o MESMO nome (assets, cash_and_equivalents, equity, current_assets,
    # current_liabilities, gross_debt) para que _apply_cvm() consiga casar o
    # valor com o indicador certo. Itens sem indicador de catálogo próprio
    # (total_liabilities_and_equity, revenue, net_income etc.) mantêm nome descritivo —
    # servem apenas como componentes de entrada para DerivedIndicatorEngine,
    # nunca são publicados como indicador autônomo.
    ACCOUNT_MAP = {
        ("BPA", "1"): "assets",
        ("BPA", "1.01"): "current_assets",
        ("BPA", "1.01.01"): "cash_and_equivalents",
        ("BPP", "2"): "total_liabilities_and_equity",
        ("BPP", "2.01"): "current_liabilities",
        ("BPP", "2.03"): "equity",
        ("BPP", "2.01.04"): "gross_debt",
        ("BPP", "2.02.01"): "gross_debt",
        ("DRE", "3.01"): "revenue",
        ("DRE", "3.03"): "gross_profit",
        ("DRE", "3.05"): "ebit",
        ("DRE", "3.06"): "financial_result",
        ("DRE", "3.11"): "net_income",
        ("DFC_MD", "6.01"): "operating_cash_flow",
        ("DFC_MI", "6.01"): "operating_cash_flow",
        ("DFC_MD", "6.02"): "investing_cash_flow",
        ("DFC_MI", "6.02"): "investing_cash_flow",
        ("DFC_MD", "6.03"): "financing_cash_flow",
        ("DFC_MI", "6.03"): "financing_cash_flow",
        ("DFC_MD", "6.05"): "cash_change",
        ("DFC_MI", "6.05"): "cash_change",
    }

    @classmethod
    def normalized_key(cls, account: CvmRawAccount) -> str | None:
        if not account.is_fixed_account:
            return None
        return cls.ACCOUNT_MAP.get((account.statement_type, account.account_code))

    @classmethod
    def aggregate(cls, accounts: list) -> dict[str, Decimal]:
        values: dict[str, Decimal] = {}
        for account in accounts:
            if not account.normalized_key:
                continue
            values[account.normalized_key] = values.get(
                account.normalized_key, Decimal("0")
            ) + Decimal(account.normalized_value)
        return values

    # Allowlist defensiva de contas de fluxo que podem ser isoladas.
    # Os códigos correspondem às contas fixas mapeadas explicitamente acima;
    # ampliar esta lista exige conferência do plano de contas/dicionário CVM.
    FLOW_ACCOUNT_CODES = {
        "DRE": frozenset({"3.01", "3.03", "3.05", "3.06", "3.11"}),
        "DFC_MD": frozenset({"6.01", "6.02", "6.03", "6.05"}),
        "DFC_MI": frozenset({"6.01", "6.02", "6.03", "6.05"}),
    }

    @staticmethod
    def isolated_quarter(
        current: CvmRawAccount, previous: CvmRawAccount | None
    ) -> CvmRawAccount | None:
        allowed_codes = CvmFinancialEngine.FLOW_ACCOUNT_CODES.get(
            current.statement_type, frozenset()
        )
        if current.account_code not in allowed_codes:
            return None
        if (
            previous is None
            or current.document_type != "ITR"
            or current.statement_type not in {"DRE", "DFC_MD", "DFC_MI"}
            or current.period_start is None
            or previous.period_start != current.period_start
            or previous.period_end >= current.period_end
            # ITR YTD só permite isolar um trimestre contra o trimestre
            # imediatamente anterior. Pular um período produziria, por
            # exemplo, seis meses rotulados incorretamente como um trimestre.
            or (
                current.period_end.year * 12
                + current.period_end.month
                - previous.period_end.year * 12
                - previous.period_end.month
                != 3
            )
            or previous.cnpj != current.cnpj
            or previous.account_code != current.account_code
            or previous.scope != current.scope
        ):
            return None
        return replace(
            current,
            original_value=current.original_value - previous.original_value,
            normalized_value=current.normalized_value - previous.normalized_value,
            period_start=previous.period_end,
            period_kind="quarterly_calculated",
        )
