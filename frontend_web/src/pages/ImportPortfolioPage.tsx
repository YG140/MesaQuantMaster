import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { CurrencyInput } from "../components/forms/CurrencyInput";
import { DecimalInput } from "../components/forms/DecimalInput";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import { normalizeDecimalForApi, parseBrazilianNumber } from "../utils/formatters";

type ImportRow = {
  code: string;
  name: string;
  assetType: string;
  quantity: string;
  averagePrice: string;
  referenceDate: string;
  notes: string;
};

const emptyRow = (): ImportRow => ({
  code: "",
  name: "",
  assetType: "STOCK",
  quantity: "",
  averagePrice: "",
  referenceDate: new Date().toISOString().slice(0, 10),
  notes: "",
});

export function ImportPortfolioPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [brokerageId, setBrokerageId] = useState("");
  const [rows, setRows] = useState<ImportRow[]>([emptyRow()]);
  const brokerages = useQuery({ queryKey: ["brokerages"], queryFn: () => endpoints.brokerages(token!) });
  const validRows = rows.filter((row) => row.code && parseBrazilianNumber(row.quantity) !== null && parseBrazilianNumber(row.averagePrice) !== null);
  const invalidRows = rows.filter((row) => row.code || row.quantity || row.averagePrice).length - validRows.length;
  const mutation = useMutation({
    mutationFn: () => endpoints.importPortfolio(token!, {
      brokerage_id: brokerageId,
      positions: validRows.map((row) => ({
        ticker: row.code,
        name: row.name || row.code,
        asset_type: row.assetType,
        quantity: normalizeDecimalForApi(row.quantity),
        average_price: normalizeDecimalForApi(row.averagePrice),
        reference_date: row.referenceDate || null,
        notes: row.notes || null,
      })),
    }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["portfolio"] }),
  });

  if (brokerages.isLoading) return <LoadingState />;
  if (brokerages.error) return <ErrorState message="Não foi possível carregar corretoras." />;

  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Importar carteira</h2><p>Registre posições atuais consolidadas.</p></section>
      <Card title="Importação">
        {mutation.error ? <ErrorState message="Revise as linhas antes de confirmar a importação." /> : null}
        {mutation.isSuccess ? <div className="success-box">Carteira importada com sucesso.</div> : null}
        <Select label="Corretora" value={brokerageId} onChange={(event) => setBrokerageId(event.target.value)}>
          <option value="">Selecione</option>
          {brokerages.data?.map((brokerage) => <option key={brokerage.id} value={brokerage.id}>{brokerage.name}</option>)}
        </Select>
        <div className="import-list">
          {rows.map((row, index) => (
            <div className="import-row" key={`row-${index + 1}`}>
              <Input label="Ativo" value={row.code} onChange={(event) => updateRow(index, "code", event.target.value, rows, setRows)} />
              <Input label="Nome" value={row.name} onChange={(event) => updateRow(index, "name", event.target.value, rows, setRows)} />
              <DecimalInput label="Quantidade atual" value={row.quantity} onChange={(event) => updateRow(index, "quantity", event.target.value, rows, setRows)} />
              <CurrencyInput label="Preço médio" value={row.averagePrice} onChange={(event) => updateRow(index, "averagePrice", event.target.value, rows, setRows)} />
              <Input label="Data de referencia" type="date" value={row.referenceDate} onChange={(event) => updateRow(index, "referenceDate", event.target.value, rows, setRows)} />
            </div>
          ))}
        </div>
        <div className="button-row">
          <Button type="button" variant="secondary" onClick={() => setRows((current) => [...current, emptyRow()])}>Adicionar linha</Button>
          <Button type="button" disabled={!brokerageId || !validRows.length || invalidRows > 0 || mutation.isPending} onClick={() => mutation.mutate()}>Confirmar importação</Button>
        </div>
        <p className="helper">{validRows.length} linhas válidas. {invalidRows ? `${invalidRows} linhas com erro.` : "Nenhum erro por linha."}</p>
      </Card>
    </div>
  );
}

function updateRow(
  index: number,
  field: keyof ImportRow,
  value: string,
  rows: ImportRow[],
  setRows: (rows: ImportRow[]) => void,
) {
  setRows(rows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row));
}
