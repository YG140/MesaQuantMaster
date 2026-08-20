import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useId, useState, type KeyboardEvent } from "react";
import { endpoints } from "../../services/endpoints/data";
import { display, formatMoney } from "../../utils/formatters";
import type { MarketAsset } from "../../types/api";
import { LoadingState } from "../feedback/LoadingState";

const DEBOUNCE_MS = 300;

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
  const listboxId = useId();
  const [debouncedQuery, setDebouncedQuery] = useState(query);
  const [activeIndex, setActiveIndex] = useState(-1);
  // Fechado explicitamente pelo usuário (Escape ou seleção) -- reaberto
  // automaticamente assim que a query (debounced) muda de novo, sem
  // precisar de um segundo estado espelhado.
  const [dismissed, setDismissed] = useState(false);

  // Debounce real: o valor exibido no input (`query`, controlado pelo
  // pai) muda a cada tecla, mas a busca em si só dispara depois de
  // DEBOUNCE_MS sem digitação -- evita uma requisição por tecla.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setActiveIndex(-1);
    setDismissed(false);
  }, [debouncedQuery]);

  const search = useQuery({
    queryKey: ["market-search", debouncedQuery],
    queryFn: () => endpoints.marketSearch(token, debouncedQuery),
    // React Query já descarta por conta própria uma resposta obsoleta se
    // uma queryKey mais nova já tiver sido disparada (dedupe por chave) --
    // combinado com o debounce acima, nunca sobrescreve o resultado mais
    // recente com um mais antigo que chegue atrasado.
    enabled: debouncedQuery.trim().length >= 2,
  });

  const results = search.data ?? [];
  const hasQuery = debouncedQuery.trim().length >= 2;
  const isOpen = hasQuery && !dismissed && (search.isLoading || Boolean(search.error) || results.length > 0);
  const activeOptionId = activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined;

  function selectAsset(asset: MarketAsset) {
    setDismissed(true);
    setActiveIndex(-1);
    onSelect(asset);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      // Só intercepta (fecha as sugestões) quando há algo aberto para
      // fechar -- do contrário deixa o evento propagar, para que um
      // diálogo pai (ex.: busca global) possa tratar Escape para fechar a
      // si mesmo.
      if (isOpen) {
        event.preventDefault();
        event.stopPropagation();
        setDismissed(true);
        setActiveIndex(-1);
      }
      return;
    }
    if (!isOpen || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => (prev + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? results.length - 1 : prev - 1));
    } else if (event.key === "Enter") {
      if (activeIndex >= 0 && activeIndex < results.length) {
        event.preventDefault();
        selectAsset(results[activeIndex]);
      }
    }
  }

  return (
    <div className="autocomplete">
      <label className="field">
        <span>Ativo ou empresa</span>
        <div className="input-icon">
          <Search size={18} />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => hasQuery && setDismissed(false)}
            placeholder="PETR4 ou Petrobras"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={isOpen}
            aria-controls={listboxId}
            aria-activedescendant={activeOptionId}
          />
        </div>
      </label>
      {isOpen && search.isLoading ? <LoadingState label="Buscando ativos..." /> : null}
      {isOpen && search.error ? (
        <p className="helper error-text" role="alert">
          {search.error instanceof Error
            ? search.error.message
            : "Não foi possível consultar o mercado agora."}
        </p>
      ) : null}
      {isOpen && results.length ? (
        <ul id={listboxId} className="suggestions" role="listbox">
          {results.map((asset, index) => (
            <li key={asset.ticker} id={`${listboxId}-option-${index}`} role="option" aria-selected={index === activeIndex}>
              <button
                type="button"
                className={index === activeIndex ? "is-active" : undefined}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => selectAsset(asset)}
              >
                {asset.logo_url ? (
                  <img className="asset-logo" src={asset.logo_url} alt="" />
                ) : null}
                <strong>{asset.ticker}</strong>
                <span>
                  {display(asset.name)} - {display(asset.asset_type)} -{" "}
                  {display(asset.exchange)} - {display(asset.currency)} -{" "}
                  {formatMoney(asset.current_price, asset.currency ?? "BRL")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {isOpen && hasQuery && !search.isLoading && !search.error && results.length === 0 ? (
        <p className="helper">Nenhum ativo encontrado.</p>
      ) : null}
    </div>
  );
}
