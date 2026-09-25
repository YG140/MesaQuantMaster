import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AllocationChart } from "../components/charts/AllocationChart";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { MetricCard } from "../components/ui/MetricCard";
import { ResponsiveTable } from "../components/ui/ResponsiveTable";
import { ApiError } from "../services/apiClient";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type { Operation, OperationUpdate, PortfolioPosition } from "../types/api";
import { formatDateTimeBR, formatMoney, formatPercent, formatQuantityBR, toNumber } from "../utils/formatters";

type Action = "edit" | "delete" | null;

export function PortfolioPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [position, setPosition] = useState<PortfolioPosition | null>(null);
  const [action, setAction] = useState<Action>(null);
  const [editing, setEditing] = useState<Operation | null>(null);
  const [message, setMessage] = useState("");
  const returnFocus = useRef<HTMLElement | null>(null);
  const portfolio = useQuery({ queryKey: ["portfolio", token], queryFn: () => endpoints.portfolio(token!), enabled: Boolean(token) });
  const operations = useQuery({ queryKey: ["operations", token], queryFn: () => endpoints.operations(token!), enabled: Boolean(token) });
  const brokerages = useQuery({ queryKey: ["brokerages", token], queryFn: () => endpoints.brokerages(token!), enabled: Boolean(token) });
  const positionOperations = useQuery({
    queryKey: ["position-operations", token, position?.asset_id],
    queryFn: () => endpoints.positionOperations(token!, position!.asset_id),
    enabled: Boolean(token && position && action),
  });

  const closeDialog = () => {
    setPosition(null);
    setAction(null);
    setEditing(null);
    window.setTimeout(() => returnFocus.current?.focus(), 0);
  };
  const refreshDerivedData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
      queryClient.invalidateQueries({ queryKey: ["operations"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["portfolio-intelligence"] }),
      queryClient.invalidateQueries({ queryKey: ["portfolio-market-recommendations"] }),
      queryClient.invalidateQueries({ queryKey: ["position-operations"] }),
    ]);
  };
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: OperationUpdate }) =>
      endpoints.updateOperation(token!, id, payload),
    onSuccess: async () => {
      await refreshDerivedData();
      setMessage("Operação atualizada e posição recalculada.");
      closeDialog();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () => endpoints.deletePosition(
      token!,
      position!.asset_id,
      position!.ticker,
      positionOperations.data!.length,
    ),
    onSuccess: async (result) => {
      await refreshDerivedData();
      setMessage(`${result.ticker}: ${result.operations_deleted} operação(ões) excluída(s).`);
      closeDialog();
    },
  });

  const openAction = (nextAction: Action, item: PortfolioPosition, trigger: HTMLElement) => {
    returnFocus.current = trigger;
    setMessage("");
    setEditing(null);
    setPosition(item);
    setAction(nextAction);
  };

  if (portfolio.isLoading || operations.isLoading) return <LoadingState />;
  if (portfolio.error || operations.error) return <ErrorState message="Não foi possível carregar a carteira." />;

  const positions = Array.isArray(portfolio.data?.positions) ? portfolio.data.positions : [];
  const chartData = positions.map((item) => ({ name: item.ticker, value: toNumber(item.allocation ?? item.weight) ?? 0 })).filter((item) => item.value > 0);

  return (
    <div className="page-stack portfolio-prism-page">
      <section className="page-heading actions">
        <div><h2>Minha carteira</h2><p>Posições, alocação e histórico de movimentações.</p></div>
        <div className="button-row">
          <Button type="button" variant="secondary" disabled={portfolio.isFetching} onClick={() => void queryClient.invalidateQueries({ queryKey: ["portfolio", token] })}>
            {portfolio.isFetching ? "Atualizando..." : "Atualizar cotações"}
          </Button>
          <Link className="button button-primary" to="/investimentos/novo">Adicionar investimento</Link>
          <Link className="button button-secondary" to="/carteira/importar">Importar carteira</Link>
        </div>
      </section>
      {message && <div className="success-box" role="status">{message}</div>}
      <MarketDataNotice status={portfolio.data?.market_data_status} quoteUpdatedAt={portfolio.data?.quote_updated_at} unpricedSymbols={portfolio.data?.unpriced_symbols ?? []} />
      <section className="portfolio-prism-hero">
        <AllocationChart data={chartData} />
        <div className="metric-grid portfolio-prism-metrics">
        <MetricCard label="Total investido" value={formatMoney(portfolio.data?.total_invested)} />
        <MetricCard label="Valor de mercado" value={formatMoney(portfolio.data?.total_market_value)} />
        <MetricCard label="Lucro ou prejuízo" value={formatMoney(portfolio.data?.total_profit)} />
        <MetricCard label="Rentabilidade" value={formatPercent(portfolio.data?.profitability)} />
        </div>
      </section>
      {!positions.length ? <EmptyState title="Sua carteira ainda está vazia." /> : (
        <>
          <Card title="Posições">
            <ResponsiveTable className="portfolio-table"><table><thead><tr><th>Ativo</th><th>Nome</th><th>Quantidade</th><th>Preço médio</th><th>Valor investido</th><th>Preço atual</th><th>Valor de mercado</th><th>Lucro ou prejuízo</th><th>Alocação</th><th>Ações</th></tr></thead>
              <tbody>{positions.map((item) => <tr key={item.asset_id}><td>{item.ticker}</td><td>{item.asset_name}</td><td>{formatQuantityBR(item.quantity)}</td><td>{formatMoney(item.average_price)}</td><td>{formatMoney(item.invested_amount)}</td><td>{formatMoney(item.current_price)}</td><td>{formatMoney(item.market_value)}</td><td>{formatMoney(item.unrealized_profit)}</td><td>{formatPercent(item.allocation ?? item.weight)}</td><td><PositionActions item={item} onAction={openAction} /></td></tr>)}</tbody>
            </table></ResponsiveTable>
            <div className="portfolio-cards">{positions.map((item) => <article className="position-card" key={item.asset_id}><div><strong>{item.ticker}</strong><span>{item.asset_name}</span></div><dl><div><dt>Quantidade</dt><dd>{formatQuantityBR(item.quantity)}</dd></div><div><dt>Valor investido</dt><dd>{formatMoney(item.invested_amount)}</dd></div><div><dt>Valor de mercado</dt><dd>{formatMoney(item.market_value)}</dd></div><div><dt>Preço médio</dt><dd>{formatMoney(item.average_price)}</dd></div><div><dt>Preço atual</dt><dd>{formatMoney(item.current_price)}</dd></div><div><dt>Lucro ou prejuízo</dt><dd>{formatMoney(item.unrealized_profit)}</dd></div><div><dt>Alocação</dt><dd>{formatPercent(item.allocation ?? item.weight)}</dd></div></dl><PositionActions item={item} onAction={openAction} /></article>)}</div>
          </Card>
          <p className="helper">Evolução: consulte as movimentações registradas abaixo. Não há série histórica de patrimônio neste contrato.</p>
        </>
      )}
      <Card title="Histórico de movimentações">
        {operations.data?.length ? <ResponsiveTable><table><thead><tr><th>Data</th><th>Tipo</th><th>Quantidade</th><th>Preço</th><th>Taxas</th></tr></thead><tbody>{operations.data.map((item) => <tr key={item.id}><td>{item.operation_date}</td><td>{item.operation_type === "BUY" ? "Compra" : "Venda"}</td><td>{formatQuantityBR(item.quantity)}</td><td>{formatMoney(item.unit_price)}</td><td>{formatMoney(item.fees)}</td></tr>)}</tbody></table></ResponsiveTable> : <p>Nenhuma movimentação registrada.</p>}
      </Card>
      {position && action && <PositionDialog
        action={action}
        position={position}
        operations={positionOperations.data ?? []}
        loading={positionOperations.isLoading}
        loadError={positionOperations.error}
        mutationError={updateMutation.error ?? deleteMutation.error}
        editing={editing}
        brokerages={brokerages.data ?? []}
        busy={updateMutation.isPending || deleteMutation.isPending}
        onEdit={setEditing}
        onSave={(payload) => editing && updateMutation.mutate({ id: editing.id, payload })}
        onDelete={() => deleteMutation.mutate()}
        onClose={closeDialog}
      />}
    </div>
  );
}

function PositionActions({ item, onAction }: { item: PortfolioPosition; onAction: (action: Action, item: PortfolioPosition, trigger: HTMLElement) => void }) {
  return <details className="position-actions"><summary aria-label={`Ações para ${item.ticker}`}>Ações</summary><div><button type="button" onClick={(event) => onAction("edit", item, event.currentTarget)}>Editar</button><button type="button" className="danger-link" onClick={(event) => onAction("delete", item, event.currentTarget)}>Excluir da carteira</button></div></details>;
}

function PositionDialog({ action, position, operations, loading, loadError, mutationError, editing, brokerages, busy, onEdit, onSave, onDelete, onClose }: {
  action: Exclude<Action, null>; position: PortfolioPosition; operations: Operation[]; loading: boolean; loadError: unknown; mutationError: unknown; editing: Operation | null;
  brokerages: Array<{ id: string; name: string }>; busy: boolean; onEdit: (operation: Operation | null) => void; onSave: (payload: OperationUpdate) => void; onDelete: () => void; onClose: () => void;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { titleRef.current?.focus(); }, []);
  return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
    <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="position-dialog-title">
      <h3 id="position-dialog-title" ref={titleRef} tabIndex={-1}>{action === "edit" ? `Editar ${position.ticker}` : `Excluir ${position.ticker} da carteira`}</h3>
      {loading && <p role="status">Carregando operações...</p>}
      {Boolean(loadError) && <p className="error-box" role="alert">{errorMessage(loadError)}</p>}
      {Boolean(mutationError) && <p className="error-box" role="alert">{errorMessage(mutationError)}</p>}
      {!loading && action === "edit" && !editing && <>
        <p>A posição é calculada a partir das operações. Escolha qual movimentação deseja corrigir:</p>
        <div className="operation-list">{operations.map((operation) => <button type="button" key={operation.id} onClick={() => onEdit(operation)}><strong>{operation.operation_type === "BUY" ? "Compra" : "Venda"} em {operation.operation_date}</strong><span>{formatQuantityBR(operation.quantity)} × {formatMoney(operation.unit_price)}{operation.source === "initial_import" ? " · importação inicial" : ""}</span></button>)}</div>
      </>}
      {action === "edit" && editing && <OperationForm operation={editing} brokerages={brokerages} busy={busy} onSubmit={onSave} onBack={() => onEdit(null)} />}
      {!loading && action === "delete" && <>
        <p>Esta ação remove todas as suas operações que formam a posição. O ativo global e os dados de mercado serão preservados.</p>
        <dl className="confirmation-summary"><div><dt>Ativo</dt><dd>{position.ticker} — {position.asset_name}</dd></div><div><dt>Quantidade</dt><dd>{formatQuantityBR(position.quantity)}</dd></div><div><dt>Valor investido</dt><dd>{formatMoney(position.invested_amount)}</dd></div><div><dt>Operações afetadas</dt><dd>{operations.length}</dd></div></dl>
        <p className="warning-box">O histórico dessas operações deixará a carteira, mas uma auditoria dos valores anteriores será mantida.</p>
        <div className="button-row"><Button type="button" variant="danger" disabled={busy || !operations.length} onClick={onDelete}>{busy ? "Excluindo..." : "Excluir da minha carteira"}</Button><Button type="button" variant="secondary" disabled={busy} onClick={onClose}>Cancelar</Button></div>
      </>}
      {action === "edit" && !editing && <div className="button-row"><Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button></div>}
    </section>
  </div>;
}

function OperationForm({ operation, brokerages, busy, onSubmit, onBack }: { operation: Operation; brokerages: Array<{ id: string; name: string }>; busy: boolean; onSubmit: (payload: OperationUpdate) => void; onBack: () => void }) {
  const [form, setForm] = useState<OperationUpdate>({ brokerage_id: operation.brokerage_id, operation_type: operation.operation_type, operation_date: operation.operation_date, quantity: operation.quantity, unit_price: operation.unit_price, fees: operation.fees, taxes: operation.taxes, notes: operation.notes });
  const [validation, setValidation] = useState("");
  const change = (field: keyof OperationUpdate, value: string | null) => setForm((current) => ({ ...current, [field]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!form.operation_date || Number.isNaN(Date.parse(`${form.operation_date}T00:00:00`))) return setValidation("Informe uma data válida.");
    if (!(Number(form.quantity) > 0)) return setValidation("A quantidade deve ser maior que zero.");
    if (!(Number(form.unit_price) > 0)) return setValidation("O preço unitário deve ser maior que zero.");
    if (Number(form.fees) < 0 || Number(form.taxes) < 0) return setValidation("Taxas e impostos não podem ser negativos.");
    setValidation("");
    onSubmit(form);
  };
  return <form className="form-grid two" onSubmit={submit}>
    {validation && <p className="error-box form-span" role="alert">{validation}</p>}
    <label>Tipo<select value={form.operation_type} onChange={(e) => change("operation_type", e.target.value)}><option value="BUY">Compra</option><option value="SELL">Venda</option></select></label>
    <label>Data<input type="date" required value={form.operation_date} onChange={(e) => change("operation_date", e.target.value)} /></label>
    <label>Quantidade<input inputMode="decimal" required value={form.quantity} onChange={(e) => change("quantity", e.target.value)} /></label>
    <label>Preço unitário<input inputMode="decimal" required value={form.unit_price} onChange={(e) => change("unit_price", e.target.value)} /></label>
    <label>Taxas<input inputMode="decimal" required value={form.fees} onChange={(e) => change("fees", e.target.value)} /></label>
    <label>Impostos<input inputMode="decimal" required value={form.taxes} onChange={(e) => change("taxes", e.target.value)} /></label>
    <label>Corretora<select value={form.brokerage_id ?? ""} onChange={(e) => change("brokerage_id", e.target.value || null)}><option value="">Sem corretora</option>{brokerages.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>Observações<input value={form.notes ?? ""} onChange={(e) => change("notes", e.target.value || null)} /></label>
    <div className="button-row form-span"><Button type="submit" disabled={busy}>{busy ? "Salvando..." : "Salvar alterações"}</Button><Button type="button" variant="secondary" disabled={busy} onClick={onBack}>Voltar</Button></div>
  </form>;
}

function errorMessage(error: unknown) { return error instanceof ApiError ? error.message : "Não foi possível concluir a ação. Tente novamente."; }

function MarketDataNotice({ status, quoteUpdatedAt, unpricedSymbols }: { status: string | null | undefined; quoteUpdatedAt: string | null | undefined; unpricedSymbols: string[] }) {
  if (status === "live") return <div className="success-box">Cotações atualizadas em {formatDateTimeBR(quoteUpdatedAt)}.</div>;
  if (status === "partial") return <div className="warning-box">Alguns ativos estão sem cotação atual. Os demais valores foram atualizados.{unpricedSymbols.length ? ` Sem cotação: ${unpricedSymbols.join(", ")}.` : ""}</div>;
  if (status === "unavailable") return <div className="warning-box">Não foi possível atualizar as cotações agora. Sua carteira continua disponível.</div>;
  return null;
}
