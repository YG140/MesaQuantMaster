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
  if (portfolio.error) return <ErrorState message="Nao foi possivel carregar analises." />;
  const positions = Array.isArray(portfolio.data?.positions) ? portfolio.data.positions : [];
  if (!positions.length) return <EmptyState title="Sua carteira ainda esta vazia." />;
  const largest = positions.reduce((max, item) => (toNumber(item.allocation ?? item.weight) ?? 0) > (toNumber(max.allocation ?? max.weight) ?? 0) ? item : max, positions[0]);
  const largestAllocation = toNumber(largest.allocation ?? largest.weight);
  const chartData = positions
    .map((item) => ({ name: item.ticker, value: toNumber(item.allocation ?? item.weight) ?? 0 }))
    .filter((item) => item.value > 0);
  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Analises</h2><p>Diversificacao, concentracao e distribuicao da carteira.</p></section>
      <div className="metric-grid">
        <MetricCard label="Posicoes analisadas" value={positions.length} />
        <MetricCard label="Maior concentracao" value={formatPercent(largestAllocation)} />
        <MetricCard label="Ativo mais representativo" value={largest.ticker} />
        <MetricCard label="Base da alocacao" value={portfolio.data?.valuation_basis ?? "Nao informado"} />
      </div>
      <Card title="Distribuicao">{chartData.length ? <AllocationChart data={chartData} /> : <p>Ainda nao ha informacao de alocacao para exibir.</p>}</Card>
      <Card title="Alertas de risco"><p>{(largestAllocation ?? 0) >= 50 ? "Carteira concentrada em uma posicao relevante." : "Sem alertas criticos de concentracao."}</p></Card>
    </div>
  );
}
