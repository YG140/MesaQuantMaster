import { LogOut } from "lucide-react";
import { Button } from "../ui/Button";
import { useAuth } from "../../features/auth/useAuth";

export function Header() {
  const { user, logout } = useAuth();
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">Mesa Quant Master</span>
        <h1>Terminal de carteira</h1>
      </div>
      <div className="topbar-user">
        <span>{user?.name}</span>
        <Button variant="ghost" onClick={logout} icon={<LogOut size={18} />}>
          Sair
        </Button>
      </div>
    </header>
  );
}
