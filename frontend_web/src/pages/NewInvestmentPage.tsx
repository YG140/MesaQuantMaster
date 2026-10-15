import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { SearchAutocomplete } from "../components/forms/SearchAutocomplete";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { DecimalInput } from "../components/forms/DecimalInput";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { MetricCard } from "../components/ui/MetricCard";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type { Brokerage, MarketAsset } from "../types/api";
import { display, formatCurrencyInputBR, formatDateTimeBR, formatDecimalBR, formatMoney, formatPercent, normalizeDecimalForApi, parseBrazilianNumber } from "../utils/formatters";

const requiredDecimal = (message: string) => z.string().min(1, message).refine((value) => parseBrazilianNumber(value) !== null, "Informe um número válido.");

const schema = z.object({
  brokerageId: z.string().min(1, "Selecione uma corretora."),
  newBrokerage: z.string().optional(),
  operationDate: z.string().min(1, "Informe a data da compra."),
  quantity: requiredDecimal("Informe a quantidade."),
  unitPrice: requiredDecimal("Informe o preço de compra."),
  fees: z.string(),
  taxes: z.string(),
  notes: z.string().optional(),
});

type InvestmentForm = z.infer<typeof schema>;

export function NewInvestmentPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [selectedAsset, setSelectedAsset] = useState<MarketAsset | null>(null);
  const [lastSavedSymbol, setLastSavedSymbol] = useState<string | null>(null);
  const savedAssessment = useQuery({
    queryKey: ["assessment-after-buy", token, lastSavedSymbol],
    queryFn: () => endpoints.assetIntelligence(token!, lastSavedSymbol!),
    enabled: Boolean(token && lastSavedSymbol),
    retry: 1,
  });
  const [showBrokerageForm, setShowBrokerageForm] = useState(false);
  const [newBrokerageName, setNewBrokerageName] = useState("");
  const [brokerageError, setBrokerageError] = useState<string | null>(null);
  const brokerages = useQuery({ queryKey: ["brokerages"], queryFn: () => endpoints.brokerages(token!) });
  const form = useForm<InvestmentForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      operationDate: new Date().toISOString().slice(0, 10),
      unitPrice: "0,00",
      fees: "0,00",
      taxes: "0,00",
    },
  });

  const mutation = useMutation({
    mutationFn: async (values: InvestmentForm) => {
      if (!selectedAsset) throw new Error("Selecione um ativo antes de salvar.");
      return endpoints.addInvestment(token!, {
        brokerage_id: values.brokerageId,
        ticker: selectedAsset.ticker,
        name: selectedAsset.name ?? selectedAsset.ticker,
        asset_type: selectedAsset.asset_type ?? "STOCK",
        operation_date: values.operationDate,
        quantity: normalizeDecimalForApi(values.quantity),
        unit_price: normalizeDecimalForApi(values.unitPrice),
        fees: normalizeDecimalForApi(values.fees),
        taxes: normalizeDecimalForApi(values.taxes),
        notes: values.notes || null,
      });
    },
    onSuccess: async () => {
      setLastSavedSymbol(selectedAsset?.ticker ?? null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio-intelligence"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio-market-recommendations"] }),
        queryClient.invalidateQueries({ queryKey: ["portfolio-projection"] }),
      ]);
      form.reset();
      setSelectedAsset(null);
      setQuery("");
    },
  });
  const brokerageMutation = useMutation({
    mutationFn: (name: string) => endpoints.createBrokerage(token!, name),
    onMutate: () => setBrokerageError(null),
    onSuccess: async (brokerage) => {
      const addBrokerageToCache = (current: Brokerage[] | undefined) => {
        const items = current ?? [];
        return items.some((item) => item.id === brokerage.id)
          ? items
          : [...items, brokerage].sort((a, b) => a.name.localeCompare(b.name));
      };
      queryClient.setQueryData<Brokerage[]>(["brokerages"], addBrokerageToCache);
      await queryClient.invalidateQueries({ queryKey: ["brokerages"] });
      queryClient.setQueryData<Brokerage[]>(["brokerages"], addBrokerageToCache);
      form.setValue("brokerageId", brokerage.id, { shouldValidate: true });
      setNewBrokerageName("");
      setShowBrokerageForm(false);
    },
    onError: (error) => {
      setBrokerageError(error instanceof Error ? error.message : "Não foi possível cadastrar a corretora.");
    },
  });

  const saveBrokerage = () => {
    const name = newBrokerageName.trim();
    if (!name) {
      setBrokerageError("Informe o nome da corretora.");
      return;
    }
    brokerageMutation.mutate(name);
  };

  if (brokerages.isLoading) return <LoadingState />;
  if (brokerages.error) return <ErrorState message="Não foi possível carregar corretoras." />;

  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Adicionar investimento</h2><p>Busque o ativo e registre o preço realmente pago.</p></section>
      <Card title="Dados do ativo">
        <SearchAutocomplete token={token!} query={query} onQueryChange={setQuery} onSelect={setSelectedAsset} />
        {selectedAsset?.limited_mode ? (
          <div className="warning-box">Consulta de mercado em modo limitado. Configure a chave de mercado no backend para cobertura completa.</div>
        ) : null}
        {selectedAsset ? (
          <div className="asset-card">
            {selectedAsset.logo_url ? <img className="asset-logo large" src={selectedAsset.logo_url} alt="" /> : null}
            <div><span>Código</span><strong>{selectedAsset.ticker}</strong></div>
            <div><span>Nome</span><strong>{display(selectedAsset.name)}</strong></div>
            <div><span>Tipo</span><strong>{display(selectedAsset.asset_type)}</strong></div>
            <div><span>Subtipo</span><strong>{display(selectedAsset.asset_subtype)}</strong></div>
            <div><span>Setor</span><strong>{display(selectedAsset.sector)}</strong></div>
            <div><span>Subsetor</span><strong>{display(selectedAsset.subsector)}</strong></div>
            <div><span>País</span><strong>{display(selectedAsset.country)}</strong></div>
            <div><span>Bolsa</span><strong>{display(selectedAsset.exchange)}</strong></div>
            <div><span>Moeda</span><strong>{display(selectedAsset.currency)}</strong></div>
            <div><span>Última cotação disponível</span><strong>{formatMoney(selectedAsset.current_price, selectedAsset.currency ?? "BRL")}</strong></div>
            <div><span>Variação</span><strong>{formatPercent(selectedAsset.change_percent)}</strong></div>
            <div><span>Horário da cotação</span><strong>{formatDateTimeBR(selectedAsset.updated_at ?? selectedAsset.last_updated)}</strong></div>
            <div><span>Fonte</span><strong>{selectedAsset.provider}</strong></div>
          </div>
        ) : null}
      </Card>
      <Card title="Dados da compra">
        {mutation.error ? <ErrorState message={mutation.error instanceof Error ? mutation.error.message : "Não foi possível salvar."} /> : null}
        {mutation.isSuccess ? <div className="success-box">Investimento salvo. A avaliação pelos indicadores é exibida abaixo e não altera a operação registrada.</div> : null}
        <form className="form-grid two" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div className="form-grid span-2">
            {brokerages.data?.length ? (
              <Select label="Corretora" {...form.register("brokerageId")} error={form.formState.errors.brokerageId?.message}>
                <option value="">Selecione</option>
                {brokerages.data.map((brokerage) => <option key={brokerage.id} value={brokerage.id}>{brokerage.name}</option>)}
              </Select>
            ) : (
              <div className="warning-box">Você ainda não cadastrou uma corretora.</div>
            )}
            {!showBrokerageForm ? (
              <Button type="button" variant="secondary" onClick={() => setShowBrokerageForm(true)}>
                + Cadastrar corretora
              </Button>
            ) : (
              <div className="brokerage-inline-form">
                <Input
                  label="Nome da corretora"
                  value={newBrokerageName}
                  onChange={(event) => setNewBrokerageName(event.target.value)}
                  disabled={brokerageMutation.isPending}
                />
                {brokerageError ? <p className="helper error-text">{brokerageError}</p> : null}
                <div className="button-row">
                  <Button type="button" variant="secondary" disabled={brokerageMutation.isPending} onClick={() => { setShowBrokerageForm(false); setNewBrokerageName(""); setBrokerageError(null); }}>
                    Cancelar
                  </Button>
                  <Button type="button" disabled={brokerageMutation.isPending} onClick={saveBrokerage}>
                    {brokerageMutation.isPending ? "Salvando..." : "Salvar corretora"}
                  </Button>
                </div>
              </div>
            )}
          </div>
          <Input label="Data da compra" type="date" {...form.register("operationDate")} error={form.formState.errors.operationDate?.message} />
          <DecimalInput label="Quantidade" {...form.register("quantity")} error={form.formState.errors.quantity?.message} />
          <CurrencyInput label="Preço de compra" {...form.register("unitPrice")} error={form.formState.errors.unitPrice?.message} />
          <Button type="button" variant="secondary" disabled={!selectedAsset?.current_price} onClick={() => form.setValue("unitPrice", formatCurrencyInputBR(selectedAsset?.current_price))}>Usar esta cotação como preço de compra</Button>
          <CurrencyInput label="Taxas" {...form.register("fees")} />
          <CurrencyInput label="Impostos" {...form.register("taxes")} />
          <Input label="Observação" {...form.register("notes")} />
          <Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Salvando..." : "Salvar investimento"}</Button>
        </form>
      </Card>
      {lastSavedSymbol ? (
        <Card title={`Avaliação da compra registrada — ${lastSavedSymbol}`}>
          {savedAssessment.isLoading ? <LoadingState label="Analisando indicadores da ação registrada..." /> : null}
          {savedAssessment.error ? (
            <p className="helper">Não foi possível obter indicadores confiáveis deste ativo agora. O registro foi salvo normalmente; não há recomendação de compra ou venda nesta condição.</p>
          ) : null}
          {savedAssessment.data ? (
            <>
              <div className="metric-grid compact">
                <MetricCard label="Orientação de análise" value={registeredPurchaseLabel(savedAssessment.data.recommendation)} />
                <MetricCard label="Confiabilidade dos dados" value={registeredPurchaseConfidence(savedAssessment.data.confidence)} />
                <MetricCard label="Pontuação por indicadores" value={savedAssessment.data.overall_score === null ? "Não disponível" : `${formatDecimalBR(savedAssessment.data.overall_score, 1)}/100`} />
                <MetricCard label="Avaliação do preço" value={registeredPurchaseValuation(savedAssessment.data.valuation_status)} />
              </div>
              <p className="helper">Parecer baseado nos indicadores disponíveis, no perfil confirmado e nas posições registradas. A valorização passada ou o preço que você pagou, isoladamente, não tornam o investimento bom ou ruim.</p>
              {savedAssessment.data.positive_reasons.length ? <details><summary>Por que pode fazer sentido</summary><ul>{savedAssessment.data.positive_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></details> : null}
              {savedAssessment.data.warning_reasons.length ? <details><summary>Riscos e pontos de atenção</summary><ul>{savedAssessment.data.warning_reasons.map((risk) => <li key={risk}>{risk}</li>)}</ul></details> : null}
            </>
          ) : null}
          <Link className="button button-secondary" to="/planejar?secao=montar-carteira">Montar carteira considerando esta posição</Link>
        </Card>
      ) : null}
    </div>
  );
}

function registeredPurchaseLabel(value: string) {
  return ({
    analyze_to_buy: "Analisar compra", buy_gradually: "Avaliar aporte gradual",
    increase_position: "Avaliar ampliação", hold: "Acompanhar",
    wait: "Aguardar", reduce_exposure: "Rever exposição",
    consider_selling: "Reavaliar posição", review_data: "Revisar dados",
    insufficient_data: "Sem dados suficientes",
  } as Record<string, string>)[value] ?? "Revisar dados";
}

function registeredPurchaseConfidence(value: string) {
  return ({ high: "Alta", medium: "Média", low: "Baixa", insufficient: "Insuficiente" } as Record<string, string>)[value] ?? "Insuficiente";
}

function registeredPurchaseValuation(value: string) {
  return ({
    very_attractive: "Potencialmente atrativo", attractive: "Potencialmente atrativo",
    near_estimated_value: "Próximo do valor estimado", elevated: "Preço elevado",
    very_elevated: "Preço muito elevado", insufficient_data: "Não avaliável",
  } as Record<string, string>)[value] ?? "Não avaliável";
}
