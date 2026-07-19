import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { SearchAutocomplete } from "../components/forms/SearchAutocomplete";
import { ErrorState } from "../components/feedback/ErrorState";
import { LoadingState } from "../components/feedback/LoadingState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { useAuth } from "../features/auth/useAuth";
import { endpoints } from "../services/endpoints/data";
import type { MarketAsset } from "../types/api";
import { display, formatMoney } from "../utils/formatters";

export function AssetsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [asset, setAsset] = useState<MarketAsset | null>(null);
  const assets = useQuery({ queryKey: ["assets"], queryFn: () => endpoints.assets(token!) });
  const createAsset = useMutation({
    mutationFn: () => {
      if (!asset) throw new Error("Selecione um ativo.");
      return endpoints.createAsset(token!, {
        ticker: asset.ticker,
        name: asset.name ?? asset.ticker,
        asset_type: asset.asset_type ?? "STOCK",
        sector: asset.sector,
        country: asset.country,
        currency: asset.currency ?? "BRL",
        exchange: asset.exchange,
      });
    },
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["assets"] }),
  });

  if (assets.isLoading) return <LoadingState />;
  if (assets.error) return <ErrorState message="Não foi possível carregar ativos." />;

  return (
    <div className="page-stack">
      <section className="page-heading"><h2>Ativos</h2><p>Pesquisa e cadastro auxiliar de ativos.</p></section>
      <Card title="Pesquisar ativo">
        <SearchAutocomplete token={token!} query={query} onQueryChange={setQuery} onSelect={setAsset} />
        {asset ? <div className="asset-card"><div><span>Código</span><strong>{asset.ticker}</strong></div><div><span>Nome</span><strong>{display(asset.name)}</strong></div><div><span>Preço atual demonstrativo</span><strong>{formatMoney(asset.current_price)}</strong></div></div> : null}
        <Button type="button" disabled={!asset || createAsset.isPending} onClick={() => createAsset.mutate()}>Cadastrar ativo</Button>
      </Card>
      <Card title="Ativos cadastrados">
        {assets.data?.length ? <div className="table-wrap"><table><thead><tr><th>Ativo</th><th>Nome</th><th>Tipo</th><th>Bolsa</th><th>Moeda</th></tr></thead><tbody>{assets.data.map((item) => <tr key={item.id}><td>{item.ticker}</td><td>{item.name}</td><td>{item.asset_type}</td><td>{display(item.exchange)}</td><td>{item.currency}</td></tr>)}</tbody></table></div> : <p>Nenhum ativo cadastrado.</p>}
      </Card>
    </div>
  );
}
