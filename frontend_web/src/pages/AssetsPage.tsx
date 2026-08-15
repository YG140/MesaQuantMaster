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
import { display, formatDateTimeBR, formatMoney, formatPercent } from "../utils/formatters";
import { MarketOpportunities } from "./PortfolioIntelligencePage";

export function AssetsPage() {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [asset, setAsset] = useState<MarketAsset | null>(null);
  const [comparison, setComparison] = useState<string[]>([]);
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
  const intelligence = useQuery({ queryKey: ["asset-intelligence", asset?.ticker], queryFn: () => endpoints.assetIntelligence(token!, asset!.ticker), enabled: Boolean(asset) });
  const analysis = useMutation({ mutationFn: () => endpoints.analyzeAssets(token!, comparison) });
  const selectAsset = (next: MarketAsset) => { setAsset(next); setComparison((items) => items.includes(next.ticker) || items.length >= 5 ? items : [...items, next.ticker]); };

  if (assets.isLoading) return <LoadingState />;
  if (assets.error) return <ErrorState message="Não foi possível carregar ativos." />;

  return (
    <div className="page-stack market-prism-page">
      <section className="page-heading"><h2>Mercado e ativos</h2><p>Pesquisa, contexto e inteligência de mercado com dados da API.</p></section>
      <Card title="Pesquisar ativo" className="market-search-card">
        <SearchAutocomplete token={token!} query={query} onQueryChange={setQuery} onSelect={selectAsset} />
        {asset ? <div className="asset-card"><div><span>Código</span><strong>{asset.ticker}</strong></div><div><span>Nome</span><strong>{display(asset.name)}</strong></div><div><span>Preço atual demonstrativo</span><strong>{formatMoney(asset.current_price)}</strong></div></div> : null}
        <Button type="button" disabled={!asset || createAsset.isPending} onClick={() => createAsset.mutate()}>Cadastrar ativo</Button>
      </Card>
      <Card title="Ativos cadastrados" className="market-assets-card">
        {assets.data?.length ? <div className="table-wrap"><table><thead><tr><th>Ativo</th><th>Nome</th><th>Tipo</th><th>Bolsa</th><th>Moeda</th></tr></thead><tbody>{assets.data.map((item) => <tr key={item.id}><td>{item.ticker}</td><td>{item.name}</td><td>{item.asset_type}</td><td>{display(item.exchange)}</td><td>{item.currency}</td></tr>)}</tbody></table></div> : <p>Nenhum ativo cadastrado.</p>}
      </Card>
      {intelligence.isLoading ? <p role="status">Carregando inteligência do ativo…</p> : null}
      {intelligence.error ? <ErrorState message="A inteligência deste ativo está indisponível." /> : null}
      {intelligence.data ? <AssetSnapshot snapshot={intelligence.data} /> : null}
      <Card title="Comparação de ativos" className="market-comparison-card">
        <p className="helper">Selecione até cinco ativos pela busca. A comparação usa somente dimensões retornadas pela análise em lote.</p>
        <div className="comparison-selection">{comparison.map(symbol=><button type="button" key={symbol} onClick={()=>setComparison(items=>items.filter(item=>item!==symbol))}>{symbol} ×</button>)}</div>
        <Button type="button" disabled={comparison.length<2||analysis.isPending} onClick={()=>analysis.mutate()}>{analysis.isPending?"Comparando…":"Comparar ativos"}</Button>
        {analysis.error?<ErrorState message="Não foi possível comparar os ativos agora." />:null}
        {analysis.data?<AssetComparison data={analysis.data}/>:null}
      </Card>
      <MarketOpportunities />
    </div>
  );
}

function AssetSnapshot({snapshot}:{snapshot:import("../types/api").AssetIntelligenceSnapshot}) {
  return <Card title={`${snapshot.symbol} · ${display(snapshot.name)}`} className="asset-intelligence-hero"><div className="metric-grid compact"><Metric label="Preço" value={formatMoney(snapshot.current_price,snapshot.currency??"BRL")}/><Metric label="Valuation" value={formatPercent(snapshot.valuation_score)}/><Metric label="Renda" value={formatPercent(snapshot.income_score)}/><Metric label="Crescimento" value={formatPercent(snapshot.growth_score)}/><Metric label="Risco" value={formatPercent(snapshot.risk_score)}/><Metric label="Liquidez" value={formatPercent(snapshot.liquidity_score)}/><Metric label="Qualidade" value={formatPercent(snapshot.data_quality_score)}/></div><div className="two-column"><ReasonList title="Pontos positivos" values={snapshot.positive_reasons}/><ReasonList title="Riscos e atenção" values={snapshot.warning_reasons}/></div><p className="helper">Atualização de mercado: {formatDateTimeBR(snapshot.market_updated_at)} · Cobertura: {formatPercent(snapshot.coverage_percentage)} · Confiança: {snapshot.confidence}</p></Card>
}
function AssetComparison({data}:{data:import("../types/api").BatchAssetAnalysisResponse}) { return <div className="comparison-results"><div className="table-wrap"><table><thead><tr><th>Ativo</th><th>Preço</th><th>Valuation</th><th>Renda</th><th>Crescimento</th><th>Risco</th><th>Liquidez</th><th>Qualidade</th><th>Freshness</th></tr></thead><tbody>{data.snapshots.map(item=><tr key={item.symbol}><td><strong>{item.symbol}</strong></td><td>{formatMoney(item.current_price,item.currency??"BRL")}</td><td>{formatPercent(item.valuation_score)}</td><td>{formatPercent(item.income_score)}</td><td>{formatPercent(item.growth_score)}</td><td>{formatPercent(item.risk_score)}</td><td>{formatPercent(item.liquidity_score)}</td><td>{formatPercent(item.data_quality_score)}</td><td>{formatDateTimeBR(item.market_updated_at)}</td></tr>)}</tbody></table></div>{data.errors.length?<div className="warning-box">{data.errors.map(error=><p key={error.symbol}>{error.symbol}: {error.message}</p>)}</div>:null}<p className="helper">Calculado em {formatDateTimeBR(data.calculated_at)}. Valores ausentes permanecem indisponíveis.</p></div> }
function Metric({label,value}:{label:string;value:string}){return <div className="market-score"><span>{label}</span><strong>{value}</strong></div>}
function ReasonList({title,values}:{title:string;values:string[]}){return <div className="market-reasons"><h3>{title}</h3>{values.length?<ul>{values.map(value=><li key={value}>{value}</li>)}</ul>:<p>Não informado pelos dados disponíveis.</p>}</div>}
