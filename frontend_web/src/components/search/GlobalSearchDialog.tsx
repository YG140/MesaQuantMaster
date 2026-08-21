import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SearchAutocomplete } from "../forms/SearchAutocomplete";
import type { MarketAsset } from "../../types/api";

/**
 * Busca global do header -- overlay pequeno e isolado que REUTILIZA
 * SearchAutocomplete/endpoints.marketSearch (nunca uma segunda
 * implementação de busca). Estrutura (backdrop + role="dialog" + trap de
 * Tab manual + Escape) espelha deliberadamente AIContextPanel.tsx, o
 * único precedente de overlay Prisma disparado a partir do header/
 * sidebar neste projeto -- AIContextPanel.tsx permanece intocado; este é
 * um componente novo e pequeno, não uma extração/refatoração daquele.
 */
export function GlobalSearchDialog({
  open,
  onClose,
  token,
}: {
  open: boolean;
  onClose: () => void;
  token: string;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    // Captura o foco anterior ANTES de qualquer coisa focar o campo de
    // busca -- nunca usa `autoFocus` nativo no input (ver
    // SearchAutocomplete): autoFocus rouba o foco durante o commit,
    // antes deste efeito rodar, o que capturaria o próprio campo de
    // busca como "foco anterior" em vez do gatilho (lupa) real.
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusTimer = window.setTimeout(() => panelRef.current?.querySelector("input")?.focus(), 0);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>("button, input, [href], [tabindex]:not([tabindex='-1'])"),
      ).filter((element) => !element.hasAttribute("disabled"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose, open]);

  function selectAsset(asset: MarketAsset) {
    onClose();
    navigate(`/ativos?ativo=${encodeURIComponent(asset.ticker)}`);
  }

  if (!open) return null;

  return (
    <>
      <button className="search-backdrop" aria-label="Fechar busca" onClick={onClose} />
      <div ref={panelRef} className="search-dialog" role="dialog" aria-modal="true" aria-labelledby="global-search-title">
        <header className="search-dialog-header">
          <div className="search-dialog-icon">
            <Search size={18} />
          </div>
          <h2 id="global-search-title">Pesquisar</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Fechar busca">
            <X size={18} />
          </button>
        </header>
        <div className="search-dialog-body">
          <SearchAutocomplete token={token} query={query} onQueryChange={setQuery} onSelect={selectAsset} />
        </div>
      </div>
    </>
  );
}
