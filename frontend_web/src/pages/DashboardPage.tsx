import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AllocationChart } from "../components/charts/AllocationChart";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type { PortfolioPosition, PortfolioSummary } from "../types/api";
import { formatMoney, formatPercent, toNumber } from "../utils/formatters";

type ChartPoint = {
  name: string;
  value: number;
};

export function DashboardPage() {
  const { token } = useAuth();
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
      <ErrorState message="Nao foi possivel carregar o inicio. Verifique se a API esta disponivel.">
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
          <h2>Inicio</h2>
          <p>Visao consolidada da sua carteira.</p>
        </section>
        <EmptyState title="Sua carteira ainda esta vazia.">
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

  return (
    <div className="page-stack">
      <section className="page-heading">
        <h2>Inicio</h2>
        <p>Visao consolidada da sua carteira.</p>
      </section>
      <div className="metric-grid">
        <MetricCard label="Patrimonio" value={formatMoney(portfolioData?.total_market_value)} />
        <MetricCard label="Valor investido" value={formatMoney(portfolioData?.total_invested)} />
        <MetricCard label="Lucro ou prejuizo" value={formatMoney(portfolioData?.total_profit)} />
        <MetricCard label="Rentabilidade" value={formatPercent(portfolioData?.profitability)} />
        <MetricCard label="Ativos" value={dashboardData?.ativos ?? positions.length} />
        <MetricCard label="Movimentacoes" value={operationsCount} />
      </div>
      <div className="two-column">
        <Card title="Alocacao">
          {allocation.length ? <AllocationChart data={allocation} /> : <p>Ainda nao ha informacao de alocacao para exibir.</p>}
        </Card>
        <Card title="Resumo de risco">
          <div className="metric-grid compact">
            <MetricCard label="Posicoes" value={positions.length} />
            <MetricCard label="Maior concentracao" value={formatPercent(concentration)} />
            <MetricCard
              label="Risco"
              value={concentration !== null && concentration >= 50 ? "Concentrado" : "Diversificado"}
              tone={concentration !== null && concentration >= 50 ? "bad" : "good"}
            />
          </div>
        </Card>
      </div>
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
