import { Search, Settings, UserRound } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { routeContext } from "../../app/navigation";
import { useAuth } from "../../features/auth/useAuth";

function initialsFor(name?: string | null): string {
  if (!name) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
  return (first + last).toUpperCase();
}

// Reorganização do header (Correção interface): "API FastAPI" removido da
// UI (era só decorativo, sem dado dinâmico); "Mesa IA" removido -- a ação
// já existe no Sidebar/nav mobile via navigation.ts (kind:"action"),
// nunca desaparece, só deixa de ser redundante aqui; "Sair" movido para
// Configurações (ver SettingsPage.tsx, seção "Sair da conta"). No lugar
// do antigo botão temático da Mesa IA, uma ação Prisma do usuário
// (avatar + nome real, com fallback quando ainda não carregado) leva a
// /configuracoes#conta.
export function Header({ onOpenSearch }: { onOpenSearch: () => void }) {
  const { user } = useAuth();
  const location = useLocation();
  const context = routeContext[location.pathname] ?? routeContext["/"];
  const initials = initialsFor(user?.name);
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">{context.eyebrow}</span>
        <h1>{context.title}</h1>
        <p>{context.description}</p>
      </div>
      <div className="topbar-user">
        <button className="topbar-icon" type="button" aria-label="Pesquisar" onClick={onOpenSearch}>
          <Search size={18} />
        </button>
        <Link className="topbar-icon" to="/configuracoes" aria-label="Configurações">
          <Settings size={18} />
        </Link>
        <Link className="user-chip" to="/configuracoes#conta" aria-label="Abrir conta e perfil">
          <span className="user-chip-avatar" aria-hidden="true">
            {initials || <UserRound size={16} />}
          </span>
          <span className="user-chip-name">{user?.name ?? "Minha conta"}</span>
        </Link>
      </div>
    </header>
  );
}
