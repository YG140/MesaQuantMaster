import { ResponsiveTable } from "../components/ui/ResponsiveTable";
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode, type SetStateAction } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { DecimalInput } from "../components/forms/DecimalInput";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { MetricCard } from "../components/ui/MetricCard";
import { DataStatusBadge } from "../components/ui/DataBadges";
import { ScoreGauge } from "../components/ui/ScoreGauge";
import { SectionHeader } from "../components/ui/SectionHeader";
import { Select } from "../components/ui/Select";
import { useAuth } from "../features/auth/useAuth";
import {
  continueOrReviewInvestorProfile,
  investorProfileActionLabel,
  investorProfileObjectiveLabel,
  investorProfileStatusLabel,
} from "../features/investorProfile/presentation";
import { ApiError } from "../services/apiClient";
import { endpoints } from "../services/endpoints/data";
import { investorProfileEndpoints } from "../services/endpoints/investorProfile";
import type {
  AssetIntelligenceSnapshot,
  BuildPortfolioResponse,
  PortfolioIntelligence,
  PortfolioPolicy,
  PortfolioPolicyAllocation,
  PortfolioPolicyPayload,
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

const areas = ["Diagnóstico", "Montar carteira", "Futuro financeiro"] as const;
type IntelligenceArea = (typeof areas)[number];
const classes = [
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
];

type PolicyDraft = {
  name: string;
  objective: string;
  risk_profile: string;
  investment_horizon: string;
  monthly_contribution: string;
  liquidity_need: string;
  income_need: boolean;
  emergency_reserve_months: string;
  maximum_weight_per_asset: string;
  maximum_weight_per_sector: string;
  maximum_weight_per_issuer: string;
  rebalance_tolerance: string;
  allocations: Array<Omit<PortfolioPolicyAllocation, "id">>;
};

export function PortfolioIntelligencePage() {
  const { token } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedSection = searchParams.get("secao");
  const area: IntelligenceArea = requestedSection === "montar-carteira"
    ? "Montar carteira"
    : requestedSection === "futuro-financeiro"
      ? "Futuro financeiro"
      : "Diagnóstico";
  const intelligence = useQuery({
    queryKey: ["portfolio-intelligence", token],
    queryFn: () => endpoints.portfolioIntelligence(token!),
    enabled: Boolean(token),
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
      <SectionHeader eyebrow="Planejar" title="Inteligência de Carteira" description="Diagnóstico, construção de carteira e futuro financeiro em uma única experiência." />
      <InvestorProfileSummary />
      <div className="tabs intelligence-areas" role="tablist" aria-label="Áreas de inteligência">
        {areas.map((item) => (
          <button key={item} type="button" role="tab" aria-selected={item === area} className={item === area ? "active" : ""} onClick={() => setSearchParams(item === "Montar carteira" ? { secao: "montar-carteira" } : item === "Futuro financeiro" ? { secao: "futuro-financeiro" } : { secao: "diagnostico" })}>
            {item}
          </button>
        ))}
      </div>
      {area === "Diagnóstico" ? <IntelligenceDependentSections intelligence={intelligence} /> : null}
      {area === "Montar carteira" ? <BuildPortfolio /> : null}
      {area === "Futuro financeiro" ? <div className="intelligence-sections">
        <details open><summary>Minha estratégia</summary><Strategy /></details>
        <details open><summary>Projeções, cenários e liberdade financeira</summary><FutureFinancial /></details>
      </div> : null}
    </div>
  );
}

function IntelligenceDependentSections({ intelligence }: { intelligence: UseQueryResult<PortfolioIntelligence, unknown> }) {
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
          <details open><summary>Visão geral</summary><Overview data={intelligence.data} /></details>
          <details><summary>Diagnóstico</summary><Diagnosis data={intelligence.data} /></details>
          <details><summary>Recomendações</summary><Recommendations data={intelligence.data} /></details>
          <details><summary>Rebalanceamento</summary><Rebalancing data={intelligence.data} /></details>
        </>
      ) : null}
      {/* Oportunidades gerencia seu próprio estado (query independente, ver
          MarketOpportunities) -- nunca escondida só porque o restante do
          diagnóstico falhou. */}
      <details><summary>Oportunidades relacionadas à carteira</summary><MarketOpportunities /></details>
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

function InvestorProfileSummary() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const investorProfile = useQuery({
    queryKey: ["investor-profile", token],
    queryFn: () => investorProfileEndpoints.get(token!),
    enabled: Boolean(token),
  });

  async function continueOrReview() {
    if (!token) return;
    await continueOrReviewInvestorProfile(token, investorProfile.data?.status, navigate);
  }

  return (
    <Card title="Perfil do Investidor" className="investor-profile-summary">
      {investorProfile.isLoading ? <LoadingState label="Consultando seu perfil..." /> : null}
      {investorProfile.error ? (
        <ErrorState message="Não foi possível consultar seu perfil agora.">
          <Button type="button" variant="secondary" onClick={() => investorProfile.refetch()} disabled={investorProfile.isFetching}>
            {investorProfile.isFetching ? "Tentando novamente..." : "Tentar novamente"}
          </Button>
        </ErrorState>
      ) : null}
      {investorProfile.data ? (
        <>
          <dl className="settings-facts">
            <div><dt>Status</dt><dd>{investorProfileStatusLabel(investorProfile.data.status)}</dd></div>
            <div><dt>Classificação</dt><dd>{investorProfile.data.dimensions?.overall_classification ?? "Ainda não calculada"}</dd></div>
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
  const queryClient = useQueryClient();
  const data = queryClient.getQueryData<BuildPortfolioResponse>(["portfolio-projection", token]);

  if (!data) {
    return <div className="card"><p>Gere uma carteira com suas premissas para visualizar projeções, cenários, capacidade mensal, reserva e liberdade financeira.</p><Link className="button button-secondary" to="/planejar?secao=montar-carteira">Informar premissas e gerar projeção</Link></div>;
  }

  return <div className="page-stack">
    <div className="metric-grid compact">
      <MetricCard label="Capacidade mensal estimada" value={formatMoney(data.diagnosis.estimated_monthly_capacity)} />
      <MetricCard label="Meta de reserva" value={formatMoney(data.diagnosis.reserve_target)} />
      <MetricCard label="Patrimônio necessário" value={formatMoney(data.freedom_goal.required_wealth)} />
      <MetricCard label="Progresso do objetivo" value={formatPercent(data.freedom_goal.achieved_percentage)} />
    </div>
    <Card title="Cenários projetados">
      <ResponsiveTable className="table-wrap"><table><thead><tr><th>Cenário</th><th>Total aportado</th><th>Patrimônio projetado</th><th>Renda estimada</th></tr></thead><tbody>{data.projections.map((item) => <tr key={item.name}><td>{item.name}</td><td>{formatMoney(item.total_contributed)}</td><td>{formatMoney(item.projected_wealth)}</td><td>{formatMoney(item.estimated_periodic_income)}</td></tr>)}</tbody></table></ResponsiveTable>
      <TextList items={[...data.diagnosis.priority_actions, ...data.freedom_goal.improvement_actions]} />
      <p className="helper smart-disclaimer">{data.disclaimer}</p>
    </Card>
  </div>;
}

function Strategy() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const policy = useQuery({
    queryKey: ["portfolio-policy", token],
    queryFn: () => endpoints.portfolioPolicy(token!),
    enabled: Boolean(token),
  });
  const [draft, setDraft] = useState<PolicyDraft>(emptyDraft());
  useEffect(() => {
    setDraft(policy.data ? draftFromPolicy(policy.data) : emptyDraft());
  }, [policy.data]);

  const validation = validateDraft(draft);
  const save = useMutation({
    mutationFn: () => endpoints.savePortfolioPolicy(token!, payloadFromDraft(draft)),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portfolio-policy", token] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio-intelligence", token] }),
      ]);
    },
  });

  if (policy.isLoading) return <LoadingState label="Carregando estratégia..." />;
  if (policy.error) return <ErrorState message="Não foi possível carregar sua estratégia." />;

  return (
    <div className="page-stack">
      {!policy.data ? (
        <div className="warning-box">Configure sua estratégia para receber análises e sugestões personalizadas.</div>
      ) : null}
      {save.isSuccess ? <div className="success-box">Estratégia salva com sucesso.</div> : null}
      {save.error ? <ErrorState message={save.error instanceof Error ? save.error.message : "Não foi possível salvar a estratégia."} /> : null}
      <Card title="Minha estratégia">
        <form className="form-grid two" onSubmit={(event) => { event.preventDefault(); if (validation.valid) save.mutate(); }}>
          <Input label="Nome" value={draft.name} onChange={(event) => updateDraft(setDraft, { name: event.target.value })} />
          <CurrencyInput label="Aporte mensal" value={draft.monthly_contribution} onChange={(event) => updateDraft(setDraft, { monthly_contribution: event.target.value })} />
          <Select label="Objetivo" value={draft.objective} onChange={(event) => updateDraft(setDraft, { objective: event.target.value })}>
            <option value="reserva">Reserva</option>
            <option value="renda">Renda</option>
            <option value="crescimento patrimonial">Crescimento patrimonial</option>
            <option value="preservação de capital">Preservação de capital</option>
          </Select>
          <Select label="Perfil de risco" value={draft.risk_profile} onChange={(event) => updateDraft(setDraft, { risk_profile: event.target.value })}>
            <option value="conservador">Conservador</option>
            <option value="moderado">Moderado</option>
            <option value="arrojado">Arrojado</option>
          </Select>
          <Select label="Prazo" value={draft.investment_horizon} onChange={(event) => updateDraft(setDraft, { investment_horizon: event.target.value })}>
            <option value="curto prazo">Curto prazo</option>
            <option value="médio prazo">Médio prazo</option>
            <option value="longo prazo">Longo prazo</option>
          </Select>
          <Select label="Necessidade de liquidez" value={draft.liquidity_need} onChange={(event) => updateDraft(setDraft, { liquidity_need: event.target.value })}>
            <option value="baixa">Baixa</option>
            <option value="média">Média</option>
            <option value="alta">Alta</option>
          </Select>
          <Input label="Meses de reserva" inputMode="numeric" value={draft.emergency_reserve_months} onChange={(event) => updateDraft(setDraft, { emergency_reserve_months: event.target.value.replace(/\D/g, "") })} />
          <DecimalInput label="Máximo por ativo (%)" value={draft.maximum_weight_per_asset} onChange={(event) => updateDraft(setDraft, { maximum_weight_per_asset: event.target.value })} />
          <DecimalInput label="Máximo por setor (%)" value={draft.maximum_weight_per_sector} onChange={(event) => updateDraft(setDraft, { maximum_weight_per_sector: event.target.value })} />
          <DecimalInput label="Máximo por emissor (%)" value={draft.maximum_weight_per_issuer} onChange={(event) => updateDraft(setDraft, { maximum_weight_per_issuer: event.target.value })} />
          <DecimalInput label="Tolerância de rebalanceamento (%)" value={draft.rebalance_tolerance} onChange={(event) => updateDraft(setDraft, { rebalance_tolerance: event.target.value })} />
          <label className="field"><span>Necessidade de renda</span><input type="checkbox" checked={draft.income_need} onChange={(event) => updateDraft(setDraft, { income_need: event.target.checked })} /></label>
          <div className="span-2">
            <strong>Total da alocação: {formatPercent(validation.total)}</strong>
            {validation.errors.map((error) => <p key={error} className="helper error-text">{error}</p>)}
          </div>
          <ResponsiveTable className="table-wrap span-2">
            <table>
              <thead><tr><th>Classe</th><th>Habilitada</th><th>Alvo</th><th>Mínimo</th><th>Máximo</th></tr></thead>
              <tbody>
                {draft.allocations.map((item) => (
                  <tr key={item.asset_class}>
                    <td>{item.asset_class}</td>
                    <td><input type="checkbox" checked={item.enabled} onChange={(event) => updateAllocation(setDraft, item.asset_class, { enabled: event.target.checked })} /></td>
                    <td><DecimalInput label={`Alvo ${item.asset_class}`} value={String(item.target_percentage)} onChange={(event) => updateAllocation(setDraft, item.asset_class, { target_percentage: event.target.value })} /></td>
                    <td><DecimalInput label={`Mínimo ${item.asset_class}`} value={String(item.minimum_percentage)} onChange={(event) => updateAllocation(setDraft, item.asset_class, { minimum_percentage: event.target.value })} /></td>
                    <td><DecimalInput label={`Máximo ${item.asset_class}`} value={String(item.maximum_percentage)} onChange={(event) => updateAllocation(setDraft, item.asset_class, { maximum_percentage: event.target.value })} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ResponsiveTable>
          <div className="button-row span-2">
            <Button type="submit" disabled={!validation.valid || save.isPending}>{save.isPending ? "Salvando..." : "Salvar estratégia"}</Button>
            <Button type="button" variant="secondary" onClick={() => setDraft(policy.data ? draftFromPolicy(policy.data) : emptyDraft())}>Restaurar valores salvos</Button>
          </div>
        </form>
      </Card>
    </div>
  );
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
  return (
    <div className="page-stack">
      <div className="score-grid">
        <ScoreGauge label="Score da carteira" value={diagnosis.portfolio_score} />
        <ScoreGauge label="Diversificação" value={diagnosis.diversification_score} />
        <ScoreGauge label="Concentração" value={diagnosis.concentration_score} />
        <ScoreGauge label="Liquidez" value={diagnosis.liquidity_score} />
        <ScoreGauge label="Renda" value={diagnosis.income_score} />
      </div>
      <div className="two-column">
        <Card title="Diagnóstico">
          <div className="button-row"><DataStatusBadge status={data.overview.market_data_status} /><span className="badge">Risco: {diagnosis.risk_level}</span><span className="badge">Qualidade: {diagnosis.data_quality}</span></div>
          <div className="metric-grid compact">
            <MetricCard label="Pontuação da carteira" value={formatPercent(diagnosis.portfolio_score)} />
            <MetricCard label="Diversificação" value={formatPercent(diagnosis.diversification_score)} />
            <MetricCard label="Concentração" value={formatPercent(diagnosis.concentration_score)} />
            <MetricCard label="Liquidez" value={diagnosis.liquidity_score === null ? "Indisponível" : formatPercent(diagnosis.liquidity_score)} />
            <MetricCard label="Renda" value={diagnosis.income_score === null ? "Indisponível" : formatPercent(diagnosis.income_score)} />
          </div>
        </Card>
        <Card title="Pontos de atenção">
          <TextList items={diagnosis.warnings.length ? diagnosis.warnings : ["Nenhum alerta crítico com os dados disponíveis."]} />
          <h3>Forças</h3>
          <TextList items={diagnosis.strengths} />
          <h3>Fraquezas</h3>
          <TextList items={diagnosis.weaknesses} />
        </Card>
      </div>
      <Card title="Distribuição por classe">
        <ClassAllocationTable items={diagnosis.class_allocations} />
        {diagnosis.unclassified_assets.length ? <p className="helper">Sem classe identificada: {diagnosis.unclassified_assets.join(", ")}.</p> : null}
      </Card>
    </div>
  );
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
        <MetricCard label="Preço atual" value={formatMoney(item.current_price)} />
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
  // "Montar carteira" busca a política diretamente (mesma query/endpoint
  // que Strategy usa: portfolio-policy -> GET /intelligence/policy) em vez
  // de receber via prop de intelligence.data.policy -- desacopla esta
  // área de uma eventual falha de /intelligence/portfolio (Correção
  // interface, resiliência). Ausência/erro de política nunca bloqueia o
  // formulário: os campos simplesmente seguem com os defaults abaixo até
  // (se) a política real chegar.
  const policyQuery = useQuery({
    queryKey: ["portfolio-policy", token],
    queryFn: () => endpoints.portfolioPolicy(token!),
    enabled: Boolean(token),
  });
  const policy = policyQuery.data ?? null;
  const appliedPolicyDefaults = useRef(false);
  const [availableAmount, setAvailableAmount] = useState("10000");
  const [monthlyContribution, setMonthlyContribution] = useState("0");
  const [objective, setObjective] = useState("crescimento patrimonial");
  const [horizon, setHorizon] = useState("médio prazo");
  const [riskProfile, setRiskProfile] = useState("moderado");
  const [liquidity, setLiquidity] = useState("média");
  const [maxAssets, setMaxAssets] = useState("10");
  const [maxAsset, setMaxAsset] = useState("20");
  const [maxClass, setMaxClass] = useState("40");
  const [income, setIncome] = useState("");
  const [essentialExpenses, setEssentialExpenses] = useState("");
  const [totalExpenses, setTotalExpenses] = useState("");
  const [reserve, setReserve] = useState("");
  const [debt, setDebt] = useState("0");
  const [currentAssets, setCurrentAssets] = useState("");
  const [desiredIncome, setDesiredIncome] = useState("");
  const [projectionYears, setProjectionYears] = useState("20");
  const [allowed, setAllowed] = useState<string[]>([]);
  const [prohibited, setProhibited] = useState<string[]>([]);

  useEffect(() => {
    if (appliedPolicyDefaults.current || policyQuery.isLoading || !policy) return;
    appliedPolicyDefaults.current = true;
    setMonthlyContribution(String(policy.monthly_contribution ?? "0"));
    setObjective(policy.objective ?? "crescimento patrimonial");
    setHorizon(policy.investment_horizon ?? "médio prazo");
    setRiskProfile(policy.risk_profile ?? "moderado");
    setLiquidity(policy.liquidity_need ?? "média");
    setMaxAsset(String(policy.maximum_weight_per_asset ?? "20"));
    setAllowed(policy.allocations.filter((item) => item.enabled).map((item) => item.asset_class));
  }, [policy, policyQuery.isLoading]);
  const toggleClass = (assetClass: string, target: "allowed" | "prohibited") => {
    const setter = target === "allowed" ? setAllowed : setProhibited;
    const otherSetter = target === "allowed" ? setProhibited : setAllowed;
    setter((current) => current.includes(assetClass) ? current.filter((item) => item !== assetClass) : [...current, assetClass]);
    otherSetter((current) => current.filter((item) => item !== assetClass));
  };
  const mutation = useMutation({
    mutationFn: () => endpoints.buildPortfolio(token!, {
      available_amount: normalizeDecimalForApi(availableAmount),
      objective,
      horizon,
      risk_profile: riskProfile,
      needs_emergency_reserve: true,
      emergency_months: policy?.emergency_reserve_months ?? 6,
      monthly_contribution: normalizeDecimalForApi(monthlyContribution),
      needs_income: policy?.income_need ?? false,
      needs_liquidity: liquidity !== "baixa",
      volatility_tolerance: "moderada",
      max_percentage_per_asset: normalizeDecimalForApi(maxAsset),
      max_percentage_per_class: normalizeDecimalForApi(maxClass),
      max_percentage_per_sector: normalizeDecimalForApi(policy?.maximum_weight_per_sector ?? "30"),
      allowed_classes: allowed,
      prohibited_classes: prohibited,
      max_assets: Number.parseInt(maxAssets, 10) || 1,
      ...(income ? { net_monthly_income: normalizeDecimalForApi(income) } : {}),
      ...(essentialExpenses ? { essential_monthly_expenses: normalizeDecimalForApi(essentialExpenses) } : {}),
      ...(totalExpenses ? { total_monthly_expenses: normalizeDecimalForApi(totalExpenses) } : {}),
      ...(reserve ? { emergency_reserve: normalizeDecimalForApi(reserve) } : {}),
      high_cost_debt: normalizeDecimalForApi(debt),
      ...(currentAssets ? { current_financial_assets: normalizeDecimalForApi(currentAssets) } : {}),
      ...(desiredIncome ? { desired_monthly_income: normalizeDecimalForApi(desiredIncome) } : {}),
      projection_years: Number.parseInt(projectionYears, 10) || 20,
      reinvest_income: true,
    }),
    onSuccess: (data) => queryClient.setQueryData(["portfolio-projection", token], data),
  });

  // Mesmo padrão de Strategy: aguarda a própria política resolver antes de
  // expor o formulário, garantindo que os defaults (allowed/objective/
  // etc., aplicados pelo useEffect acima) já estejam corretos quando o
  // formulário aparece -- nunca depende de /intelligence/portfolio, só da
  // própria política (portfolio-policy), independente e rápida.
  if (policyQuery.isLoading) return <LoadingState label="Carregando dados para montar a carteira..." />;

  return (
    <div className="page-stack smart-portfolio-flow">
      <Card title="Monte uma carteira para o seu momento">
        <p className="helper">Informe o essencial. Os demais parâmetros continuam disponíveis nas configurações avançadas.</p>
        <div className="warning-box">Simulação educacional. Não constitui ordem de compra e não oferece garantia de retorno.</div>
        <form className="form-grid two" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
          <CurrencyInput label="Valor disponível para investir" value={availableAmount} onChange={(event) => setAvailableAmount(event.target.value)} />
          <CurrencyInput label="Aporte mensal" value={monthlyContribution} onChange={(event) => setMonthlyContribution(event.target.value)} />
          <Select label="Objetivo" value={objective} onChange={(event) => setObjective(event.target.value)}><option value="reserva">Reserva</option><option value="renda">Renda</option><option value="crescimento patrimonial">Crescimento patrimonial</option><option value="preservação de capital">Preservação de capital</option></Select>
          <Select label="Horizonte" value={horizon} onChange={(event) => setHorizon(event.target.value)}><option value="curto prazo">Curto prazo</option><option value="médio prazo">Médio prazo</option><option value="longo prazo">Longo prazo</option></Select>
          <Select label="Perfil de risco" value={riskProfile} onChange={(event) => setRiskProfile(event.target.value)}><option value="conservador">Conservador</option><option value="moderado">Moderado</option><option value="arrojado">Arrojado</option></Select>
          <Input label="Quantidade máxima de ativos" inputMode="numeric" value={maxAssets} onChange={(event) => setMaxAssets(event.target.value.replace(/\D/g, ""))} />
          <details className="span-2 details-panel smart-advanced-settings">
            <summary>Configurações avançadas</summary>
            <div className="form-grid two">
              <Select label="Necessidade de liquidez" value={liquidity} onChange={(event) => setLiquidity(event.target.value)}><option value="baixa">Baixa</option><option value="média">Média</option><option value="alta">Alta</option></Select>
              <DecimalInput label="Limite por ativo (%)" value={maxAsset} onChange={(event) => setMaxAsset(event.target.value)} />
              <DecimalInput label="Limite por classe (%)" value={maxClass} onChange={(event) => setMaxClass(event.target.value)} />
              <CurrencyInput label="Renda mensal líquida" value={income} onChange={(event) => setIncome(event.target.value)} />
              <CurrencyInput label="Despesas essenciais" value={essentialExpenses} onChange={(event) => setEssentialExpenses(event.target.value)} />
              <CurrencyInput label="Despesas mensais totais" value={totalExpenses} onChange={(event) => setTotalExpenses(event.target.value)} />
              <CurrencyInput label="Reserva de emergência atual" value={reserve} onChange={(event) => setReserve(event.target.value)} />
              <CurrencyInput label="Dívidas de alto custo" value={debt} onChange={(event) => setDebt(event.target.value)} />
              <CurrencyInput label="Patrimônio financeiro atual" value={currentAssets} onChange={(event) => setCurrentAssets(event.target.value)} />
              <CurrencyInput label="Renda mensal desejada" value={desiredIncome} onChange={(event) => setDesiredIncome(event.target.value)} />
              <Input label="Anos da projeção" inputMode="numeric" value={projectionYears} onChange={(event) => setProjectionYears(event.target.value.replace(/\D/g, ""))} />
              <div className="span-2 class-restrictions">
                <strong>Classes permitidas e proibidas</strong>
                <p className="helper">Sem seleção em “permitida”, todas as classes não proibidas podem ser avaliadas.</p>
                {classes.map((assetClass) => <div key={assetClass} className="class-restriction-row"><span>{assetClass}</span><label><input type="checkbox" checked={allowed.includes(assetClass)} onChange={() => toggleClass(assetClass, "allowed")} /> Permitida</label><label><input type="checkbox" checked={prohibited.includes(assetClass)} onChange={() => toggleClass(assetClass, "prohibited")} /> Proibida</label></div>)}
              </div>
            </div>
          </details>
          {mutation.error ? <div className="span-2"><ErrorState message="Não foi possível montar sua carteira agora. Seus dados foram preservados."><Button type="button" variant="secondary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>Tentar novamente</Button></ErrorState></div> : null}
          <Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Analisando dados e montando sua carteira..." : "Montar minha carteira"}</Button>
        </form>
      </Card>
      {mutation.data ? <BuildResult data={mutation.data} totalConsidered={normalizeDecimalForApi(availableAmount)} /> : null}
    </div>
  );
}

function BuildResult({ data, totalConsidered }: { data: BuildPortfolioResponse; totalConsidered: string }) {
  const sortedAssets = [...data.assets].sort((left, right) => (parseBrazilianNumber(right.recommended_percentage) ?? 0) - (parseBrazilianNumber(left.recommended_percentage) ?? 0));
  return (
    <div className="page-stack smart-result">
      <Card title="Sua carteira recomendada">
        <div className="metric-grid compact smart-summary">
          <MetricCard label="Confiança" value={confidenceLabel(data.confidence)} />
          <MetricCard label="Valor total considerado" value={formatMoney(totalConsidered)} />
          <MetricCard label="Valor alocado" value={formatMoney(data.total_allocated_amount)} />
          <MetricCard label="Saldo não alocado" value={formatMoney(data.unallocated_amount)} />
          <MetricCard label="Quantidade de ativos" value={sortedAssets.length} />
          {(data.existing_positions_count ?? 0) > 0 ? <MetricCard label="Carteira registrada" value={formatMoney(data.existing_portfolio_value)} /> : null}
        </div>
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
      <ResultDetails title="Ativos não incluídos">{data.exclusions.length ? <ResponsiveTable className="table-wrap"><table><thead><tr><th>Ativo</th><th>Classe</th><th>Motivo</th></tr></thead><tbody>{data.exclusions.map((item) => <tr key={item.symbol}><td>{item.symbol}</td><td>{item.asset_class}</td><td>{item.reasons.join(" ")}</td></tr>)}</tbody></table></ResponsiveTable> : <p>Nenhum ativo adicional foi excluído.</p>}</ResultDetails>
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

function emptyDraft(): PolicyDraft {
  return {
    name: "Minha estratégia",
    objective: "crescimento patrimonial",
    risk_profile: "moderado",
    investment_horizon: "médio prazo",
    monthly_contribution: "0",
    liquidity_need: "média",
    income_need: false,
    emergency_reserve_months: "6",
    maximum_weight_per_asset: "20",
    maximum_weight_per_sector: "30",
    maximum_weight_per_issuer: "30",
    rebalance_tolerance: "5",
    allocations: classes.map((assetClass) => ({
      asset_class: assetClass,
      target_percentage: "0",
      minimum_percentage: "0",
      maximum_percentage: "0",
      enabled: false,
    })),
  };
}

function draftFromPolicy(policy: PortfolioPolicy): PolicyDraft {
  const byClass = new Map(policy.allocations.map((item) => [item.asset_class, item]));
  return {
    name: policy.name,
    objective: policy.objective,
    risk_profile: policy.risk_profile,
    investment_horizon: policy.investment_horizon,
    monthly_contribution: String(policy.monthly_contribution),
    liquidity_need: policy.liquidity_need,
    income_need: policy.income_need,
    emergency_reserve_months: String(policy.emergency_reserve_months),
    maximum_weight_per_asset: String(policy.maximum_weight_per_asset),
    maximum_weight_per_sector: String(policy.maximum_weight_per_sector),
    maximum_weight_per_issuer: String(policy.maximum_weight_per_issuer),
    rebalance_tolerance: String(policy.rebalance_tolerance),
    allocations: classes.map((assetClass) => {
      const saved = byClass.get(assetClass);
      return {
        asset_class: assetClass,
        target_percentage: String(saved?.target_percentage ?? "0"),
        minimum_percentage: String(saved?.minimum_percentage ?? "0"),
        maximum_percentage: String(saved?.maximum_percentage ?? "0"),
        enabled: saved?.enabled ?? false,
      };
    }),
  };
}

function payloadFromDraft(draft: PolicyDraft): PortfolioPolicyPayload {
  return {
    name: draft.name,
    objective: draft.objective,
    risk_profile: draft.risk_profile,
    investment_horizon: draft.investment_horizon,
    monthly_contribution: normalizeDecimalForApi(draft.monthly_contribution),
    liquidity_need: draft.liquidity_need,
    income_need: draft.income_need,
    emergency_reserve_months: Number.parseInt(draft.emergency_reserve_months, 10) || 0,
    maximum_weight_per_asset: normalizeDecimalForApi(draft.maximum_weight_per_asset),
    maximum_weight_per_sector: normalizeDecimalForApi(draft.maximum_weight_per_sector),
    maximum_weight_per_issuer: normalizeDecimalForApi(draft.maximum_weight_per_issuer),
    rebalance_tolerance: normalizeDecimalForApi(draft.rebalance_tolerance),
    allocations: draft.allocations.map((item) => ({
      asset_class: item.asset_class,
      target_percentage: normalizeDecimalForApi(item.target_percentage),
      minimum_percentage: normalizeDecimalForApi(item.minimum_percentage),
      maximum_percentage: normalizeDecimalForApi(item.maximum_percentage),
      enabled: item.enabled,
    })),
  };
}

function validateDraft(draft: PolicyDraft) {
  const errors = [];
  const enabled = draft.allocations.filter((item) => item.enabled);
  const total = enabled.reduce((sum, item) => sum + (parseBrazilianNumber(item.target_percentage) ?? 0), 0);
  if (!enabled.length) errors.push("Habilite pelo menos uma classe.");
  if (Math.abs(total - 100) > 0.0001) errors.push("A soma das classes habilitadas deve ser exatamente 100%.");
  for (const item of draft.allocations) {
    const target = parseBrazilianNumber(item.target_percentage) ?? 0;
    const minimum = parseBrazilianNumber(item.minimum_percentage) ?? 0;
    const maximum = parseBrazilianNumber(item.maximum_percentage) ?? 0;
    if ([target, minimum, maximum].some((value) => value < 0)) errors.push("Percentuais não podem ser negativos.");
    if (minimum > target) errors.push(`Em ${item.asset_class}, o mínimo não pode ser maior que o alvo.`);
    if (target > maximum) errors.push(`Em ${item.asset_class}, o alvo não pode ser maior que o máximo.`);
  }
  return { total, errors: [...new Set(errors)], valid: errors.length === 0 };
}

function updateDraft(setDraft: (value: SetStateAction<PolicyDraft>) => void, value: Partial<PolicyDraft>) {
  setDraft((current) => ({ ...current, ...value }));
}

function updateAllocation(
  setDraft: (value: SetStateAction<PolicyDraft>) => void,
  assetClass: string,
  value: Partial<PolicyDraft["allocations"][number]>,
) {
  setDraft((current) => ({
    ...current,
    allocations: current.allocations.map((item) => item.asset_class === assetClass ? { ...item, ...value } : item),
  }));
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
