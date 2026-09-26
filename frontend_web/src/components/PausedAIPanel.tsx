import { Bot, X } from "lucide-react";
import { useEffect, useRef } from "react";

export function PausedAIPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    close.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") { event.preventDefault(); close.current?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); if (previous instanceof HTMLElement) previous.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return <div className="orbita-dialog-backdrop"><section className="orbita-paused-panel" role="dialog" aria-modal="true" aria-labelledby="paused-ai-title">
    <button ref={close} className="topbar-icon" onClick={onClose} aria-label="Fechar Mesa IA"><X /></button>
    <Bot size={40} aria-hidden="true" /><p className="eyebrow">Workstation / assistente</p><h2 id="paused-ai-title">Mesa IA — pausada</h2>
    <p>Nenhuma chamada externa é realizada. A análise dos seus dados continua disponível em Mercado e Planejar.</p>
    <p className="helper">Sem conversa, envio de dados ou execução de ordens.</p>
  </section></div>;
}
