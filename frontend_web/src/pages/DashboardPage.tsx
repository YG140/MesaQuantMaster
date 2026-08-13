import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AllocationChart } from "../components/charts/AllocationChart";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { DataStatusBadge } from "../components/ui/DataBadges";
import { MetricCard } from "../components/ui/MetricCard";
import { QuantumCard } from "../components/ui/QuantumCard";
import { SectionHeader } from "../components/ui/SectionHeader";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type { PortfolioPosition, PortfolioSummary } from "../types/api";
import { formatDateTimeBR, formatMoney, formatPercent, toNumber } from "../utils/formatters";

type ChartPoint = {
  name: string;
  value: number;
};

export function DashboardPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const dashboard = useQuery({
    queryKey: ["dashboard", token],
    queryFn: () => endpoints.dashboard(token!),
    enabled: Boolean(token),
  });
  const portfolio = useQuery({
    queryKey: ["portfolio", token],
    queryFn: () => endpoints.portfolio(token!),
    enabled: Boolean(token),
  });

  if (dashboard.isLoading || portfolio.isLoading) return <LoadingState />;
  if (dashboard.error || portfolio.error) {
    return (
      <ErrorState message="Não foi possível carregar o início. Verifique se a API está disponível.">
        <Button type="button" variant="secondary" onClick={() => void Promise.all([dashboard.refetch(), portfolio.refetch()])}>
          Tentar novamente
        </Button>
      </ErrorState>
    );
  }

  const portfolioData = portfolio.data;
  const dashboardData = dashboard.data;
  const positions = validPositions(portfolioData?.positions);

  if (!positions.length) {
    return (
      <div className="page-stack">
        <section className="page-heading">
          <h2>Início</h2>
          <p>Visão consolidada da sua carteira.</p>
        </section>
        <EmptyState title="Sua carteira ainda está vazia.">
          <div className="button-row">
            <Link className="button button-primary" to="/investimentos/novo">Adicionar investimento</Link>
            <Link className="button button-secondary" to="/carteira/importar">Importar carteira existente</Link>
          </div>
        </EmptyState>
      </div>
    );
  }

  const allocation = allocationPoints(portfolioData);
  const concentration = maxConcentration(positions, allocation);
  const operationsCount = dashboardData?.operations_count ?? dashboardData?.operacoes ?? 0;
  const refreshing = dashboard.isFetching || portfolio.isFetching;
  const refreshQuotes = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dashboard", token] }),
      queryClient.invalidateQueries({ queryKey: ["portfolio", token] }),
    ]);
  };

  return (
    <div className="page-stack">
      <SectionHeader eyebrow="Acompanhar" title="Seu universo financeiro" description="Acompanhe patrimônio, desempenho e qualidade dos dados em tempo real." actions={
        <Button type="button" variant="secondary" disabled={refreshing} onClick={() => void refreshQuotes()}>
          {refreshing ? "Atualizando..." : "Atualizar cotações"}
        </Button>
      } />
      <MarketDataNotice
        status={dashboardData?.market_data_status ?? portfolioData?.market_data_status}
        quoteUpdatedAt={dashboardData?.quote_updated_at ?? portfolioData?.quote_updated_at}
        unpricedSymbols={dashboardData?.unpriced_symbols ?? portfolioData?.unpriced_symbols ?? []}
      />
      <div className="metric-grid">
        <MetricCard label="Patrimônio" value={formatMoney(dashboardData?.patrimonio_total ?? portfolioData?.total_market_value)} helper="Valor de mercado disponível" />
        <MetricCard label="Valor investido" value={formatMoney(portfolioData?.total_invested)} />
        <MetricCard label="Lucro ou prejuízo" value={formatMoney(portfolioData?.total_profit)} />
        <MetricCard label="Rentabilidade" value={formatPercent(portfolioData?.profitability)} />
        <MetricCard label="Ativos" value={dashboardData?.ativos ?? positions.length} />
        <MetricCard label="Movimentações" value={operationsCount} />
      </div>
      <div className="quick-action-grid">
        <Link className="quick-action" to="/investimentos/novo"><span>01</span><strong>Novo aporte</strong><small>Registre um investimento</small></Link>
        <Link className="quick-action" to="/carteira"><span>02</span><strong>Ver carteira</strong><small>Posições e movimentações</small></Link>
        <Link className="quick-action" to="/analisar"><span>03</span><strong>Analisar</strong><small>Risco e diagnóstico</small></Link>
        <Link className="quick-action" to="/planejar"><span>04</span><strong>Planejar</strong><small>Estratégia e objetivos</small></Link>
      </div>
      <div className="two-column">
        <Card title="Alocação">
          {allocation.length ? <AllocationChart data={allocation} /> : <p>Ainda não há informação de alocação para exibir.</p>}
        </Card>
        <Card title="Resumo de risco">
          <DataStatusBadge status={dashboardData?.market_data_status ?? portfolioData?.market_data_status} />
          <div className="metric-grid compact">
            <MetricCard label="Posições" value={positions.length} />
            <MetricCard label="Maior concentração" value={formatPercent(concentration)} />
            <MetricCard
              label="Risco"
              value={concentration !== null && concentration >= 50 ? "Concentrado" : "Diversificado"}
              tone={concentration !== null && concentration >= 50 ? "bad" : "good"}
            />
          </div>
        </Card>
      </div>
      <QuantumCard className="data-provenance">
        <div><span className="eyebrow">Integridade</span><h3>Leitura responsável dos dados</h3></div>
        <p>Ativos sem preço permanecem identificados como indisponíveis e não são convertidos em zero.</p>
      </QuantumCard>
    </div>
  );
}

function MarketDataNotice({
  status,
  quoteUpdatedAt,
  unpricedSymbols,
}: {
  status: string | null | undefined;
  quoteUpdatedAt: string | null | undefined;
  unpricedSymbols: string[];
}) {
  if (status === "live") {
    return (
      <div className="success-box">
        Cotações atualizadas em {formatDateTimeBR(quoteUpdatedAt)}.
      </div>
    );
  }
  if (status === "partial") {
    return (
      <div className="warning-box">
        Alguns ativos estão sem cotação atual. Os demais valores foram atualizados.
        {unpricedSymbols.length ? ` Sem cotação: ${unpricedSymbols.join(", ")}.` : ""}
      </div>
    );
  }
  return (
    <div className="warning-box">
      Não foi possível atualizar as cotações agora. Sua carteira continua disponível.
    </div>
  );
}

function validPositions(positions: PortfolioSummary["positions"]): PortfolioPosition[] {
  return Array.isArray(positions) ? positions : [];
}

function allocationPoints(portfolio: PortfolioSummary | undefined): ChartPoint[] {
  const allocation = Array.isArray(portfolio?.allocation) ? portfolio.allocation : [];
  return allocation.reduce<ChartPoint[]>((items, item) => {
    const value = toNumber(item.allocation ?? item.weight);
    const name = item.ticker ?? item.asset ?? item.name;
    if (typeof name === "string" && name.trim() && value !== null && value > 0) {
      items.push({ name: name.trim(), value });
    }
    return items;
  }, []);
}

function maxConcentration(positions: PortfolioPosition[], allocation: ChartPoint[]): number | null {
  const positionValues = positions
    .map((position) => toNumber(position.allocation ?? position.weight))
    .filter((value): value is number => value !== null && value >= 0);
  const allocationValues = allocation.map((item) => item.value);
  const values = positionValues.length ? positionValues : allocationValues;
  return values.length ? Math.max(...values) : null;
}
