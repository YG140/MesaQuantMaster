from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import settings
from app.engines.intelligence_engine import (
    PortfolioBuilderEngine,
    PortfolioIntelligenceEngine,
)
from app.engines.smart_portfolio_engine import PortfolioCandidate, PortfolioHolding, SmartPortfolioEngine
from app.engines.sector_relative_valuation import PeerAsset, enrich_sector_valuations
from app.models.portfolio_policy import PortfolioPolicy, PortfolioPolicyAllocation
from app.repositories.portfolio_policy_repository import PortfolioPolicyRepository
from app.repositories.asset_repository import AssetRepository
from app.schemas.intelligence import (
    BuildPortfolioRequest,
    BuildPortfolioResponse,
    PortfolioIntelligenceResponse,
    PortfolioPolicyAllocationRead,
    PortfolioPolicyRead,
    PortfolioPolicyUpsert,
)
from app.services.portfolio_service import PortfolioService
from app.services.market_intelligence_service import MarketIntelligenceService
from app.services.symbol_identity import (
    B3_MARKET,
    market_context_of,
    resolve_symbol_identity,
)
from app.schemas.market_intelligence import AnalyzeAssetsRequest


# Espelha AnalyzeAssetsRequest.symbols (max_length=50 em
# app/schemas/market_intelligence.py) — o limite real de símbolos aceitos
# por chamada ao analisador/resolver. Não é um número mágico independente:
# se o schema mudar, os lotes passam a violar essa constante nos testes.
MAX_SYMBOLS_PER_ANALYSIS_BATCH = 50


class PortfolioIntelligenceService:
    def __init__(
        self,
        portfolio_service: PortfolioService,
        policy_repository: PortfolioPolicyRepository,
        asset_repository: AssetRepository | None = None,
        market_intelligence_service: MarketIntelligenceService | None = None,
    ):
        self.portfolio_service = portfolio_service
        self.policy_repository = policy_repository
        self.asset_repository = asset_repository
        self.market_intelligence_service = market_intelligence_service

    def get_policy(self, user_id) -> PortfolioPolicyRead | None:
        policy = self.policy_repository.get_by_user(user_id)
        return self._policy_to_schema(policy) if policy is not None else None

    def save_policy(self, user_id, data: PortfolioPolicyUpsert) -> PortfolioPolicyRead:
        now = datetime.now(timezone.utc)
        policy = self.policy_repository.get_by_user(user_id)
        if policy is None:
            policy = PortfolioPolicy(
                user_id=user_id,
                created_at=now,
                updated_at=now,
                name=data.name,
                objective=data.objective,
                risk_profile=data.risk_profile,
                investment_horizon=data.investment_horizon,
                monthly_contribution=data.monthly_contribution,
                liquidity_need=data.liquidity_need,
                income_need=data.income_need,
                emergency_reserve_months=data.emergency_reserve_months,
                maximum_weight_per_asset=data.maximum_weight_per_asset,
                maximum_weight_per_sector=data.maximum_weight_per_sector,
                maximum_weight_per_issuer=data.maximum_weight_per_issuer,
                rebalance_tolerance=data.rebalance_tolerance,
            )
            policy = self.policy_repository.save(policy)
        else:
            policy.name = data.name
            policy.objective = data.objective
            policy.risk_profile = data.risk_profile
            policy.investment_horizon = data.investment_horizon
            policy.monthly_contribution = data.monthly_contribution
            policy.liquidity_need = data.liquidity_need
            policy.income_need = data.income_need
            policy.emergency_reserve_months = data.emergency_reserve_months
            policy.maximum_weight_per_asset = data.maximum_weight_per_asset
            policy.maximum_weight_per_sector = data.maximum_weight_per_sector
            policy.maximum_weight_per_issuer = data.maximum_weight_per_issuer
            policy.rebalance_tolerance = data.rebalance_tolerance
            policy.updated_at = now

        allocations = [
            PortfolioPolicyAllocation(
                asset_class=item.asset_class,
                target_percentage=item.target_percentage,
                minimum_percentage=item.minimum_percentage,
                maximum_percentage=item.maximum_percentage,
                enabled=item.enabled,
            )
            for item in data.allocations
        ]
        saved = self.policy_repository.replace_allocations(policy, allocations)
        return self._policy_to_schema(saved)

    def get_portfolio_intelligence(self, user_id) -> PortfolioIntelligenceResponse:
        portfolio = self.portfolio_service.calculate(user_id)
        policy = self.get_policy(user_id)
        return PortfolioIntelligenceEngine.build(portfolio, policy)

    def build_portfolio(
        self, user_id, data: BuildPortfolioRequest
    ) -> BuildPortfolioResponse:
        # user_id vem exclusivamente do usuário autenticado (ver
        # app/api/intelligence.py, current_user.id) -- nunca do corpo da
        # requisição. Uma PortfolioPolicy persistida (via onboarding do
        # Perfil do Investidor OU via PUT/POST /policy diretos -- ambos
        # igualmente autoritativos; o modelo não persiste campo de
        # provenance, então não há como distinguir a origem) passa a ser
        # a fonte estratégica de verdade
        # de build_portfolio() (ver SmartPortfolioEngine.build/
        # PortfolioStrategy). Ausência de política preserva o
        # comportamento legado integralmente (policy=None) -- inclusive
        # quando policy_repository não foi injetado (mesmo padrão
        # defensivo já usado para asset_repository/
        # market_intelligence_service abaixo).
        policy = self.get_policy(user_id) if self.policy_repository is not None else None
        if self.asset_repository is None or self.market_intelligence_service is None:
            return SmartPortfolioEngine.build(data, [], policy=policy)

        # Apenas posições persistidas pelo usuário autenticado. O frontend não
        # pode forjar holdings para alterar limites e pareceres.
        portfolio = (
            self.portfolio_service.calculate(user_id)
            if self.portfolio_service is not None else None
        )
        persisted_positions = portfolio.positions if portfolio is not None else []
        held_symbols = {position.ticker.upper() for position in persisted_positions}

        # Ordenamos explicitamente por ticker (chave estável) em vez de
        # confiar na ordem implícita do repositório, para que o universo e o
        # resultado sejam sempre reproduzíveis. Deduplicamos por ticker e
        # filtramos inativos na mesma passagem.
        seen_tickers: set[str] = set()
        active_assets = []
        for item in sorted(self.asset_repository.list(), key=lambda asset: asset.ticker):
            if not item.is_active:
                continue
            ticker = item.ticker.upper()
            if ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            active_assets.append(item)

        universe_total = len(active_assets)
        universe_max = settings.PORTFOLIO_UNIVERSE_MAX_ASSETS
        universe_truncated = universe_total > universe_max
        # Prioridade de cobertura para posições reais se houver truncamento:
        # um ativo já registrado não pode ser deixado sem análise apenas
        # porque seu ticker vem depois dos primeiros N alfabeticamente.
        # Sem carteira cadastrada, preserva-se a ordem legada integral.
        if held_symbols and universe_truncated:
            prioritized = sorted(
                active_assets,
                key=lambda asset: (asset.ticker.upper() not in held_symbols, asset.ticker),
            )
            considered_assets = prioritized[:universe_max]
        else:
            considered_assets = active_assets[:universe_max] if universe_truncated else active_assets
        universe_considered = len(considered_assets)

        if not considered_assets:
            legacy = PortfolioBuilderEngine.build(data, policy)
            return legacy.model_copy(
                update={
                    "unallocated_amount": data.available_amount.quantize(
                        Decimal("0.01")
                    ),
                    "missing_data": [
                        "Nenhum ativo cadastrado está disponível para análise."
                    ],
                    "strategy_summary": (
                        "Metas por classe exibidas; seleção indisponível por ausência de ativos."
                    ),
                }
            )

        # Universo processado em lotes determinísticos (mesma ordem por
        # ticker), nunca truncado silenciosamente acima de universe_max.
        batches = [
            considered_assets[index : index + MAX_SYMBOLS_PER_ANALYSIS_BATCH]
            for index in range(0, universe_considered, MAX_SYMBOLS_PER_ANALYSIS_BATCH)
        ]

        snapshots = []
        errors = []
        for batch in batches:
            result = self.market_intelligence_service.analyze_assets(
                AnalyzeAssetsRequest(symbols=[item.ticker for item in batch]),
                user_id=user_id,
            )
            snapshots.extend(result.snapshots)
            errors.extend(result.errors)

        # Contexto de mercado do provider REALMENTE em uso nesta chamada
        # (ver market_context_of) -- calculado uma única vez aqui, nunca
        # assumido como "B3" implicitamente dentro de _issuer_identity.
        # getattr encadeado com default: resiliente a duplos de teste que
        # não expõem market_service/provider (resulta em None, nunca
        # aciona a regra do fracionário B3).
        market_context = market_context_of(
            getattr(
                getattr(self.market_intelligence_service, "market_service", None),
                "provider",
                None,
            )
        )
        assets_by_symbol = {item.ticker.upper(): item for item in considered_assets}
        candidates = []
        for snapshot in snapshots:
            asset = assets_by_symbol.get(snapshot.symbol.upper())
            candidates.append(
                PortfolioCandidate(
                    snapshot=snapshot,
                    sector=asset.sector if asset else None,
                    issuer=self._issuer_identity(
                        asset, snapshot, market_context=market_context
                    ),
                    market_context=(
                        getattr(asset, "exchange", None) or market_context
                    ),
                )
            )
        # Reunir todo o universo, inclusive lotes distintos, para comparar
        # somente emissores reais do mesmo setor. Não alterar a identidade
        # ou o limite de concentração de cada candidato.
        enriched = enrich_sector_valuations([
            PeerAsset(snapshot=candidate.snapshot, sector=candidate.sector, issuer=candidate.issuer)
            for candidate in candidates
        ])
        candidates = [
            PortfolioCandidate(
                snapshot=enriched.get(candidate.snapshot.symbol, candidate.snapshot),
                sector=candidate.sector, issuer=candidate.issuer,
                market_context=candidate.market_context,
            )
            for candidate in candidates
        ]
        # A posição vale a cotação somente quando disponível. Sem ela, o
        # custo registrado é um proxy explícito, nunca um preço inventado.
        # O setor/emissor são resolvidos pelo cadastro do ativo, não pelo
        # texto livre enviado na requisição de montagem.
        holdings = []
        candidate_by_symbol = {
            candidate.snapshot.symbol.upper(): candidate for candidate in candidates
        }
        all_assets_by_symbol = {asset.ticker.upper(): asset for asset in active_assets}
        for position in persisted_positions:
            symbol = position.ticker.upper()
            asset = all_assets_by_symbol.get(symbol)
            analyzed = candidate_by_symbol.get(symbol)
            current_value = position.market_value
            has_quote = current_value is not None and current_value > 0
            value = current_value if has_quote else position.invested_amount
            if value is None or value <= 0:
                continue
            raw_class = (
                SmartPortfolioEngine.class_label(analyzed.snapshot.asset_class)
                if analyzed else self._registered_asset_class(position.asset_type)
            )
            holdings.append(PortfolioHolding(
                symbol=symbol,
                quantity=position.quantity,
                value=value,
                valuation_basis="market" if has_quote else "invested",
                asset_class=raw_class,
                sector=getattr(asset, "sector", None),
                issuer=(
                    analyzed.issuer if analyzed else
                    self._issuer_identity(asset, None, market_context=market_context)
                    if asset is not None else None
                ),
            ))
        return SmartPortfolioEngine.build(
            data,
            candidates,
            policy=policy,
            holdings=holdings,
            provider_errors=[item.message for item in errors],
            universe_total=universe_total,
            universe_considered=universe_considered,
            universe_truncated=universe_truncated,
            batch_size=MAX_SYMBOLS_PER_ANALYSIS_BATCH,
            batch_count=len(batches),
        )

    @staticmethod
    def _registered_asset_class(asset_type: str | None) -> str | None:
        mapping = {
            "stock": "Ações", "acao": "Ações", "ações": "Ações",
            "fii": "FIIs", "etf": "ETFs", "bdr": "BDRs",
            "treasury": "Tesouro Direto", "cdb": "Renda fixa bancária",
            "lci": "Renda fixa bancária", "lca": "Renda fixa bancária",
            "crypto": "Criptomoedas",
        }
        return mapping.get((asset_type or "").strip().casefold())

    @staticmethod
    def _issuer_identity(asset, snapshot, *, market_context: str | None) -> str | None:
        """Chave de identidade de emissor usada por
        `SmartPortfolioEngine.allocate` para `maximum_weight_per_issuer`.

        Antes desta correção era `asset.name` (nome de exibição bruto).
        Isso não é uma identidade de emissor confiável: dois nomes
        ligeiramente diferentes para a MESMA empresa (ex.: o `shortName`
        que a BRAPI retorna para o mercado fracionário B3 é literalmente
        o próprio ticker -- "PETR4F", não "Petroleo Brasileiro SA Pfd")
        fariam o motor tratar PETR4 e PETR4F como dois emissores
        independentes para fins de concentração (ver auditoria Prompt 1,
        seção I).

        A chave é NAMESPACED por mercado comprovado, nunca só
        `canonical_symbol` sozinho -- um `canonical_symbol` idêntico ("PETR4")
        obtido em dois mercados DIFERENTES nunca pode colidir na mesma
        chave de emissor (ticker nunca é identidade global única, ver
        auditoria Prompt 1 seção 4). O mercado usado é, em ordem de
        prioridade:

        1. `asset.exchange`, se já persistido no próprio Asset -- é a
           identidade mais estável, independente de qual provider
           respondeu a ESTA chamada específica.
        2. `market_context` (mercado do provider realmente em uso nesta
           chamada, ver market_context_of), quando o Asset não tem
           exchange conhecido.

        A canonicalização do fracionário só é aplicada quando esse
        mercado resolvido é EXATAMENTE B3_MARKET -- nunca por suposição.
        Sem nenhum mercado comprovado (nem exchange nem contexto), o
        fallback é o `canonical_symbol` isolado, sem namespace --
        idêntico ao comportamento anterior, conservador.

        Não resolve o caso pré-existente e mais amplo de classes
        diferentes do MESMO emissor CVM com canonical_symbol distinto
        (ex.: PETR3 vs PETR4) -- isso exigiria vincular cada candidato ao
        issuer_id/CNPJ oficial já resolvido, plumbing que build_portfolio
        não tem hoje (nem asset_repository nem market_intelligence_service
        expõem cvm_repository aqui) e que está fora do escopo desta
        correção especificamente sobre ações fracionárias B3.
        """
        ticker = asset.ticker if asset is not None else snapshot.symbol
        if not ticker:
            return None

        exchange = getattr(asset, "exchange", None) or market_context
        resolution_market = exchange if exchange == B3_MARKET else None
        canonical_symbol = resolve_symbol_identity(
            ticker, market=resolution_market
        ).canonical_symbol

        if not exchange:
            return canonical_symbol
        return f"{exchange}:{canonical_symbol}"

    @staticmethod
    def _policy_to_schema(policy: PortfolioPolicy) -> PortfolioPolicyRead:
        return PortfolioPolicyRead(
            id=policy.id,
            user_id=policy.user_id,
            name=policy.name,
            objective=policy.objective,
            risk_profile=policy.risk_profile,
            investment_horizon=policy.investment_horizon,
            monthly_contribution=policy.monthly_contribution,
            liquidity_need=policy.liquidity_need,
            income_need=policy.income_need,
            emergency_reserve_months=policy.emergency_reserve_months,
            maximum_weight_per_asset=policy.maximum_weight_per_asset,
            maximum_weight_per_sector=policy.maximum_weight_per_sector,
            maximum_weight_per_issuer=policy.maximum_weight_per_issuer,
            rebalance_tolerance=policy.rebalance_tolerance,
            allocations=[
                PortfolioPolicyAllocationRead(
                    id=allocation.id,
                    asset_class=allocation.asset_class,
                    target_percentage=allocation.target_percentage,
                    minimum_percentage=allocation.minimum_percentage,
                    maximum_percentage=allocation.maximum_percentage,
                    enabled=allocation.enabled,
                )
                for allocation in policy.allocations
            ],
            created_at=policy.created_at,
            updated_at=policy.updated_at,
        )
