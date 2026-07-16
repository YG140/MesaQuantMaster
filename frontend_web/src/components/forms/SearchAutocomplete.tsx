import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { endpoints } from "../../services/endpoints/data";
import { display } from "../../utils/formatters";
import type { MarketAsset } from "../../types/api";
import { LoadingState } from "../feedback/LoadingState";

export function SearchAutocomplete({
  token,
  query,
  onQueryChange,
  onSelect,
}: {
  token: string;
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (asset: MarketAsset) => void;
}) {
  const search = useQuery({
    queryKey: ["market-search", query],
    queryFn: () => endpoints.marketSearch(token, query),
    enabled: query.trim().length >= 2,
  });

  return (
    <div className="autocomplete">
      <label className="field">
        <span>Ativo ou empresa</span>
        <div className="input-icon">
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="PETR4 ou Petrobras"
            aria-autocomplete="list"
          />
        </div>
      </label>
      {search.isLoading ? <LoadingState label="Buscando ativos..." /> : null}
      {search.data?.length ? (
        <ul className="suggestions" role="listbox">
          {search.data.map((asset) => (
            <li key={asset.ticker}>
              <button type="button" onClick={() => onSelect(asset)}>
                <strong>{asset.ticker}</strong>
                <span>
                  {display(asset.name)} - {display(asset.asset_type)} -{" "}
                  {display(asset.exchange)} - {display(asset.country)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {query.trim().length >= 2 && search.data?.length === 0 ? (
        <p className="helper">Nenhum ativo encontrado.</p>
      ) : null}
    </div>
  );
}
