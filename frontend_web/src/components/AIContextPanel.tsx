import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Bot, ChevronRight, Info, LockKeyhole, Send, Sparkles, X } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { aiSuggestions } from "../app/navigation";
import { useAuth } from "../features/auth/useAuth";
import { ApiError } from "../services/apiClient";
import { endpoints } from "../services/endpoints/data";
import type { AIAgentChatResponse } from "../types/api";

const MAX_MESSAGE_LENGTH = 4000;
const createMessageId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;
const toolLabels: Record<string, string> = {
  analyze_asset: "Análise de ativo",
  compare_assets: "Comparação de ativos",
  analyze_portfolio: "Análise da carteira",
  get_portfolio_policy: "Política de investimento",
  build_portfolio_suggestion: "Sugestão de carteira",
};

type ChatMessage =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; content: string; meta: AIAgentChatResponse };

export function AIContextPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { token } = useAuth();
  const location = useLocation();
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const context = location.pathname.startsWith("/invest") || location.pathname.includes("importar")
    ? "investir"
    : location.pathname.startsWith("/planejar")
      ? "planejar"
      : location.pathname.startsWith("/analisar") || location.pathname.includes("inteligencia") || location.pathname.startsWith("/ativos")
        ? "analisar"
        : "acompanhar";

  const chat = useMutation({
    mutationFn: (content: string) => endpoints.aiAgentChat(token!, { message: content }),
    onSuccess: (response) => {
      if (!response.answer?.trim()) return;
      setHistory((items) => [...items, { id: createMessageId(), role: "assistant", content: response.answer, meta: response }]);
    },
  });

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>("button, textarea, [href], [tabindex]:not([tabindex='-1'])")).filter((element) => !element.hasAttribute("disabled"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 80);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose, open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [history, chat.isPending]);

  const send = (event?: FormEvent) => {
    event?.preventDefault();
    const content = message.trim();
    if (!content || content.length > MAX_MESSAGE_LENGTH || chat.isPending) return;
    setHistory((items) => [...items, { id: createMessageId(), role: "user", content }]);
    setMessage("");
    chat.mutate(content);
  };

  const errorMessage = chat.error ? describeAIError(chat.error) : null;

  return (
    <>
      {open ? <button className="ai-backdrop" aria-label="Fechar Mesa IA" onClick={onClose} /> : null}
      {open ? <aside ref={panelRef} className="ai-panel is-open" role="dialog" aria-modal="true" aria-labelledby="mesa-ai-title">
        <header className="ai-panel-header">
          <div className="ai-avatar"><Bot size={21} /></div>
          <div><span className="eyebrow">Agente quantitativa</span><h2 id="mesa-ai-title">Mesa IA</h2></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Fechar Mesa IA"><X size={20} /></button>
        </header>
        <div className="ai-trust-strip"><LockKeyhole size={15} /> Somente leitura · conteúdo educacional</div>
        <div className="ai-conversation" aria-live="polite">
          {!history.length ? (
            <div className="ai-welcome">
              <Sparkles size={28} /><h3>Interprete seus dados reais</h3>
              <p>A Mesa IA consulta ferramentas autorizadas para explicar sua carteira. Ela não executa operações.</p>
              <div className="ai-suggestions">
                {aiSuggestions[context].map((suggestion) => (
                  <button key={suggestion} type="button" onClick={() => setMessage(suggestion)}><span>{suggestion}</span><ChevronRight size={16} /></button>
                ))}
              </div>
            </div>
          ) : null}
          {history.map((item) => (
            <article key={item.id} className={`chat-message chat-${item.role}`}>
              <span>{item.role === "user" ? "Você" : "Mesa IA"}</span><p>{item.content}</p>
              {item.role === "assistant" ? <AIResponseMeta response={item.meta} /> : null}
            </article>
          ))}
          {chat.isPending ? <div className="ai-thinking" role="status"><i /><i /><i /> Consultando a inteligência quantitativa…</div> : null}
          {errorMessage ? <div className="ai-error" role="alert"><AlertTriangle size={17} /> {errorMessage}</div> : null}
          <div ref={bottomRef} />
        </div>
        <form className="ai-composer" onSubmit={send}>
          <label htmlFor="mesa-ai-message">Pergunte à Mesa IA</label>
          <textarea ref={inputRef} id="mesa-ai-message" value={message} maxLength={MAX_MESSAGE_LENGTH + 1} placeholder="Ex.: Minha carteira está concentrada?" onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} />
          <div className="ai-composer-footer">
            <span className={message.length > MAX_MESSAGE_LENGTH ? "error-text" : ""}>{message.length}/{MAX_MESSAGE_LENGTH}</span>
            <button type="submit" className="ai-send" disabled={!message.trim() || message.length > MAX_MESSAGE_LENGTH || chat.isPending}><Send size={18} /> Enviar</button>
          </div>
        </form>
        <p className="ai-privacy"><Info size={14} /> Dados financeiros necessários podem ser enviados ao provedor de IA. O histórico existe apenas nesta sessão.</p>
      </aside> : null}
    </>
  );
}

function AIResponseMeta({ response }: { response: AIAgentChatResponse }) {
  return <div className="ai-response-meta">
    {response.tools_used.length ? <div className="tool-chips">{response.tools_used.map((tool) => <span key={tool}>{toolLabels[tool] ?? tool}</span>)}</div> : null}
    {response.warnings.map((warning) => <p className="meta-warning" key={warning}><AlertTriangle size={14} /> {warning}</p>)}
    {response.data_quality_notes.map((note) => <p className="meta-note" key={note}><Info size={14} /> {note}</p>)}
  </div>;
}

function describeAIError(error: Error): string {
  if (!(error instanceof ApiError)) return "Falha de rede ao consultar a Mesa IA. Tente novamente.";
  if (error.code === "UNAUTHORIZED") return "Sua sessão expirou. Entre novamente para usar a Mesa IA.";
  if (error.code === "VALIDATION") return `Não foi possível enviar a pergunta: ${error.message}`;
  if (error.status === 503) return "A Mesa IA está desativada ou temporariamente indisponível.";
  if (error.code === "TIMEOUT") return "A Mesa IA demorou mais que o esperado. Tente uma pergunta mais objetiva.";
  if (error.code === "NETWORK") return "Não foi possível conectar à Mesa IA. Verifique o backend.";
  return "Não foi possível obter uma resposta da Mesa IA agora.";
}
