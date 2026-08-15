import { Bot, Database, LogOut, Search, Settings } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "../ui/Button";
import { useAuth } from "../../features/auth/useAuth";
import { routeContext } from "../../app/navigation";

export function Header({ onOpenAI }: { onOpenAI: () => void }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const context = routeContext[location.pathname] ?? routeContext["/"];
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">{context.eyebrow}</span>
        <h1>{context.title}</h1>
        <p>{context.description}</p>
      </div>
      <div className="topbar-user">
        <span className="data-pulse"><Database size={15} /> API FastAPI</span>
        <button className="topbar-icon" type="button" aria-label="Pesquisar"><Search size={18} /></button>
        <Link className="topbar-icon" to="/configuracoes" aria-label="Configurações"><Settings size={18} /></Link>
        <button className="mesa-ai-trigger" type="button" onClick={onOpenAI}><Bot size={18} /> Mesa IA</button>
        <Link className="user-name profile-link" to="/configuracoes#conta" aria-label="Abrir perfil">{user?.name}</Link>
        <Button variant="ghost" onClick={logout} icon={<LogOut size={18} />}>
          Sair
        </Button>
      </div>
    </header>
  );
}
