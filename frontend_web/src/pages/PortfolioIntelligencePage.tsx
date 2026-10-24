import { ResponsiveTable } from "../components/ui/ResponsiveTable";
import { EmergencyReserveBuilder } from "./EmergencyReserveBuilder";
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { ScoreGauge } from "../components/ui/ScoreGauge";
import { SectionHeader } from "../components/ui/SectionHeader";
import { useAuth } from "../features/auth/useAuth";
import {
  continueOrReviewInvestorProfile,
  investorProfileActionLabel,
  investorProfileHorizonLabel,
  investorProfileLiquidityLabel,
  investorProfileObjectiveLabel,
  investorProfileRiskLabel,
  investorProfileStatusLabel,
} from "../features/investorProfile/presentation";
import { ApiError } from "../services/apiClient";
import { endpoints } from "../services/endpoints/data";
import { investorProfileEndpoints } from "../services/endpoints/investorProfile";
import type {
  AssetIntelligenceSnapshot,
  BuildPortfolioResponse,
  PortfolioIntelligence,
} from "../types/api";
import {
  formatDateTimeBR,
  formatDecimalBR,
  formatMoney,
  formatPercent,
  formatQuantityBR,
  normalizeDecimalForApi,
  parseBrazilianNumber,
} from "../utils/formatters";

/** A cotação do mercado internacional NÃO é convertida implicitamente em BRL. */
function formatPriceWithCurrency(value: string | number | null, currency: string | null) {
  if (!currency || currency === "BRL") return formatMoney(value);
  const amount = parseBrazilianNumber(value);
  if (amount === null || !Number.isFinite(amount)) return "Indisponível";
  if (!/^[A-Z]{3}$/.test(currency)) return `${formatDecimalBR(amount, 2)} ${currency}`;
  try {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(amount);
  } catch {
    return `${formatDecimalBR(amount, 2)} ${currency}`;
  }
}

const areas = ["Diagnóstico", "Montar carteira", "Reserva", "Futuro financeiro"] as const;
type IntelligenceArea = (typeof areas)[number];
export function PortfolioIntelligencePage() {
  const { token } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSection = searchParams.get("secao");
  const area: IntelligenceArea = requestedSection === "montar-carteira"
    ? "Montar carteira"
    : requestedSection === "reserva"
      ? "Reserva"
      : requestedSection === "futuro-financeiro"
        ? "Futuro financeiro"
        : "Diagnóstico";
  const intelligence = useQuery({
    queryKey: ["portfolio-intelligence", token],
    queryFn: () => endpoints.portfolioIntelligence(token!),
    // Consulta pesada só quando a aba Diagnóstico está ativa.
    enabled: Boolean(token) && area === "Diagnóstico",
    retry: false,
    staleTime: 30_000,
  });

  // Resiliência (Correção interface): o shell da página, as abas, o Perfil
  // do Investidor e as áreas "Montar carteira"/"Futuro financeiro" NUNCA
  // dependem de intelligence.data -- cada uma busca (ou não precisa de)
  // seus próprios dados de forma independente (ver BuildPortfolio, que
  // agora busca portfolio-policy diretamente em vez de receber via prop;
  // Strategy/FutureFinancial já eram independentes). Só o conteúdo da aba
  // "Diagnóstico" que realmente depende de /intelligence/portfolio fica
  // condicionado ao estado dessa query, isoladamente (ver
  // IntelligenceDependentSections).
  return (
    <div className={`page-stack planning-prism-page planning-${requestedSection ?? "diagnostico"}`}>
      <SectionHeader eyebrow="Planejar" title="Inteligência de Carteira" description="Diagnóstico, carteira, reserva de emergência e futuro financeiro no mesmo lugar." />
      <InvestorProfileSummary />
      <div className="tabs intelligence-areas" role="tablist" aria-label="Áreas de inteligência">
        {areas.map((item) => (
          <button key={item} type="button" role="tab" aria-selected={item === area} className={item === area ? "active" : ""} onClick={() => setSearchParams(item === "Montar carteira" ? { secao: "montar-carteira" } : item === "Reserva" ? { secao: "reserva" } : item === "Futuro financeiro" ? { secao: "futuro-financeiro" } : { secao: "diagnostico" })}>
            {item}
          </button>
        ))}
      </div>
      {area === "Diagnóstico" ? <IntelligenceDependentSections intelligence={intelligence} /> : null}
      {area === "Montar carteira" ? <BuildPortfolio /> : null}
      {area === "Reserva" ? <EmergencyReserveBuilder /> : null}
      {area === "Futuro financeiro" ? <div className="intelligence-sections">
        <details open><summary>Minha meta e projeções</summary><FutureFinancial /></details>
        <details><summary>Estratégia do Perfil do Investidor</summary><Strategy /></details>
      </div> : null}
    </div>
  );
}

function IntelligenceDependentSections({ intelligence }: { intelligence: UseQueryResult<PortfolioIntelligence, unknown> }) {
  const [opportunitiesOpen, setOpportunitiesOpen] = useState(false);
  return (
    <div className="intelligence-sections">
      {intelligence.isLoading ? <LoadingState label="Carregando inteligência da carteira..." /> : null}
      {intelligence.error ? (
        <ErrorState message={describeIntelligenceError(intelligence.error)}>
          <Button type="button" variant="secondary" onClick={() => intelligence.refetch()} disabled={intelligence.isFetching}>
            {intelligence.isFetching ? "Tentando novamente..." : "Tentar novamente"}
          </Button>
        </ErrorState>
      ) : null}
      {!intelligence.isLoading && !intelligence.error && !intelligence.data ? (
        <EmptyState title="Dados insuficientes para calcular." />
      ) : null}
      {intelligence.data ? (
        <>
          <details open><summary>Como está minha carteira?</summary><Diagnosis data={intelligence.data} /></details>
          <details><summary>Todos os números da carteira</summary><Overview data={intelligence.data} /></details>
          <details><summary>Recomendações</summary><Recommendations data={intelligence.data} /></details>
          <details><summary>Rebalanceamento</summary><Rebalancing data={intelligence.data} /></details>
        </>
      ) : null}
      {/* Oportunidades gerencia seu próprio estado (query independente, ver
          MarketOpportunities) -- nunca escondida só porque o restante do
          diagnóstico falhou. */}
      <details onToggle={(event) => setOpportunitiesOpen(event.currentTarget.open)}>
        <summary>Oportunidades relacionadas à carteira</summary>
        {opportunitiesOpen ? <MarketOpportunities /> : null}
      </details>
    </div>
  );
}

function describeIntelligenceError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Não foi possível conectar à API. Verifique sua conexão e tente novamente.";
  if (error.code === "VALIDATION") return `Há um problema nos dados da sua carteira: ${error.message}`;
  if (error.code === "NOT_FOUND") return "Não encontramos as informações necessárias para calcular sua carteira.";
  if (error.code === "TIMEOUT") return "A consulta demorou mais que o esperado. Tente novamente.";
  if (error.code === "NETWORK") return "Não foi possível conectar à API. Verifique sua conexão.";
  if (error.code === "SERVER" || error.code === "BAD_GATEWAY") return "Ocorreu um erro interno ao calcular sua carteira. Tente novamente em instantes.";
  if (error.code === "UNAUTHORIZED") return "Sua sessão expirou. Entre novamente.";
  return "Não foi possível carregar a inteligência da carteira agora.";
}

function describeInvestorProfileError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Não foi possível consultar seu perfil agora. Verifique a conexão com o servidor.";
  if (error.code === "TIMEOUT") return "A consulta do perfil demorou demais. Confira a conexão com o servidor e tente novamente.";
  if (error.code === "NETWORK") return "Não foi possível conectar ao servidor para consultar o perfil.";
  if (error.code === "UNAUTHORIZED") return "Sua sessão expirou. Entre novamente para consultar seu perfil.";
  if (error.status !== null && error.status >= 500) return "O servidor não conseguiu carregar o perfil. Verifique o backend e o banco de dados.";
  if (error.code === "SERVER" || error.code === "BAD_GATEWAY") return "O servidor não conseguiu carregar o perfil. Verifique o backend e o banco de dados.";
  return "Não foi possível consultar seu perfil agora. Tente novamente.";
}

function InvestorProfileSummary() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const investorProfile = useQuery({
    queryKey: ["investor-profile", token],
    queryFn: () => investorProfileEndpoints.get(token!),
    enabled: Boolean(token),
    retry: false,
  });

  async function continueOrReview() {
    if (!token) return;
    await continueOrReviewInvestorProfile(token, investorProfile.data?.status, navigate);
  }

  return (
    <Card title="Perfil do Investidor" className="investor-profile-summary">
      {investorProfile.isLoading ? <LoadingState label="Consultando seu perfil..." /> : null}
      {investorProfile.error ? (
        <ErrorState message={describeInvestorProfileError(investorProfile.error)}>
          <Button type="button" variant="secondary" onClick={() => investorProfile.refetch()} disabled={investorProfile.isFetching}>
            {investorProfile.isFetching ? "Tentando novamente..." : "Tentar novamente"}
          </Button>
        </ErrorState>
      ) : null}
      {investorProfile.data ? (
        <>
          <dl className="settings-facts">
            <div><dt>Status</dt><dd>{investorProfileStatusLabel(investorProfile.data.status)}</dd></div>
            <div><dt>Classificação</dt><dd>{investorProfile.data.dimensions?.overall_classification ? investorProfileRiskLabel(investorProfile.data.dimensions.overall_classification) : "Ainda não calculada"}</dd></div>
            <div><dt>Objetivo</dt><dd>{investorProfileObjectiveLabel(investorProfile.data.primary_objective)}</dd></div>
            <div><dt>Última revisão</dt><dd>{formatDateTimeBR(investorProfile.data.last_reviewed_at ?? investorProfile.data.confirmed_at ?? undefined)}</dd></div>
          </dl>
          <button className="button button-secondary" type="button" onClick={continueOrReview}>
            {investorProfileActionLabel(investorProfile.data.status)}
          </button>
        </>
      ) : null}
    </Card>
  );
}

function FutureFinancial() {
  const { token } = useAuth();
  const future = useQuery({
    queryKey: ["financial-future", token],
    queryFn: () => endpoints.financialFuture(token!),
    enabled: Boolean(token),
  });
  if (future.isLoading) return <LoadingState label="Atualizando seu futuro financeiro..." />;
  if (future.error) return <ErrorState message="Não foi possível calcular seu futuro financeiro. A carteira e a meta permanecem salvas.">
    <Button variant="secondary" type="button" onClick={() => { void future.refetch(); }}>Tentar novamente</Button>
  </ErrorState>;
  if (!future.data) return <Card title="Defina sua meta patrimonial">
    <p>Informe sua meta em Montar Carteira. Ela ficará salva na conta e poderá ser acompanhada aqui, tanto no computador quanto no aplicativo.</p>
    <Link className="button button-secondary" to="/planejar?secao=montar-carteira">Definir minha meta</Link>
  </Card>;

  const data = future.data;
  const months = data.goal.estimated_months;
  const timeToGoal = months == null
    ? "Não atingida no horizonte simulado"
    : months === 0 ? "Meta já atingida"
    : `${Math.floor(months / 12)} ano(s) e ${months % 12} mês(es)`;
  return <div className="page-stack">
    <Card title="Meu caminho até a meta">
      <div className="metric-grid compact">
        <MetricCard label="Patrimônio registrado" value={formatMoney(data.goal.current_wealth)} />
        <MetricCard label="Meta de patrimônio" value={formatMoney(data.goal.required_wealth)} />
        <MetricCard label="Falta para a meta" value={formatMoney(data.goal.gap)} />
        <MetricCard label="Progresso" value={formatPercent(data.goal.achieved_percentage)} />
        <MetricCard label="Prazo estimado (cenário central)" value={timeToGoal} />
      </div>
      <p className="helper">O tempo é uma simulação, não uma previsão garantida. Usa o aporte recorrente e o horizonte definidos no Perfil do Investidor.</p>
      {data.valuation_note ? <p className="warning-box">{data.valuation_note}</p> : null}
    </Card>
    <Card title="Cenários do futuro">
      <ResponsiveTable className="table-wrap"><table><thead><tr><th>Cenário</th><th>Total contribuído</th><th>Patrimônio estimado</th><th>Em reais de hoje</th><th>Renda mensal hipotética</th></tr></thead><tbody>{data.projections.map((item) => <tr key={item.name}>
        <td>{({ stress: "Estresse", conservative: "Conservador", central: "Central", optimistic: "Otimista" } as Record<string, string>)[item.name] ?? item.name}</td>
        <td>{formatMoney(item.total_contributed)}</td>
        <td>{formatMoney(item.projected_wealth)}</td>
        <td>{item.real_projected_wealth == null ? "Inflação não informada" : formatMoney(item.real_projected_wealth)}</td>
        <td>{formatMoney(item.estimated_periodic_income)}</td>
      </tr>)}</tbody></table></ResponsiveTable>
      <details><summary>Reserva, capacidade e premissas</summary>
        <div className="metric-grid compact">
          <MetricCard label="Capacidade mensal estimada" value={formatMoney(data.diagnosis.estimated_monthly_capacity)} />
          <MetricCard label="Reserva recomendada (se calculável)" value={formatMoney(data.diagnosis.reserve_target)} />
        </div>
        <TextList items={data.diagnosis.priority_actions} />
      </details>
      <p className="helper smart-disclaimer">{data.disclaimer}</p>
      <Button variant="secondary" type="button" onClick={() => { void future.refetch(); }} disabled={future.isFetching}>{future.isFetching ? "Atualizando..." : "Atualizar projeção"}</Button>
    </Card>
  </div>;
}

function Strategy() {
  const { token } = useAuth();
  const policy = useQuery({
    queryKey: ["portfolio-policy", token],
    queryFn: () => endpoints.portfolioPolicy(token!),
    enabled: Boolean(token),
  });
  if (policy.isLoading) return <LoadingState label="Carregando estratégia..." />;
  if (policy.error) return <ErrorState message="Não foi possível carregar sua estratégia." />;
  if (!policy.data) return <Card title="Minha estratégia">
    <p>Conclua e confirme seu Perfil do Investidor para gerar automaticamente a estratégia.</p>
  </Card>;

  const applied = policy.data;
  const allocations = applied.allocations.filter((item) => item.enabled);
  const total = allocations.reduce((sum, item) => sum + (parseBrazilianNumber(item.target_percentage) ?? 0), 0);
  return <Card title="Minha estratégia">
    <p className="helper">Configuração gerada pelo Perfil do Investidor. Para modificar objetivos, restrições ou limites, revise seu perfil no cartão acima.</p>
    <dl className="settings-facts">
      <div><dt>Objetivo</dt><dd>{investorProfileObjectiveLabel(applied.objective)}</dd></div>
      <div><dt>Classificação de risco</dt><dd>{investorProfileRiskLabel(applied.risk_profile)}</dd></div>
      <div><dt>Horizonte</dt><dd>{investorProfileHorizonLabel(applied.investment_horizon)}</dd></div>
      <div><dt>Aporte mensal</dt><dd>{formatMoney(applied.monthly_contribution)}</dd></div>
      <div><dt>Necessidade de liquidez</dt><dd>{investorProfileLiquidityLabel(applied.liquidity_need)}</dd></div>
      <div><dt>Limite por ativo</dt><dd>{formatPercent(applied.maximum_weight_per_asset)}</dd></div>
      <div><dt>Limite por setor</dt><dd>{formatPercent(applied.maximum_weight_per_sector)}</dd></div>
      <div><dt>Limite por emissor</dt><dd>{formatPercent(applied.maximum_weight_per_issuer)}</dd></div>
    </dl>
    <strong>Total da alocação: {formatPercent(total)}</strong>
    <ResponsiveTable className="table-wrap">
      <table>
        <thead><tr><th>Classe</th><th>Alvo</th><th>Mínimo</th><th>Máximo</th></tr></thead>
        <tbody>{allocations.map((item) => <tr key={item.asset_class}>
          <td>{item.asset_class}</td>
          <td>{formatPercent(item.target_percentage)}</td>
          <td>{formatPercent(item.minimum_percentage)}</td>
          <td>{formatPercent(item.maximum_percentage)}</td>
        </tr>)}</tbody>
      </table>
    </ResponsiveTable>
  </Card>;
}

function Overview({ data }: { data: PortfolioIntelligence }) {
  const overview = data.overview;
  if (!overview.investments_count) {
    return <EmptyState title="Carteira vazia"><p>Cadastre investimentos para liberar o diagnóstico.</p></EmptyState>;
  }
  return (
    <>
      {!data.policy ? <div className="warning-box">Configure sua estratégia para receber análises e sugestões personalizadas.</div> : null}
      {overview.market_data_status === "partial" ? <div className="warning-box">Dados parciais: alguns ativos ainda não possuem cotação atual.</div> : null}
      {overview.market_data_status === "unavailable" ? <div className="warning-box">Provedor indisponível ou sem cotações disponíveis. A carteira continua acessível.</div> : null}
      <div className="metric-grid">
        <MetricCard label="Patrimônio atual" value={formatMoney(overview.current_equity)} />
        <MetricCard label="Total investido" value={formatMoney(overview.total_invested)} />
        <MetricCard label="Lucro ou prejuízo" value={formatMoney(overview.profit_loss)} />
        <MetricCard label="Rentabilidade" value={formatPercent(overview.profitability)} />
        <MetricCard label="Renda recebida" value={overview.received_income === null ? "Dados insuficientes para calcular." : formatMoney(overview.received_income)} />
        <MetricCard label="Investimentos" value={overview.investments_count} />
        <MetricCard label="Renda fixa" value={formatPercent(overview.fixed_income_percentage)} />
        <MetricCard label="Renda variável" value={formatPercent(overview.variable_income_percentage)} />
        <MetricCard label="Classificação" value={overview.portfolio_classification} />
        <MetricCard label="Risco estimado" value={overview.risk_level} />
        <MetricCard label="Qualidade dos dados" value={overview.data_quality} />
        <MetricCard label="Última atualização" value={formatDateTimeBR(overview.last_updated_at)} />
      </div>
    </>
  );
}

function Diagnosis({ data }: { data: PortfolioIntelligence }) {
  const diagnosis = data.diagnosis;
  const score = parseBrazilianNumber(diagnosis.portfolio_score);
  const state = score == null
    ? "Avaliação ainda parcial"
    : score >= 75 ? "Boa aderência estrutural"
    : score >= 50 ? "Atenção a alguns pontos"
    : "Revisão prioritária";
  return <div className="page-stack">
    <Card title="Resumo do diagnóstico">
      <h3>{state}</h3>
      <p>A avaliação considera distribuição, concentração, limites do seu perfil e cobertura de cotações. Não mede a qualidade fundamentalista de todos os ativos nem garante retorno.</p>
      <div className="metric-grid compact">
        <MetricCard label="Pontuação estrutural" value={diagnosis.portfolio_score == null ? "Não calculável com segurança" : formatPercent(diagnosis.portfolio_score)} />
        <MetricCard label="Risco por concentração" value={diagnosis.risk_level} />
        <MetricCard label="Qualidade dos dados" value={diagnosis.data_quality} />
      </div>
    </Card>
    <Card title="O que precisa de atenção">
      <TextList items={diagnosis.warnings} fallback="Nenhum alerta estrutural identificado com os dados atuais." />
      <h3>O que já está bom</h3>
      <TextList items={diagnosis.strengths} fallback="Aguardando dados suficientes." />
    </Card>
    <details><summary>Indicadores e distribuição detalhados</summary>
      <div className="score-grid">
        <ScoreGauge label="Diversificação estrutural" value={diagnosis.diversification_score} />
        <ScoreGauge label="Baixa concentração" value={diagnosis.concentration_score} />
      </div>
      <p className="helper">Liquidez e renda não recebem nota sem dados de proventos, volumes e condições de resgate.</p>
      <ClassAllocationTable items={diagnosis.class_allocations} />
      {diagnosis.unclassified_assets.length ? <p className="helper">Ativos sem classificação: {diagnosis.unclassified_assets.join(", ")}.</p> : null}
    </details>
  </div>;
}

function Recommendations({ data }: { data: PortfolioIntelligence }) {
  const { token } = useAuth();
  const market = useQuery({
    queryKey: ["portfolio-market-recommendations", token],
    queryFn: () => endpoints.portfolioMarketRecommendations(token!),
    enabled: Boolean(token) && Boolean(data.overview.investments_count),
  });
  if (!data.policy) return <EmptyState title="Configure sua estratégia para receber análises e sugestões personalizadas." />;
  if (market.isLoading) return <LoadingState label="Carregando recomendações de mercado..." />;
  if (market.error) return <ErrorState message="Os dados de mercado estão temporariamente indisponíveis." />;
  if (market.data?.snapshots.length) {
    return (
      <div className="page-stack">
        {market.data.errors.length ? <div className="warning-box">Alguns investimentos estão sem dados de mercado suficientes.</div> : null}
        {market.data.snapshots.map((item) => <MarketRecommendationCard key={item.symbol} item={item} />)}
      </div>
    );
  }
  if (!data.recommendations.length) return <EmptyState title="Dados insuficientes para calcular." />;
  return (
    <div className="page-stack">
      {data.recommendations.map((item) => (
        <Card key={item.symbol} title={`${item.symbol} - ${item.recommendation}`}>
          <div className="metric-grid">
            <MetricCard label="Classe" value={item.asset_class} />
            <MetricCard label="Peso atual" value={formatPercent(item.current_weight)} />
            <MetricCard label="Avaliação de preço" value={item.valuation_status} />
            <MetricCard label="Confiança" value={item.confidence} />
            <MetricCard label="Valor atual" value={formatMoney(item.current_value)} />
          </div>
          <h3>Motivos positivos</h3>
          <TextList items={item.positive_reasons} />
          <h3>Pontos de atenção</h3>
          <TextList items={[...item.risk_reasons, ...item.missing_data]} fallback="Sem pontos de atenção com os dados disponíveis." />
        </Card>
      ))}
    </div>
  );
}

function MarketRecommendationCard({ item }: { item: AssetIntelligenceSnapshot }) {
  const missing = item.indicators.filter((indicator) => indicator.status !== "available");
  const grouped = groupedIndicators(item.indicators);
  return (
    <Card key={item.symbol} title={`${item.symbol} - ${recommendationLabel(item.recommendation)}`}>
      <div className="metric-grid">
        <MetricCard label="Investimento" value={item.name || item.symbol} />
        <MetricCard label="Classe" value={assetClassLabel(item.asset_class)} />
        <MetricCard label="Pontuação geral" value={formatPercent(item.overall_score)} />
        <MetricCard label="Avaliação de preço" value={valuationLabel(item.valuation_status)} />
        <MetricCard label="Confiança" value={confidenceLabel(item.confidence)} />
        <MetricCard label="Cobertura dos dados" value={formatPercent(item.coverage_percentage)} />
        <MetricCard label="Qualidade dos dados" value={formatPercent(item.data_quality_score)} />
        <MetricCard label="Preço atual" value={formatPriceWithCurrency(item.current_price, item.currency)} />
        {item.valuation.estimated_range_low != null && item.valuation.estimated_range_high != null ? (
          <MetricCard label="Faixa setorial indicativa (não preço justo intrínseco)" value={`${formatMoney(item.valuation.estimated_range_low)} – ${formatMoney(item.valuation.estimated_range_high)}`} />
        ) : null}
        <MetricCard label="Atualização" value={formatDateTimeBR(item.market_updated_at)} />
      </div>
      {item.valuation.peer_comparison ? <p className="helper" role="note">{item.valuation.peer_comparison}</p> : null}
      {item.warning_reasons.length ? <div className="warning-box">{item.warning_reasons[0]}</div> : null}
      {item.data_quality?.anomaly_flags.length ? (
        <div className="warning-box">{item.data_quality.anomaly_flags.join(" ")}</div>
      ) : null}
      <h3>Indicadores por categoria</h3>
      {Object.entries(grouped).map(([category, indicators]) => (
        <details key={category} className="details-panel" open={category === "preço e mercado"}>
          <summary>{category}</summary>
          <IndicatorTable items={indicators} />
        </details>
      ))}
      <h3>Dados ausentes</h3>
      <TextList
        items={missing.map((indicator) => `${indicator.label}: ${indicator.unavailable_reason || statusLabel(indicator.status)}`)}
        fallback="Nenhum dado ausente nos indicadores analisados."
      />
      <h3>Motivos</h3>
      <TextList items={item.positive_reasons} />
      <h3>Pontos de atenção</h3>
      <TextList items={item.warning_reasons} fallback="Sem pontos de atenção com os dados disponíveis." />
    </Card>
  );
}

function IndicatorTable({ items }: { items: AssetIntelligenceSnapshot["indicators"] }) {
  if (!items.length) return <p>Não existem dados suficientes para uma análise confiável deste investimento.</p>;
  return (
    <ResponsiveTable className="table-wrap">
      <table>
        <thead><tr><th>Indicador</th><th>Valor</th><th>Período</th><th>Status</th><th>Fonte</th><th>Atualização</th><th>Explicação</th></tr></thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key}>
              <td>{item.label}</td>
              <td>{item.display_value || "Não informado"}</td>
              <td>{item.period || "Não informado"}</td>
              <td>{statusLabel(item.status)}</td>
              <td>{item.source}</td>
              <td>{formatDateTimeBR(item.reference_date)}</td>
              <td>{[item.sector_comparison, item.explanation || item.description].filter(Boolean).join(" • ") || "Não informado"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ResponsiveTable>
  );
}

function Rebalancing({ data }: { data: PortfolioIntelligence }) {
  if (!data.policy) return <EmptyState title="Configure sua estratégia para receber análises e sugestões personalizadas." />;
  if (!data.rebalancing.length) return <EmptyState title="Dados insuficientes para calcular." />;
  return (
    <Card title="Rebalanceamento">
      <ResponsiveTable className="table-wrap">
        <table>
          <thead><tr><th>Classe</th><th>Atual</th><th>Meta</th><th>Diferença</th><th>Falta</th><th>Excesso</th><th>Próximo aporte</th><th>Status</th></tr></thead>
          <tbody>
            {data.rebalancing.map((item) => (
              <tr key={item.asset_class}>
                <td>{item.asset_class}</td>
                <td>{formatPercent(item.current_percentage)}</td>
                <td>{formatPercent(item.target_percentage)}</td>
                <td>{formatPercent(item.difference_percentage)}</td>
                <td>{formatMoney(item.missing_value)}</td>
                <td>{formatMoney(item.excess_value)}</td>
                <td>{formatMoney(item.suggested_contribution)}</td>
                <td>{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ResponsiveTable>
    </Card>
  );
}

function BuildPortfolio() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const policyQuery = useQuery({
    queryKey: ["portfolio-policy", token],
    queryFn: () => endpoints.portfolioPolicy(token!),
    enabled: Boolean(token),
  });
  const profileQuery = useQuery({
    queryKey: ["investor-profile", token],
    queryFn: () => investorProfileEndpoints.get(token!),
    enabled: Boolean(token),
  });
  const policy = policyQuery.data ?? null;
  const savedGoal = useQuery({
    queryKey: ["financial-goal", token],
    queryFn: () => endpoints.financialGoal(token!),
    enabled: Boolean(token),
  });
  const [goalAmount, setGoalAmount] = useState("");
  const [dailyAmount, setDailyAmount] = useState("");
  useEffect(() => {
    if (savedGoal.data?.wealth_goal_amount != null) setGoalAmount(String(savedGoal.data.wealth_goal_amount));
  }, [savedGoal.data?.wealth_goal_amount]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!policy || profileQuery.data?.status !== "complete") {
        throw new Error("Confirme seu Perfil do Investidor antes de montar uma carteira.");
      }
      const wealthGoal = normalizeDecimalForApi(goalAmount);
      await endpoints.saveFinancialGoal(token!, wealthGoal);
      void queryClient.invalidateQueries({ queryKey: ["financial-goal", token] });
      void queryClient.invalidateQueries({ queryKey: ["financial-future", token] });
      return endpoints.buildPortfolio(token!, {
        available_amount: normalizeDecimalForApi(dailyAmount),
        wealth_goal_amount: wealthGoal,
        objective: policy.objective,
        horizon: policy.investment_horizon,
        risk_profile: policy.risk_profile,
        needs_emergency_reserve: true,
        emergency_months: policy.emergency_reserve_months,
        monthly_contribution: String(policy.monthly_contribution),
        needs_income: policy.income_need,
        needs_liquidity: policy.liquidity_need !== "baixa",
        max_percentage_per_asset: String(policy.maximum_weight_per_asset),
        max_percentage_per_sector: String(policy.maximum_weight_per_sector),
        // A política persistida define as classes e os alvos; não há
        // overrides manuais para ampliar limites nem restringir classes.
        allowed_classes: policy.allocations.filter((item) => item.enabled).map((item) => item.asset_class),
        prohibited_classes: [],
        max_assets: null,
        reinvest_income: true,
      });
    },
    onSuccess: (data) => queryClient.setQueryData(["portfolio-projection", token], data),
  });

  if (policyQuery.isLoading || profileQuery.isLoading) {
    return <LoadingState label="Carregando seu perfil para montar a carteira..." />;
  }
  if (policyQuery.error || profileQuery.error) {
    return <ErrorState message="Não foi possível consultar o perfil e a estratégia de investimentos.">
      <Button type="button" variant="secondary" onClick={() => { void policyQuery.refetch(); void profileQuery.refetch(); }}>
        Tentar novamente
      </Button>
    </ErrorState>;
  }
  if (!policy || profileQuery.data?.status !== "complete") {
    return <Card title="Finalize o Perfil do Investidor">
      <p>Para montar uma carteira, conclua e confirme seu Perfil do Investidor. Objetivos, risco, horizonte, liquidez, limites e classes serão definidos automaticamente.</p>
      <p className="helper">Use o botão de continuar ou revisar no cartão Perfil do Investidor acima.</p>
    </Card>;
  }

  return (
    <div className="page-stack smart-portfolio-flow">
      <Card title="Monte uma carteira para o seu momento">
        <p className="helper">Sua estratégia é aplicada automaticamente a partir do Perfil do Investidor. Informe sua meta de patrimônio e o aporte disponível hoje. A quantidade de unidades usa o aporte de hoje, o preço negociável e os limites da estratégia. A meta também entra no cálculo do quanto falta alcançar.</p>
        <p className="helper">Perfil aplicado: {investorProfileRiskLabel(policy.risk_profile)} • Prazo de investimento: {investorProfileHorizonLabel(policy.investment_horizon)} • Aporte mensal previsto no perfil: {formatMoney(policy.monthly_contribution)}. Para alterar a estratégia, revise seu Perfil do Investidor.</p>
        <div className="warning-box">Simulação educacional. Não constitui ordem de compra e não oferece garantia de retorno.</div>
        <form className="form-grid two" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
          <CurrencyInput label="Patrimônio que quero alcançar" value={goalAmount} onChange={(event) => setGoalAmount(event.target.value)} />
          <CurrencyInput label="Aporte de hoje" value={dailyAmount} onChange={(event) => setDailyAmount(event.target.value)} />
          {mutation.error ? <div className="span-2"><ErrorState message="Não foi possível montar sua carteira agora. Seus dados foram preservados."><Button type="button" variant="secondary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>Tentar novamente</Button></ErrorState></div> : null}
          <div className="span-2"><Button type="submit" disabled={mutation.isPending || (parseBrazilianNumber(dailyAmount) ?? 0) <= 0 || (parseBrazilianNumber(goalAmount) ?? 0) <= 0}>{mutation.isPending ? "Analisando dados e montando sua carteira..." : "Montar minha carteira"}</Button></div>
        </form>
      </Card>
      {mutation.data ? <BuildResult data={mutation.data} totalConsidered={String(mutation.data.daily_contribution_amount ?? normalizeDecimalForApi(dailyAmount))} /> : null}
    </div>
  );
}

function BuildResult({ data, totalConsidered }: { data: BuildPortfolioResponse; totalConsidered: string }) {
  const sortedAssets = [...data.assets].sort((left, right) => (parseBrazilianNumber(right.recommended_percentage) ?? 0) - (parseBrazilianNumber(left.recommended_percentage) ?? 0));
  const budgetNotSelected = data.budget_not_selected ?? [];
  const notIncluded = [...data.exclusions, ...budgetNotSelected];
  const cashRemaining = parseBrazilianNumber(data.unallocated_amount) ?? 0;
  return (
    <div className="page-stack smart-result">
      <Card title="Sua carteira recomendada">
        <div className="metric-grid compact smart-summary">
          <MetricCard label="Confiança" value={confidenceLabel(data.confidence)} />
          <MetricCard label="Aporte de hoje" value={formatMoney(totalConsidered)} />
          <MetricCard label="Valor alocado" value={formatMoney(data.total_allocated_amount)} />
          <MetricCard label="Saldo não alocado" value={formatMoney(data.unallocated_amount)} />
          <MetricCard label="Quantidade de ativos" value={sortedAssets.length} />
          {data.goal_gap_after_contribution != null ? <MetricCard label="Falta para minha meta após a simulação" value={formatMoney(data.goal_gap_after_contribution)} /> : null}
          {(data.existing_positions_count ?? 0) > 0 ? <MetricCard label="Carteira registrada" value={formatMoney(data.existing_portfolio_value)} /> : null}
        </div>
        {data.goal_gap_before_contribution != null ? (
          <div className="helper" role="note">
            <strong>Como a meta influencia esta montagem:</strong>
            <p>Antes desta simulação, faltavam {formatMoney(data.goal_gap_before_contribution)} para o patrimônio desejado. A meta serve para acompanhar o progresso e planejar os aportes futuros; não reduz seu orçamento de hoje nem impõe um teto às compras. Quantidades e valores dependem do aporte informado, dos preços e dos limites do Perfil do Investidor.</p>
            {data.required_monthly_contribution_without_returns != null ? (
              <p>Para buscar a meta no prazo do perfil, seriam necessários aproximadamente {formatMoney(data.required_monthly_contribution_without_returns)} por mês após as compras simuladas hoje, sem considerar rendimentos. Isto é apenas uma referência matemática, não uma promessa de retorno.</p>
            ) : null}
          </div>
        ) : null}
        {sortedAssets.length === 1 ? (
          <div className="warning-box" role="note">
            <strong>Por que apareceu apenas um ativo?</strong>
            {data.preflight ? (
              <p>O sistema recebeu {data.preflight.snapshots_received} análise(s) de ativos e {data.preflight.eligible_count} passaram pelos filtros de elegibilidade. Isso não significa que todos caibam no orçamento e nos limites da estratégia.</p>
            ) : null}
            <p>A quantidade sugerida é {formatQuantityBR(sortedAssets[0].executable_quantity)} unidade(s) do ativo selecionado, calculada com o aporte de hoje, o preço de referência e a parcela permitida para esse ativo.</p>
            {budgetNotSelected.length > 0 ? <p>{budgetNotSelected.length} outro(s) candidato(s) não couberam na divisão do aporte. Consulte os motivos na seção “Ativos não incluídos”.</p> : null}
            {cashRemaining > 0 ? <p>Restaram {formatMoney(data.unallocated_amount)} sem alocação. Esse valor não é investido automaticamente em ativos que não atendem à política de risco.</p> : null}
          </div>
        ) : null}
        {!sortedAssets.length ? <div className="smart-insufficient"><h3>Ainda não há dados suficientes para recomendar ativos.</h3><p>O valor não alocado permanece disponível. Revise os dados ausentes abaixo ou tente novamente.</p><TextList items={data.missing_data} fallback="A cobertura atual não permite uma recomendação segura." /></div> : (
          <div className="recommended-assets" aria-label="Ativos recomendados">
            {sortedAssets.map((asset) => <RecommendedAssetCard asset={asset} key={asset.symbol} />)}
          </div>
        )}
        <p className="helper smart-disclaimer">{data.disclaimer}</p>
        {(data.existing_positions_count ?? 0) > 0 ? <p className="helper">Novas compras calculadas considerando {data.existing_positions_count} posição(ões) registradas e os limites do seu perfil.</p> : null}
        {(data.holdings_warnings ?? []).map((warning) => <p className="helper" role="note" key={warning}>{warning}</p>)}
      </Card>
      {(data.existing_holdings_assessments ?? []).length > 0 ? (
        <ResultDetails title="Avaliação dos ativos já comprados">
          <p className="helper">Avaliação das posições cadastradas na aba Carteira, usando indicadores, confiança e limites de concentração.</p>
          <div className="holdings-assessments">
            {data.existing_holdings_assessments!.map((holding) => (
              <article className="holding-assessment" key={holding.symbol}>
                <div className="holding-assessment-heading">
                  <strong>{holding.symbol}</strong>
                  <span className="badge">{registeredHoldingLabel(holding.recommendation)}</span>
                </div>
                <dl className="asset-execution-grid">
                  <div><dt>Quantidade existente</dt><dd>{formatQuantityBR(holding.quantity)}</dd></div>
                  <div><dt>Valor considerado</dt><dd>{formatMoney(holding.estimated_value)}</dd></div>
                  <div><dt>Peso atual</dt><dd>{formatPercent(holding.estimated_weight)}</dd></div>
                  <div><dt>Confiança nos indicadores</dt><dd>{confidenceLabel(holding.confidence)}</dd></div>
                </dl>
                <p>{holding.rationale}</p>
                {holding.valuation_basis !== "market" ? <p className="helper">Sem cotação atual: valor aproximado pelo custo.</p> : null}
                {holding.alerts.length ? <details><summary>Riscos e alertas</summary><TextList items={holding.alerts} /></details> : null}
              </article>
            ))}
          </div>
        </ResultDetails>
      ) : null}
      <ResultDetails title="Por que esta carteira?"><p>{data.strategy_summary}</p><TextList items={data.selections.map((item) => `${item.asset_class}: ${item.message}`)} /></ResultDetails>
      <ResultDetails title="Riscos e cuidados"><TextList items={[...data.diagnosis.debt_alerts, ...data.freedom_goal.risks]} fallback="Nenhum cuidado adicional foi identificado com os dados disponíveis." /></ResultDetails>
      <ResultDetails title="Distribuição por classe">{!data.class_allocations.length ? <EmptyState title="Cobertura insuficiente para alocar com segurança." /> : <ResponsiveTable className="table-wrap"><table><thead><tr><th>Classe</th><th>Percentual</th><th>Valor sugerido</th><th>Explicação</th></tr></thead><tbody>{data.class_allocations.map((item) => <tr key={item.asset_class}><td>{item.asset_class}</td><td>{formatPercent(item.percentage)}</td><td>{formatMoney(item.amount)}</td><td>{item.explanation}</td></tr>)}</tbody></table></ResponsiveTable>}</ResultDetails>
      <ResultDetails title="Planejamento financeiro"><div className="metric-grid compact"><MetricCard label="Fase" value={data.diagnosis.phase} /><MetricCard label="Capacidade mensal estimada" value={formatMoney(data.diagnosis.estimated_monthly_capacity)} /><MetricCard label="Meta de reserva" value={formatMoney(data.diagnosis.reserve_target)} /><MetricCard label="Progresso do objetivo" value={formatPercent(data.freedom_goal.achieved_percentage)} /></div><TextList items={[...data.diagnosis.priority_actions, ...data.freedom_goal.improvement_actions]} /><ResponsiveTable className="table-wrap"><table><thead><tr><th>Cenário</th><th>Total aportado</th><th>Patrimônio projetado</th><th>Renda estimada</th></tr></thead><tbody>{data.projections.map((item) => <tr key={item.name}><td>{item.name}</td><td>{formatMoney(item.total_contributed)}</td><td>{formatMoney(item.projected_wealth)}</td><td>{formatMoney(item.estimated_periodic_income)}</td></tr>)}</tbody></table></ResponsiveTable></ResultDetails>
      <ResultDetails title="Carteira executável">{!sortedAssets.length ? <p>Sem ativos executáveis.</p> : <ResponsiveTable className="table-wrap"><table><thead><tr><th>Ativo</th><th>Preço</th><th>Quantidade</th><th>Valor executável</th><th>Diferença do alvo</th></tr></thead><tbody>{sortedAssets.map((asset) => <tr key={`execution-${asset.symbol}`}><td>{asset.symbol}</td><td>{formatMoney(asset.reference_price)}</td><td>{asset.executable_quantity ?? "—"}</td><td>{formatMoney(asset.executable_amount)}</td><td>{formatMoney(asset.target_gap)}</td></tr>)}</tbody></table></ResponsiveTable>}</ResultDetails>
      <ResultDetails title="Plano de aportes">{!data.contribution_plan.length ? <p>Sem aporte mensal informado.</p> : <ResponsiveTable className="table-wrap"><table><thead><tr><th>Prioridade</th><th>Destino</th><th>Valor</th><th>Motivo</th></tr></thead><tbody>{data.contribution_plan.map((item) => <tr key={`${item.priority}-${item.symbol}`}><td>{item.priority}</td><td>{item.symbol}</td><td>{formatMoney(item.suggested_amount)}</td><td>{item.reason}</td></tr>)}</tbody></table></ResponsiveTable>}</ResultDetails>
      <ResultDetails title="Dados e fontes"><TextList items={[...data.missing_data, ...sortedAssets.flatMap((asset) => asset.execution_impediments)]} fallback="Sem avisos adicionais sobre dados e fontes." /></ResultDetails>
      <ResultDetails title="Ativos não incluídos">{notIncluded.length ? <ResponsiveTable className="table-wrap"><table><thead><tr><th>Ativo</th><th>Classe</th><th>Motivo</th></tr></thead><tbody>{notIncluded.map((item, index) => <tr key={`${item.symbol}-${index}`}><td>{item.symbol}</td><td>{item.asset_class}</td><td>{item.reasons.join(" ")}</td></tr>)}</tbody></table></ResponsiveTable> : <p>Nenhum ativo adicional foi excluído.</p>}</ResultDetails>
    </div>
  );
}

type RecommendedAsset = BuildPortfolioResponse["assets"][number];
type RecommendedIndicator = RecommendedAsset["indicators_used"][number];

function RecommendedAssetCard({ asset }: { asset: RecommendedAsset }) {
  const quantity = asset.executable_quantity === null
    ? "Indisponível"
    : `${formatQuantityBR(asset.executable_quantity)} unidades`;
  return <article className="recommended-asset">
    <header className="recommended-asset-heading">
      <div><strong>{asset.symbol}</strong><span>{asset.asset_class}</span></div>
      <div className="recommended-asset-signal">
        <span className="badge">{assetSignalLabel(asset.score, asset.confidence)}</span>
        <small>Pontuação: {formatDecimalBR(asset.score, 1)}/100</small>
      </div>
      {asset.market_segment ? <span className="market-segment">{marketSegmentLabel(asset.market_segment)}</span> : null}
      {asset.trading_symbol && asset.trading_symbol !== asset.symbol ? <small>Ticker negociável: {asset.trading_symbol}</small> : null}
      {asset.market_segment === "mixed" ? <small>Lote padrão e sobra fracionária exigem tickers distintos; não utilize um único ticker para toda a quantidade.</small> : null}
    </header>
    <dl className="asset-execution-grid">
      <div><dt>Percentual-alvo</dt><dd>{formatPercent(asset.recommended_percentage)}</dd></div>
      <div><dt>Valor-alvo</dt><dd>{formatMoney(asset.recommended_amount)}</dd></div>
      <div><dt>Preço de referência</dt><dd>{formatMoney(asset.reference_price)}</dd></div>
      <div><dt>Quantidade sugerida</dt><dd>{quantity}</dd></div>
      <div><dt>Valor executável</dt><dd>{asset.executable_quantity === null ? "Indisponível" : formatMoney(asset.executable_amount)}</dd></div>
      <div><dt>Saldo/diferença</dt><dd>{formatTargetGap(asset.target_gap)}</dd></div>
      <div><dt>Confiança nos dados</dt><dd>{confidenceLabel(asset.confidence)}</dd></div>
      {(parseBrazilianNumber(asset.existing_quantity) ?? 0) > 0 ? (
        <>
          <div><dt>Quantidade que já possui</dt><dd>{formatQuantityBR(asset.existing_quantity)}</dd></div>
          <div><dt>Valor em carteira</dt><dd>{formatMoney(asset.existing_value)}</dd></div>
          <div><dt>Peso após novo aporte</dt><dd>{formatPercent(asset.post_purchase_weight)}</dd></div>
        </>
      ) : null}
    </dl>
    {asset.estimated_range_low != null && asset.estimated_range_high != null ? (
      <div className="portfolio-peer-valuation">
        <strong>Faixa de preço indicativa por múltiplos do setor</strong>
        <span>{formatMoney(asset.estimated_range_low)} – {formatMoney(asset.estimated_range_high)}</span>
        <small>Comparação relativa, não preço justo intrínseco ou garantia de rentabilidade. Confiança na faixa: {confidenceLabel(asset.valuation_confidence ?? "insufficient")}.</small>
        {asset.peer_comparison ? <p className="helper">{asset.peer_comparison}</p> : null}
      </div>
    ) : asset.peer_comparison ? (
      <details className="confidence-explanation"><summary>Por que não há estimativa de preço?</summary><p className="helper">{asset.peer_comparison}</p></details>
    ) : null}
    {asset.allocation_note ? <p className="helper recommended-allocation-note">{asset.allocation_note}</p> : null}
    {asset.execution_impediments.length ? <div className="execution-warning" role="note"><strong>Quantidade sugerida: indisponível</strong><TextList items={asset.execution_impediments} /></div> : null}
    {asset.missing_data.length ? <details className="confidence-explanation" aria-label="Dados ausentes"><summary>Limitações e indicadores não disponíveis</summary><TextList items={asset.missing_data} /></details> : null}
    <details className="asset-details">
      <summary>Ver detalhes</summary>
      <div className="asset-detail-content">
        <h4>Justificativas</h4><TextList items={asset.reasons} />
        <h4>Riscos</h4><TextList items={asset.risks} fallback="Nenhum risco adicional identificado com os dados disponíveis." />
        <h4>Indicadores utilizados</h4>
        {asset.indicators_used.some((item) => item.sector_comparison) ? (
          <div className="portfolio-sector-benchmarks">
            <strong>Comparação com empresas do mesmo setor</strong>
            <TextList items={asset.indicators_used.flatMap((item) => item.sector_comparison ? [`${item.label}: ${item.sector_comparison}`] : [])} />
          </div>
        ) : null}
        <ResponsiveTable className="table-wrap indicator-table"><table><thead><tr><th>Indicador</th><th>Valor</th><th>Situação</th><th>Referência</th></tr></thead><tbody>{asset.indicators_used.map((item) => <tr key={item.key}><td data-label="Indicador">{item.label}</td><td data-label="Valor">{formatIndicatorValue(item)}</td><td data-label="Situação">{indicatorStatusLabel(item)}</td><td data-label="Referência">{formatDateTimeBR(item.reference_date)}</td></tr>)}</tbody></table></ResponsiveTable>
        <details className="indicator-provenance"><summary>Ver procedência e qualidade dos dados</summary><ResponsiveTable className="table-wrap"><table><thead><tr><th>Indicador</th><th>Fonte</th><th>Tipo</th><th>Referência</th><th>Validade</th><th>Frescor</th></tr></thead><tbody>{asset.indicators_used.map((item) => <tr key={`source-${item.key}`}><td data-label="Indicador">{item.label}</td><td data-label="Fonte">{item.source}</td><td data-label="Tipo">{sourceTypeLabel(item.source_type)}</td><td data-label="Referência">{formatDateTimeBR(item.reference_date)}</td><td data-label="Validade">{formatDateTimeBR(item.valid_until)}</td><td data-label="Frescor">{freshnessLabel(item.freshness_status)}</td></tr>)}</tbody></table></ResponsiveTable><h4>Ausências e impedimentos</h4><TextList items={[...asset.missing_data, ...asset.execution_impediments, ...asset.indicators_used.flatMap((item) => item.unavailable_reason ? [item.unavailable_reason] : [])]} fallback="Nenhuma ausência ou impedimento informado." /></details>
      </div>
    </details>
  </article>;
}

function formatTargetGap(value: string | number) {
  const amount = parseBrazilianNumber(value);
  if (amount === null) return "Não informado";
  return amount > 0 ? `${formatMoney(amount)} não alocados neste ativo` : formatMoney(amount);
}

function formatIndicatorValue(indicator: RecommendedIndicator) {
  if (indicator.status === "not_applicable") return "Não aplicável";
  if (indicator.value === null || indicator.status === "unavailable") return "Indisponível";
  if (typeof indicator.value === "string" && parseBrazilianNumber(indicator.value) === null) return indicator.value;
  if (indicator.unit === "percentage" || indicator.unit === "percent") return formatPercent(indicator.value);
  if (indicator.unit === "currency" || indicator.unit === "BRL") return formatMoney(indicator.value);
  return formatDecimalBR(indicator.value, 2, "Indisponível");
}

function indicatorStatusLabel(indicator: RecommendedIndicator) {
  if (indicator.status === "not_applicable") return "Não aplicável";
  if (indicator.status === "unavailable") return "Indisponível";
  return freshnessLabel(indicator.freshness_status);
}

function freshnessLabel(value: string) {
  return ({ current: "Atual", stale: "Vencido", unavailable: "Indisponível", not_applicable: "Não aplicável" } as Record<string, string>)[value] ?? value;
}

function sourceTypeLabel(value: string) {
  return ({ official: "Oficial", provider: "Provedor", snapshot: "Snapshot", manual: "Manual" } as Record<string, string>)[value] ?? value;
}

function marketSegmentLabel(value: string) {
  return ({ fractional: "Mercado fracionário", mixed: "Lote padrão + fracionário", standard_lot: "Lote padrão" } as Record<string, string>)[value] ?? value;
}

function ResultDetails({ title, children }: { title: string; children: ReactNode }) {
  return <details className="details-panel smart-result-details"><summary>{title}</summary><div className="smart-detail-body">{children}</div></details>;
}

export function MarketOpportunities() {
  const { token } = useAuth();
  const intelligence = useQuery({
    queryKey: ["portfolio-intelligence", token],
    queryFn: () => endpoints.portfolioIntelligence(token!),
    enabled: Boolean(token),
    retry: false,
    staleTime: 30_000,
  });
  const macro = useQuery({
    queryKey: ["macro-context", token],
    queryFn: () => endpoints.macroContext(token!),
    enabled: Boolean(token),
  });
  if (intelligence.isLoading) return <LoadingState label="Carregando oportunidades de mercado..." />;
  if (intelligence.error || !intelligence.data) return <ErrorState message="Não foi possível carregar as oportunidades de mercado." />;
  const data = intelligence.data;
  return (
    <div className="page-stack">
      <Card title="Grupos de análise">
        <div className="metric-grid compact">
          {["Ações", "FIIs", "ETFs", "Tesouro Direto", "Renda fixa privada", "BDRs", "Ativos internacionais", "Criptomoedas", "Cenário econômico"].map((item) => (
            <MetricCard key={item} label={item} value="Estrutura preparada" />
          ))}
        </div>
      </Card>
      <Card title="Termos técnicos">
        <TextList
          items={[
            "Tracking error: diferença de comportamento entre o ETF e o índice que ele busca acompanhar.",
            "Duration: estimativa da sensibilidade do preço do título às mudanças nas taxas de juros.",
            "Rating: avaliação de risco de crédito feita por uma agência especializada.",
            "MVRV: relação entre o valor de mercado e uma estimativa do valor pago pelos participantes da rede.",
          ]}
        />
      </Card>
      <Card title="Cenário econômico">
        {macro.isLoading ? <LoadingState label="Carregando cenário econômico..." /> : null}
        {macro.error ? <ErrorState message="Não foi possível carregar o cenário econômico." /> : null}
        {macro.data ? (
          <ResponsiveTable className="table-wrap">
            <table>
              <thead><tr><th>Indicador</th><th>Estado</th><th>Frequência</th><th>Fonte</th></tr></thead>
              <tbody>{macro.data.map((item) => <tr key={item.key}><td>{item.label}</td><td>{statusLabel(item.state)}</td><td>{item.frequency}</td><td>{item.source}</td></tr>)}</tbody>
            </table>
          </ResponsiveTable>
        ) : null}
      </Card>
      {data.opportunities.length ? (
        data.opportunities.map((item) => (
          <Card key={item.asset_class} title={item.asset_class}>
            <div className="metric-grid compact">
              <MetricCard label="Classificação" value={item.classification} />
              <MetricCard label="Confiança" value={item.confidence} />
            </div>
            <p>{item.highlight_reason}</p>
            <TextList items={item.risks} />
          </Card>
        ))
      ) : (
        <EmptyState title="Dados insuficientes para calcular." />
      )}
    </div>
  );
}

function ClassAllocationTable({ items }: { items: PortfolioIntelligence["diagnosis"]["class_allocations"] }) {
  if (!items.length) return <p>Dados insuficientes para calcular.</p>;
  return (
    <ResponsiveTable className="table-wrap">
      <table>
        <thead><tr><th>Classe</th><th>Valor atual</th><th>Atual</th><th>Meta</th><th>Mínimo</th><th>Máximo</th><th>Diferença</th><th>Status</th></tr></thead>
        <tbody>{items.map((item) => <tr key={item.asset_class}><td>{item.asset_class}</td><td>{formatMoney(item.current_value)}</td><td>{formatPercent(item.current_percentage)}</td><td>{formatPercent(item.target_percentage)}</td><td>{formatPercent(item.minimum_percentage)}</td><td>{formatPercent(item.maximum_percentage)}</td><td>{formatPercent(item.difference_percentage)}</td><td>{item.status}</td></tr>)}</tbody>
      </table>
    </ResponsiveTable>
  );
}

function TextList({ items, fallback = "Dados insuficientes para calcular." }: { items: string[]; fallback?: string }) {
  const visible = items.filter(Boolean);
  if (!visible.length) return <p>{fallback}</p>;
  return <ul>{visible.map((item) => <li key={item}>{item}</li>)}</ul>;
}

function assetSignalLabel(score: string | number, confidence: string) {
  const numericScore = parseBrazilianNumber(score);
  if (confidence === "insufficient" || numericScore === null) return "Não avaliável";
  if (confidence === "low") return "Dados exigem cautela";
  if (numericScore >= 70) return "Favorável para análise";
  if (numericScore < 55) return "Exige cautela";
  return "Avaliar fundamentos";
}

function registeredHoldingLabel(value: string) {
  if (value === "review_concentration") return "Rever concentração";
  if (value === "not_analyzed") return "Sem análise disponível";
  return recommendationLabel(value);
}

function recommendationLabel(value: string) {
  return ({
    analyze_to_buy: "Analisar para compra",
    buy_gradually: "Comprar aos poucos",
    increase_position: "Aumentar posição",
    hold: "Manter",
    wait: "Aguardar",
    reduce_exposure: "Reduzir exposição",
    consider_selling: "Considerar venda",
    review_data: "Revisar dados",
    insufficient_data: "Dados insuficientes",
  } as Record<string, string>)[value] ?? "Dados insuficientes";
}

function valuationLabel(value: string) {
  return ({
    very_attractive: "Potencialmente muito atrativo",
    attractive: "Potencialmente atrativo",
    near_estimated_value: "Próximo do valor estimado",
    elevated: "Potencialmente elevado",
    very_elevated: "Potencialmente muito elevado",
    insufficient_data: "Dados insuficientes",
  } as Record<string, string>)[value] ?? "Dados insuficientes";
}

function confidenceLabel(value: string) {
  return ({
    high: "Alta",
    medium: "Média",
    low: "Baixa",
    insufficient: "Insuficiente",
  } as Record<string, string>)[value] ?? "Insuficiente";
}

function statusLabel(value: string) {
  return ({
    available: "Disponível",
    unavailable: "Indisponível",
    stale: "Desatualizado",
    not_applicable: "Não aplicável",
    insufficient_data: "Dados insuficientes",
    potentially_inconsistent: "Potencialmente inconsistente",
    partial: "Parcial",
    invalid: "Inválido",
  } as Record<string, string>)[value] ?? "Indisponível";
}

function assetClassLabel(value: string) {
  return ({
    stock: "Ações",
    fii: "FIIs",
    etf: "ETFs",
    treasury: "Tesouro Direto",
    cdb: "CDB",
    lci: "LCI",
    lca: "LCA",
    debenture: "Debênture",
    investment_fund: "Fundo de investimento",
    bdr: "BDR",
    international: "Ativo internacional",
    crypto: "Criptomoeda",
    unknown: "Não informado",
  } as Record<string, string>)[value] ?? "Não informado";
}

function groupedIndicators(items: AssetIntelligenceSnapshot["indicators"]) {
  return items.reduce<Record<string, AssetIntelligenceSnapshot["indicators"]>>((groups, item) => {
    const category = item.category || "qualidade dos dados";
    groups[category] = groups[category] ?? [];
    groups[category].push(item);
    return groups;
  }, {});
}
