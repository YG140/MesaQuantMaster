import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AllocationChart } from "../components/charts/AllocationChart";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Card } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import { formatMoney, formatPercent, formatQuantityBR, toNumber } from "../utils/formatters";

export function PortfolioPage() {
  const { token } = useAuth();
  const portfolio = useQuery({ queryKey: ["portfolio", token], queryFn: () => endpoints.portfolio(token!), enabled: Boolean(token) });
  const operations = useQuery({ queryKey: ["operations", token], queryFn: () => endpoints.operations(token!), enabled: Boolean(token) });

  if (portfolio.isLoading || operations.isLoading) return <LoadingState />;
  if (portfolio.error || operations.error) return <ErrorState message="Nao foi possivel carregar a carteira." />;

  const positions = Array.isArray(portfolio.data?.positions) ? portfolio.data.positions : [];
  const chartData = positions
    .map((item) => ({ name: item.ticker, value: toNumber(item.allocation ?? item.weight) ?? 0 }))
    .filter((item) => item.value > 0);

  return (
    <div className="page-stack">
      <section className="page-heading actions">
        <div>
          <h2>Minha carteira</h2>
          <p>Posicoes, alocacao e historico de movimentacoes.</p>
        </div>
        <div className="button-row">
          <Link className="button button-primary" to="/investimentos/novo">Adicionar investimento</Link>
          <Link className="button button-secondary" to="/carteira/importar">Importar carteira</Link>
        </div>
      </section>
      <div className="metric-grid">
        <MetricCard label="Total investido" value={formatMoney(portfolio.data?.total_invested)} />
        <MetricCard label="Valor de mercado" value={formatMoney(portfolio.data?.total_market_value)} />
        <MetricCard label="Lucro ou prejuizo" value={formatMoney(portfolio.data?.total_profit)} />
        <MetricCard label="Rentabilidade" value={formatPercent(portfolio.data?.profitability)} />
      </div>
      {!positions.length ? (
        <EmptyState title="Sua carteira ainda esta vazia." />
      ) : (
        <>
          <Card title="Posicoes">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ativo</th><th>Nome</th><th>Quantidade</th><th>Preco medio</th><th>Valor investido</th><th>Preco atual</th><th>Valor de mercado</th><th>Lucro ou prejuizo</th><th>Alocacao</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((item) => (
                    <tr key={item.asset_id}>
                      <td>{item.ticker}</td><td>{item.asset_name}</td><td>{formatQuantityBR(item.quantity)}</td><td>{formatMoney(item.average_price)}</td><td>{formatMoney(item.invested_amount)}</td><td>{formatMoney(item.current_price)}</td><td>{formatMoney(item.market_value)}</td><td>{formatMoney(item.unrealized_profit)}</td><td>{formatPercent(item.allocation ?? item.weight)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="Grafico de alocacao">{chartData.length ? <AllocationChart data={chartData} /> : <p>Ainda nao ha informacao de alocacao para exibir.</p>}</Card>
        </>
      )}
      <Card title="Historico de movimentacoes">
        {operations.data?.length ? (
          <div className="table-wrap"><table><thead><tr><th>Data</th><th>Tipo</th><th>Quantidade</th><th>Preco de compra</th><th>Taxas</th></tr></thead><tbody>{operations.data.map((item) => <tr key={item.id}><td>{item.operation_date}</td><td>{item.operation_type === "BUY" ? "Compra" : "Venda"}</td><td>{formatQuantityBR(item.quantity)}</td><td>{formatMoney(item.unit_price)}</td><td>{formatMoney(item.fees)}</td></tr>)}</tbody></table></div>
        ) : <p>Nenhuma movimentacao registrada.</p>}
      </Card>
    </div>
  );
}
