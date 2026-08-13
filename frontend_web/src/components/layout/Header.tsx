import { Bot, Database, LogOut } from "lucide-react";
import { useLocation } from "react-router-dom";
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
        <button className="mesa-ai-trigger" type="button" onClick={onOpenAI}><Bot size={18} /> Mesa IA</button>
        <span className="user-name">{user?.name}</span>
        <Button variant="ghost" onClick={logout} icon={<LogOut size={18} />}>
          Sair
        </Button>
      </div>
    </header>
  );
}
