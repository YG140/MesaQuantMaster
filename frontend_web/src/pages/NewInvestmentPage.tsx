import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { SearchAutocomplete } from "../components/forms/SearchAutocomplete";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { CurrencyInput } from "../components/ui/CurrencyInput";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type { MarketAsset } from "../types/api";
import { display, formatCurrencyInputBR, formatMoney, normalizeDecimalForApi, parseBrazilianNumber } from "../utils/formatters";

const requiredDecimal = (message: string) => z.string().min(1, message).refine((value) => parseBrazilianNumber(value) !== null, "Informe um numero valido.");

const schema = z.object({
  brokerageId: z.string().min(1, "Selecione uma corretora."),
  newBrokerage: z.string().optional(),
  operationDate: z.string().min(1, "Informe a data da compra."),
  quantity: requiredDecimal("Informe a quantidade."),
  unitPrice: requiredDecimal("Informe o preco de compra."),
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
  const brokerages = useQuery({ queryKey: ["brokerages"], queryFn: () => endpoints.brokerages(token!) });
  const form = useForm<InvestmentForm>({
    resolver: zodResolver(schema),
    defaultValues: {
      operationDate: new Date().toISOString().slice(0, 10),
      fees: "0",
      taxes: "0",
    },
  });
  const brokerageId = useWatch({
    control: form.control,
    name: "brokerageId",
  });

  const mutation = useMutation({
    mutationFn: async (values: InvestmentForm) => {
      if (!selectedAsset) throw new Error("Selecione um ativo antes de salvar.");
      let brokerageId = values.brokerageId;
      if (values.brokerageId === "new") {
        const brokerage = await endpoints.createBrokerage(token!, values.newBrokerage ?? "");
        brokerageId = brokerage.id;
      }
      return endpoints.addInvestment(token!, {
        brokerage_id: brokerageId,
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
      await queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      form.reset();
      setSelectedAsset(null);
      setQuery("");
    },
  });

  if (brokerages.isLoading) return <LoadingState />;
  if (brokerages.error) return <ErrorState message="Nao foi possivel carregar corretoras." />;

  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Adicionar investimento</h2><p>Busque o ativo e registre o preco realmente pago.</p></section>
      <Card title="Dados do ativo">
        <div className="warning-box">Os dados de mercado apresentados nesta versao sao demonstrativos e podem nao representar a cotacao atual.</div>
        <SearchAutocomplete token={token!} query={query} onQueryChange={setQuery} onSelect={setSelectedAsset} />
        {selectedAsset ? (
          <div className="asset-card">
            <div><span>Codigo</span><strong>{selectedAsset.ticker}</strong></div>
            <div><span>Nome</span><strong>{display(selectedAsset.name)}</strong></div>
            <div><span>Tipo</span><strong>{display(selectedAsset.asset_type)}</strong></div>
            <div><span>Setor</span><strong>{display(selectedAsset.sector)}</strong></div>
            <div><span>Pais</span><strong>{display(selectedAsset.country)}</strong></div>
            <div><span>Bolsa</span><strong>{display(selectedAsset.exchange)}</strong></div>
            <div><span>Moeda</span><strong>{display(selectedAsset.currency)}</strong></div>
            <div><span>Preco atual</span><strong>{formatMoney(selectedAsset.current_price, selectedAsset.currency ?? "R$")}</strong></div>
            <div><span>Horario da cotacao</span><strong>{display(selectedAsset.last_updated)}</strong></div>
            <div><span>Fonte</span><strong>{selectedAsset.provider}</strong></div>
          </div>
        ) : null}
      </Card>
      <Card title="Dados da compra">
        {mutation.error ? <ErrorState message={mutation.error instanceof Error ? mutation.error.message : "Nao foi possivel salvar."} /> : null}
        {mutation.isSuccess ? <div className="success-box">Investimento salvo com sucesso.</div> : null}
        <form className="form-grid two" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <Select label="Corretora" {...form.register("brokerageId")} error={form.formState.errors.brokerageId?.message}>
            <option value="">Selecione</option>
            {brokerages.data?.map((brokerage) => <option key={brokerage.id} value={brokerage.id}>{brokerage.name}</option>)}
            <option value="new">Outra corretora</option>
          </Select>
          {brokerageId === "new" ? <Input label="Nome da corretora" {...form.register("newBrokerage")} /> : null}
          <Input label="Data da compra" type="date" {...form.register("operationDate")} error={form.formState.errors.operationDate?.message} />
          <Input label="Quantidade" inputMode="decimal" {...form.register("quantity")} error={form.formState.errors.quantity?.message} />
          <CurrencyInput label="Preco de compra" {...form.register("unitPrice")} error={form.formState.errors.unitPrice?.message} />
          <Button type="button" variant="secondary" disabled={!selectedAsset?.current_price} onClick={() => form.setValue("unitPrice", formatCurrencyInputBR(selectedAsset?.current_price))}>Usar preco atual como preco de compra</Button>
          <CurrencyInput label="Taxas" {...form.register("fees")} />
          <CurrencyInput label="Impostos" {...form.register("taxes")} />
          <Input label="Observacao" {...form.register("notes")} />
          <Button type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Salvando..." : "Salvar investimento"}</Button>
        </form>
      </Card>
    </div>
  );
}
