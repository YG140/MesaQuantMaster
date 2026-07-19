import { useQuery } from "@tanstack/react-query";
import { AllocationChart } from "../components/charts/AllocationChart";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Card } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import { formatPercent, toNumber } from "../utils/formatters";

export function AnalysisPage() {
  const { token } = useAuth();
  const portfolio = useQuery({ queryKey: ["portfolio", token], queryFn: () => endpoints.portfolio(token!), enabled: Boolean(token) });
  if (portfolio.isLoading) return <LoadingState />;
  if (portfolio.error) return <ErrorState message="Não foi possível carregar análises." />;
  const positions = Array.isArray(portfolio.data?.positions) ? portfolio.data.positions : [];
  if (!positions.length) return <EmptyState title="Sua carteira ainda está vazia." />;
  const largest = positions.reduce((max, item) => (toNumber(item.allocation ?? item.weight) ?? 0) > (toNumber(max.allocation ?? max.weight) ?? 0) ? item : max, positions[0]);
  const largestAllocation = toNumber(largest.allocation ?? largest.weight);
  const chartData = positions
    .map((item) => ({ name: item.ticker, value: toNumber(item.allocation ?? item.weight) ?? 0 }))
    .filter((item) => item.value > 0);
  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Análises</h2><p>Diversificação, concentração e distribuição da carteira.</p></section>
      <div className="metric-grid">
        <MetricCard label="Posições analisadas" value={positions.length} />
        <MetricCard label="Maior concentracao" value={formatPercent(largestAllocation)} />
        <MetricCard label="Ativo mais representativo" value={largest.ticker} />
        <MetricCard label="Base da alocação" value={portfolio.data?.valuation_basis ?? "Não informado"} />
      </div>
      <Card title="Distribuição">{chartData.length ? <AllocationChart data={chartData} /> : <p>Ainda não há informação de alocação para exibir.</p>}</Card>
      <Card title="Alertas de risco"><p>{(largestAllocation ?? 0) >= 50 ? "Carteira concentrada em uma posição relevante." : "Sem alertas críticos de concentração."}</p></Card>
    </div>
  );
}
