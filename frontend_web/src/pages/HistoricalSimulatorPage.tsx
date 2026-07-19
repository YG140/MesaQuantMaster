import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorState } from "../components/feedback/ErrorState";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { MetricCard } from "../components/ui/MetricCard";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import { formatMoney, formatPercent, normalizeDecimalForApi, parseBrazilianNumber } from "../utils/formatters";

const defaultSeries = "2026-01-02,10.00\n2026-01-03,10.50\n2026-01-04,10.20\n2026-01-05,11.00";

export function HistoricalSimulatorPage() {
  const { token } = useAuth();
  const [initialCapital, setInitialCapital] = useState("10000");
  const [windowSize, setWindowSize] = useState("3");
  const [feePercent, setFeePercent] = useState("0");
  const [fixedFee, setFixedFee] = useState("0");
  const [series, setSeries] = useState(defaultSeries);
  const mutation = useMutation({
    mutationFn: () => endpoints.runSimulation(token!, {
      initial_capital: normalizeDecimalForApi(initialCapital),
      historical_data: parseSeries(series),
      strategy: { name: "momentum", moving_average_window: parseBrazilianNumber(windowSize) ?? 0 },
      fee_percent: normalizeDecimalForApi(feePercent),
      fixed_fee: normalizeDecimalForApi(fixedFee),
    }),
  });

  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Simulador historico</h2><p>Simule como uma estrategia teria se comportado usando precos do passado. Isso nao preve resultados futuros.</p></section>
      <Card title="Parametros">
        {mutation.error ? <ErrorState message="Revise os dados da simulação." /> : null}
        <form className="form-grid two" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
          <CurrencyInput label="Capital inicial" value={initialCapital} onChange={(event) => setInitialCapital(event.target.value)} />
          <Input label="Janela momentum" value={windowSize} onChange={(event) => setWindowSize(event.target.value)} />
          <Input label="Custo percentual" value={feePercent} onChange={(event) => setFeePercent(event.target.value)} />
          <CurrencyInput label="Custo fixo" value={fixedFee} onChange={(event) => setFixedFee(event.target.value)} />
          <label className="field span-2"><span>Serie historica: data,fechamento</span><textarea value={series} onChange={(event) => setSeries(event.target.value)} /></label>
          <Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Simulando..." : "Executar simulacao"}</Button>
        </form>
      </Card>
      {mutation.data ? (
        <Card title="Resultado">
          <div className="metric-grid">
            <MetricCard label="Patrimônio final" value={formatMoney(mutation.data.final_equity)} />
            <MetricCard label="Retorno" value={formatPercent(mutation.data.total_return_percent)} />
            <MetricCard label="Benchmark" value={formatPercent(mutation.data.benchmark_return_percent)} />
            <MetricCard label="Excesso de retorno" value={formatPercent(mutation.data.excess_return_percent)} />
            <MetricCard label="Drawdown" value={formatPercent(mutation.data.max_drawdown_percent)} />
            <MetricCard label="Custos" value={formatMoney(mutation.data.total_fees)} />
            <MetricCard label="Trades" value={mutation.data.trades_count} />
          </div>
        </Card>
      ) : null}
    </div>
  );
}

function parseSeries(raw: string) {
  return raw.split("\n").filter(Boolean).map((line) => {
    const [timestamp, close] = line.split(",").map((part) => part.trim());
    return { timestamp, close: normalizeDecimalForApi(close) };
  });
}
