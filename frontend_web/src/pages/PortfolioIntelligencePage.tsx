import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type SetStateAction } from "react";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { DecimalInput } from "../components/forms/DecimalInput";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { MetricCard } from "../components/ui/MetricCard";
import { Select } from "../components/ui/Select";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type {
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
  const [tab, setTab] = useState(tabs[0]);
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
      <section className="page-heading">
        <div>
          <h2>Inteligência de Carteira</h2>
          <p>Analise sua carteira, encontre possíveis desequilíbrios e descubra como direcionar seus próximos investimentos.</p>
        </div>
      </section>
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
      <div className="two-column">
        <Card title="Diagnóstico">
          <div className="metric-grid compact">
            <MetricCard label="Pontuação da carteira" value={formatPercent(diagnosis.portfolio_score)} />
            <MetricCard label="Diversificação" value={formatPercent(diagnosis.diversification_score)} />
            <MetricCard label="Concentração" value={formatPercent(diagnosis.concentration_score)} />
            <MetricCard label="Liquidez" value="Dados insuficientes para calcular." />
            <MetricCard label="Renda" value="Dados insuficientes para calcular." />
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
  if (!data.policy) return <EmptyState title="Configure sua estratégia para receber análises e sugestões personalizadas." />;
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
  const mutation = useMutation({
    mutationFn: () => endpoints.buildPortfolio(token!, {
      available_amount: normalizeDecimalForApi(availableAmount),
      objective: policy?.objective ?? "crescimento patrimonial",
      horizon: policy?.investment_horizon ?? "médio prazo",
      risk_profile: policy?.risk_profile ?? "moderado",
      needs_emergency_reserve: true,
      emergency_months: policy?.emergency_reserve_months ?? 6,
      monthly_contribution: normalizeDecimalForApi(policy?.monthly_contribution ?? "0"),
      needs_income: policy?.income_need ?? false,
      needs_liquidity: policy?.liquidity_need !== "baixa",
      volatility_tolerance: "moderada",
      max_percentage_per_asset: normalizeDecimalForApi(policy?.maximum_weight_per_asset ?? "0"),
      max_percentage_per_class: "100",
      max_percentage_per_sector: normalizeDecimalForApi(policy?.maximum_weight_per_sector ?? "0"),
      allowed_classes: policy?.allocations.filter((item) => item.enabled).map((item) => item.asset_class) ?? [],
    }),
  });
  if (!policy) return <EmptyState title="Configure sua estratégia para montar uma carteira alinhada à sua política." />;
  return (
    <div className="page-stack">
      <Card title="Montar carteira">
        <form className="form-grid two" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
          <CurrencyInput label="Valor disponível" value={availableAmount} onChange={(event) => setAvailableAmount(event.target.value)} />
          <MetricCard label="Estratégia usada" value={policy.name} />
          <Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Gerando..." : "Gerar resultado"}</Button>
        </form>
      </Card>
      {mutation.data ? <BuildResult data={mutation.data} /> : null}
    </div>
  );
}

function BuildResult({ data }: { data: BuildPortfolioResponse }) {
  if (!data.class_allocations.length) return <EmptyState title="Configure sua estratégia para montar uma carteira alinhada à sua política." />;
  return (
    <Card title="Resultado">
      <h3>Etapa 1 - Alocação entre classes</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Classe</th><th>Percentual</th><th>Valor sugerido</th><th>Explicação</th></tr></thead>
          <tbody>{data.class_allocations.map((item) => <tr key={item.asset_class}><td>{item.asset_class}</td><td>{formatPercent(item.percentage)}</td><td>{formatMoney(item.amount)}</td><td>{item.explanation}</td></tr>)}</tbody>
        </table>
      </div>
      <h3>Etapa 2 - Seleção dentro de cada classe</h3>
      <TextList items={data.selections.map((item) => `${item.asset_class}: ${item.message}`)} />
    </Card>
  );
}

function Opportunities({ data }: { data: PortfolioIntelligence }) {
  if (!data.opportunities.length) return <EmptyState title="Dados insuficientes para calcular." />;
  return (
    <div className="page-stack">
      {data.opportunities.map((item) => (
        <Card key={item.asset_class} title={item.asset_class}>
          <div className="metric-grid compact">
            <MetricCard label="Classificação" value={item.classification} />
            <MetricCard label="Confiança" value={item.confidence} />
          </div>
          <p>{item.highlight_reason}</p>
          <TextList items={item.risks} />
        </Card>
      ))}
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
