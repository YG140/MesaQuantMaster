import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { MetricCard } from "../components/ui/MetricCard";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import {
  formatMoney, normalizeDecimalForApi, parseBrazilianNumber,
} from "../utils/formatters";

/** Preview independente: nunca altera saldos, investimentos nem o perfil. */
export function EmergencyReserveBuilder() {
  const { token } = useAuth();
  const policy = useQuery({
    queryKey: ["portfolio-policy", token],
    queryFn: () => endpoints.portfolioPolicy(token!),
    enabled: Boolean(token),
  });
  const [expenses, setExpenses] = useState("");
  const [available, setAvailable] = useState("");
  const [unstableIncome, setUnstableIncome] = useState(false);
  const [monthlyEdited, setMonthlyEdited] = useState(false);

  useEffect(() => {
    if (!monthlyEdited && policy.data?.monthly_contribution != null) {
      setAvailable(String(policy.data.monthly_contribution));
    }
  }, [monthlyEdited, policy.data?.monthly_contribution]);

  const build = useMutation({
    mutationFn: () => endpoints.emergencyReservePlan(token!, {
      essential_monthly_expenses: normalizeDecimalForApi(expenses),
      current_reserve: "0", // Planejamento sempre parte de uma reserva zerada.
      monthly_available: normalizeDecimalForApi(available),
      income_unstable: unstableIncome,
    }),
  });
  const valid = (parseBrazilianNumber(expenses) ?? 0) > 0
    && (parseBrazilianNumber(available) ?? -1) >= 0;

  return (
    <div className="page-stack" data-testid="emergency-reserve-builder">
      <Card title="Monte sua reserva de emergência">
        {policy.isLoading ? <LoadingState label="Consultando sua estratégia de proteção..." /> : null}
        {policy.isError ? (
          <p className="warning-box">Não foi possível carregar a política. A simulação usará uma referência inicial de 6 meses; sua carteira não será alterada.</p>
        ) : null}
        <form className="form-grid two" onSubmit={(event) => { event.preventDefault(); if (valid) build.mutate(); }}>
          <CurrencyInput label="Despesas essenciais por mês" value={expenses} onChange={(event) => setExpenses(event.target.value)} />
          <CurrencyInput label="Quanto posso guardar por mês" value={available} onChange={(event) => { setMonthlyEdited(true); setAvailable(event.target.value); }} />
          <label className="field">
            <span>Minha renda mensal</span>
            <select value={unstableIncome ? "variavel" : "estavel"} onChange={(event) => setUnstableIncome(event.target.value === "variavel")}>
              <option value="estavel">Estável</option>
              <option value="variavel">Variável ou sazonal</option>
            </select>
          </label>
          {build.isError ? <div className="span-2"><ErrorState message="Não foi possível calcular sua reserva. Seus investimentos não foram alterados." /></div> : null}
          <div className="span-2">
            <Button type="submit" disabled={!valid || build.isPending}>
              {build.isPending ? "Calculando minha reserva..." : "Montar minha reserva"}
            </Button>
          </div>
        </form>
      </Card>

      {build.data ? <Card title="Seu plano de proteção">
        <div className="metric-grid compact">
          <MetricCard label="Meta da reserva" value={formatMoney(build.data.target_amount)} />
          <MetricCard label="Proteção desejada" value={`${build.data.target_months} meses`} />
          <MetricCard label="Falta guardar" value={formatMoney(build.data.shortfall)} />
          <MetricCard label="Próximo aporte para reserva" value={formatMoney(build.data.suggested_next_reserve_contribution)} />
          <MetricCard label="Sobra do aporte informado" value={formatMoney(build.data.remaining_next_contribution)} />
          <MetricCard label="Prazo sem juros" value={build.data.estimated_months_to_goal == null
            ? "Depende de definir um aporte mensal" : build.data.estimated_months_to_goal === 0
              ? "Meta já atendida" : `${build.data.estimated_months_to_goal} mês(es)`} />
        </div>
        <h3>Onde alocar a reserva</h3>
        {build.data.asset_allocations?.length ? (
          <div className="metric-grid compact">
            {build.data.asset_allocations.map((item) => (
              <div className="metric-card" key={item.asset_type}>
                <span>{item.suggested_asset}</span>
                <strong>{formatMoney(item.next_contribution_amount)} no próximo aporte</strong>
                <small>Meta neste ativo: {formatMoney(item.target_amount)}</small>
                <small>{item.rationale}</small>
                <details>
                  <summary>Condições antes de investir</summary>
                  <p>{item.liquidity_warning}</p>
                </details>
              </div>
            ))}
          </div>
        ) : (
          <p className="warning-box">O servidor ainda não informou quais ativos recebem cada parcela. Reinicie o backend atualizado para obter o plano por ativo.</p>
        )}
        <p className="helper">Valores por tipo de investimento, não por produto validado. Nenhuma ordem de compra foi enviada.</p>
        {build.data.has_relevant_debt ? <p className="warning-box">Seu perfil informa dívida relevante. Avalie os juros da dívida antes de direcionar qualquer sobra para investimentos de risco.</p> : null}
        {build.data.basis !== "confirmed_profile_policy" ? <p className="warning-box">A meta de meses é provisória. Confirme o Perfil do Investidor para personalizá-la.</p> : null}
        <details>
          <summary>Cuidados e limitações</summary>
          <ul>{build.data.warnings.map((notice) => <li key={notice}>{notice}</li>)}</ul>
        </details>
      </Card> : null}
    </div>
  );
}
