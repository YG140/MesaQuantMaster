import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode, type SetStateAction } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
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
import { endpoints } from "../services/endpoints/data";
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
  formatMoney,
  formatPercent,
  normalizeDecimalForApi,
  parseBrazilianNumber,
} from "../utils/formatters";

const tabs = ["Minha estratégia", "Visão geral", "Diagnóstico", "Recomendações", "Rebalanceamento", "Montar carteira", "Oportunidades"];
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
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const initialTab = location.pathname === "/analisar"
    ? "Diagnóstico"
    : location.pathname === "/planejar"
      ? "Minha estratégia"
      : location.pathname === "/investir" || searchParams.get("area") === "investir"
        ? "Montar carteira"
        : tabs[0];
  const [tab, setTab] = useState(initialTab);
  const intelligence = useQuery({
    queryKey: ["portfolio-intelligence", token],
    queryFn: () => endpoints.portfolioIntelligence(token!),
    enabled: Boolean(token),
  });

  if (intelligence.isLoading) return <LoadingState label="Carregando inteligência da carteira..." />;
  if (intelligence.error) return <ErrorState message="Não foi possível carregar a inteligência da carteira." />;
  if (!intelligence.data) return <EmptyState title="Dados insuficientes para calcular." />;

  return (
    <div className="page-stack">
      <SectionHeader eyebrow={location.pathname === "/planejar" ? "Planejar" : location.pathname.includes("invest") ? "Investir" : "Analisar"} title="Inteligência de Carteira" description="Diagnóstico quantitativo, estratégia e próximos movimentos calculados pelo MesaQuantMaster." />
      <div className="tabs" role="tablist" aria-label="Áreas de inteligência">
        {tabs.map((item) => (
          <button key={item} type="button" className={item === tab ? "active" : ""} onClick={() => setTab(item)}>
            {item}
          </button>
        ))}
      </div>
      {tab === "Minha estratégia" ? <Strategy /> : null}
      {tab === "Visão geral" ? <Overview data={intelligence.data} /> : null}
      {tab === "Diagnóstico" ? <Diagnosis data={intelligence.data} /> : null}
      {tab === "Recomendações" ? <Recommendations data={intelligence.data} /> : null}
      {tab === "Rebalanceamento" ? <Rebalancing data={intelligence.data} /> : null}
      {tab === "Montar carteira" ? <BuildPortfolio policy={intelligence.data.policy} /> : null}
      {tab === "Oportunidades" ? <Opportunities data={intelligence.data} /> : null}
    </div>
  );
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
          <div className="table-wrap span-2">
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
          </div>
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
        <MetricCard label="Atualização" value={formatDateTimeBR(item.market_updated_at)} />
      </div>
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
    <div className="table-wrap">
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
              <td>{item.explanation || item.description || "Não informado"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Rebalancing({ data }: { data: PortfolioIntelligence }) {
  if (!data.policy) return <EmptyState title="Configure sua estratégia para receber análises e sugestões personalizadas." />;
  if (!data.rebalancing.length) return <EmptyState title="Dados insuficientes para calcular." />;
  return (
    <Card title="Rebalanceamento">
      <div className="table-wrap">
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
      </div>
    </Card>
  );
}

function BuildPortfolio({ policy }: { policy: PortfolioPolicy | null }) {
  const { token } = useAuth();
  const [availableAmount, setAvailableAmount] = useState("10000");
  const [monthlyContribution, setMonthlyContribution] = useState(String(policy?.monthly_contribution ?? "0"));
  const [objective, setObjective] = useState(policy?.objective ?? "crescimento patrimonial");
  const [horizon, setHorizon] = useState(policy?.investment_horizon ?? "médio prazo");
  const [riskProfile, setRiskProfile] = useState(policy?.risk_profile ?? "moderado");
  const [liquidity, setLiquidity] = useState(policy?.liquidity_need ?? "média");
  const [maxAssets, setMaxAssets] = useState("10");
  const [maxAsset, setMaxAsset] = useState(String(policy?.maximum_weight_per_asset ?? "20"));
  const [maxClass, setMaxClass] = useState("40");
  const [income, setIncome] = useState("");
  const [essentialExpenses, setEssentialExpenses] = useState("");
  const [totalExpenses, setTotalExpenses] = useState("");
  const [reserve, setReserve] = useState("");
  const [debt, setDebt] = useState("0");
  const [currentAssets, setCurrentAssets] = useState("");
  const [desiredIncome, setDesiredIncome] = useState("");
  const [projectionYears, setProjectionYears] = useState("20");
  const [allowed, setAllowed] = useState<string[]>(policy?.allocations.filter((item) => item.enabled).map((item) => item.asset_class) ?? []);
  const [prohibited, setProhibited] = useState<string[]>([]);
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
  });
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
        </div>
        {!sortedAssets.length ? <div className="smart-insufficient"><h3>Ainda não há dados suficientes para recomendar ativos.</h3><p>O valor não alocado permanece disponível. Revise os dados ausentes abaixo ou tente novamente.</p><TextList items={data.missing_data} fallback="A cobertura atual não permite uma recomendação segura." /></div> : (
          <div className="recommended-assets" aria-label="Ativos recomendados">
            {sortedAssets.map((asset) => <article className="recommended-asset" key={asset.symbol}>
              <div><strong>{asset.symbol}</strong><span>{asset.asset_class}</span></div>
              <div><small>Percentual</small><b>{formatPercent(asset.recommended_percentage)}</b></div>
              <div><small>Valor</small><b>{formatMoney(asset.recommended_amount)}</b></div>
              <div><small>Confiança</small><b>{confidenceLabel(asset.confidence)}</b></div>
              <details className="asset-details"><summary>Ver detalhes</summary><div className="asset-detail-content"><h4>Justificativas</h4><TextList items={asset.reasons} /><h4>Riscos</h4><TextList items={asset.risks} fallback="Nenhum risco adicional identificado com os dados disponíveis." /><h4>Indicadores e procedência</h4><div className="table-wrap"><table><thead><tr><th>Indicador</th><th>Fonte</th><th>Referência</th><th>Validade</th></tr></thead><tbody>{asset.indicators_used.map((item) => <tr key={item.key}><td>{item.label}</td><td>{item.source}</td><td>{formatDateTimeBR(item.reference_date)}</td><td>{formatDateTimeBR(item.valid_until)}</td></tr>)}</tbody></table></div><h4>Dados ausentes</h4><TextList items={asset.missing_data} fallback="Nenhum dado ausente entre os indicadores aplicáveis." /></div></details>
            </article>)}
          </div>
        )}
        <p className="helper smart-disclaimer">{data.disclaimer}</p>
      </Card>
      <ResultDetails title="Por que esta carteira?"><p>{data.strategy_summary}</p><TextList items={data.selections.map((item) => `${item.asset_class}: ${item.message}`)} /></ResultDetails>
      <ResultDetails title="Riscos e cuidados"><TextList items={[...data.diagnosis.debt_alerts, ...data.freedom_goal.risks]} fallback="Nenhum cuidado adicional foi identificado com os dados disponíveis." /></ResultDetails>
      <ResultDetails title="Distribuição por classe">{!data.class_allocations.length ? <EmptyState title="Cobertura insuficiente para alocar com segurança." /> : <div className="table-wrap"><table><thead><tr><th>Classe</th><th>Percentual</th><th>Valor sugerido</th><th>Explicação</th></tr></thead><tbody>{data.class_allocations.map((item) => <tr key={item.asset_class}><td>{item.asset_class}</td><td>{formatPercent(item.percentage)}</td><td>{formatMoney(item.amount)}</td><td>{item.explanation}</td></tr>)}</tbody></table></div>}</ResultDetails>
      <ResultDetails title="Planejamento financeiro"><div className="metric-grid compact"><MetricCard label="Fase" value={data.diagnosis.phase} /><MetricCard label="Capacidade mensal estimada" value={formatMoney(data.diagnosis.estimated_monthly_capacity)} /><MetricCard label="Meta de reserva" value={formatMoney(data.diagnosis.reserve_target)} /><MetricCard label="Progresso do objetivo" value={formatPercent(data.freedom_goal.achieved_percentage)} /></div><TextList items={[...data.diagnosis.priority_actions, ...data.freedom_goal.improvement_actions]} /><div className="table-wrap"><table><thead><tr><th>Cenário</th><th>Total aportado</th><th>Patrimônio projetado</th><th>Renda estimada</th></tr></thead><tbody>{data.projections.map((item) => <tr key={item.name}><td>{item.name}</td><td>{formatMoney(item.total_contributed)}</td><td>{formatMoney(item.projected_wealth)}</td><td>{formatMoney(item.estimated_periodic_income)}</td></tr>)}</tbody></table></div></ResultDetails>
      <ResultDetails title="Carteira executável">{!sortedAssets.length ? <p>Sem ativos executáveis.</p> : <div className="table-wrap"><table><thead><tr><th>Ativo</th><th>Preço</th><th>Quantidade</th><th>Valor executável</th><th>Diferença do alvo</th></tr></thead><tbody>{sortedAssets.map((asset) => <tr key={`execution-${asset.symbol}`}><td>{asset.symbol}</td><td>{formatMoney(asset.reference_price)}</td><td>{asset.executable_quantity ?? "—"}</td><td>{formatMoney(asset.executable_amount)}</td><td>{formatMoney(asset.target_gap)}</td></tr>)}</tbody></table></div>}</ResultDetails>
      <ResultDetails title="Plano de aportes">{!data.contribution_plan.length ? <p>Sem aporte mensal informado.</p> : <div className="table-wrap"><table><thead><tr><th>Prioridade</th><th>Destino</th><th>Valor</th><th>Motivo</th></tr></thead><tbody>{data.contribution_plan.map((item) => <tr key={`${item.priority}-${item.symbol}`}><td>{item.priority}</td><td>{item.symbol}</td><td>{formatMoney(item.suggested_amount)}</td><td>{item.reason}</td></tr>)}</tbody></table></div>}</ResultDetails>
      <ResultDetails title="Dados e fontes"><TextList items={[...data.missing_data, ...sortedAssets.flatMap((asset) => asset.execution_impediments)]} fallback="Sem avisos adicionais sobre dados e fontes." /></ResultDetails>
      <ResultDetails title="Ativos não incluídos">{data.exclusions.length ? <div className="table-wrap"><table><thead><tr><th>Ativo</th><th>Classe</th><th>Motivo</th></tr></thead><tbody>{data.exclusions.map((item) => <tr key={item.symbol}><td>{item.symbol}</td><td>{item.asset_class}</td><td>{item.reasons.join(" ")}</td></tr>)}</tbody></table></div> : <p>Nenhum ativo adicional foi excluído.</p>}</ResultDetails>
    </div>
  );
}

function ResultDetails({ title, children }: { title: string; children: ReactNode }) {
  return <details className="details-panel smart-result-details"><summary>{title}</summary><div className="smart-detail-body">{children}</div></details>;
}

function Opportunities({ data }: { data: PortfolioIntelligence }) {
  const { token } = useAuth();
  const macro = useQuery({
    queryKey: ["macro-context", token],
    queryFn: () => endpoints.macroContext(token!),
    enabled: Boolean(token),
  });
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
          <div className="table-wrap">
            <table>
              <thead><tr><th>Indicador</th><th>Estado</th><th>Frequência</th><th>Fonte</th></tr></thead>
              <tbody>{macro.data.map((item) => <tr key={item.key}><td>{item.label}</td><td>{statusLabel(item.state)}</td><td>{item.frequency}</td><td>{item.source}</td></tr>)}</tbody>
            </table>
          </div>
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
    <div className="table-wrap">
      <table>
        <thead><tr><th>Classe</th><th>Valor atual</th><th>Atual</th><th>Meta</th><th>Mínimo</th><th>Máximo</th><th>Diferença</th><th>Status</th></tr></thead>
        <tbody>{items.map((item) => <tr key={item.asset_class}><td>{item.asset_class}</td><td>{formatMoney(item.current_value)}</td><td>{formatPercent(item.current_percentage)}</td><td>{formatPercent(item.target_percentage)}</td><td>{formatPercent(item.minimum_percentage)}</td><td>{formatPercent(item.maximum_percentage)}</td><td>{formatPercent(item.difference_percentage)}</td><td>{item.status}</td></tr>)}</tbody>
      </table>
    </div>
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
