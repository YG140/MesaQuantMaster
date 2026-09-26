import { Sparkles } from "lucide-react";
import { NavLink } from "react-router-dom";
import { primaryNavigation } from "../../app/navigation";

export function Sidebar({ onOpenAI }: { onOpenAI: () => void }) {
  const destinations = (mobile: boolean) => primaryNavigation.map((item) => item.kind === "action"
    ? <button key={item.label} aria-label={item.label} title="Mesa IA — pausada" className={mobile ? "mobile-ai-destination" : "primary-ai-link"} type="button" onClick={onOpenAI}><item.icon size={mobile ? 20 : 18} /><span>{item.label}</span></button>
    : <NavLink key={item.to} aria-label={item.label} to={item.to} end={item.to === "/"}><item.icon size={mobile ? 20 : 18} /><span>{item.label}</span></NavLink>);
  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <div className="brand">
        <strong><Sparkles size={20} /></strong>
        <span><b>MESA</b><small>QUANT MASTER</small></span>
      </div>
      <nav aria-label="Destinos principais" data-testid="desktop-primary-navigation">
        {destinations(false)}
      </nav>
      <div className="mobile-nav" aria-label="Destinos principais" data-testid="mobile-primary-navigation">
        {destinations(true)}
      </div>
    </aside>
  );
}
