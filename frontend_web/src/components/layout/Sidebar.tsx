import { Bot, Sparkles } from "lucide-react";
import { NavLink } from "react-router-dom";
import { objectiveNavigation, secondaryNavigation } from "../../app/navigation";

export function Sidebar({ onOpenAI }: { onOpenAI: () => void }) {
  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <div className="brand">
        <strong><Sparkles size={20} /></strong>
        <span><b>Mesa Quant</b><small>Quantum Prism</small></span>
      </div>
      <nav>
        <p>Objetivos</p>
        {objectiveNavigation.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"}>
            <item.icon size={18} />
            <span>{item.label}<small>{item.description}</small></span>
          </NavLink>
        ))}
        <p>Acessos rápidos</p>
        {secondaryNavigation.map((item) => (
          <NavLink key={item.to} to={item.to}>
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <button className="sidebar-ai" type="button" onClick={onOpenAI}><Bot size={19} /><span><b>Mesa IA</b><small>Interprete seus dados</small></span></button>
      <div className="mobile-nav" aria-label="Navegação mobile">
        {objectiveNavigation.map((item) => <NavLink key={item.to} to={item.to} end={item.to === "/"}><item.icon size={20} /><span>{item.label}</span></NavLink>)}
        <button type="button" onClick={onOpenAI}><Bot size={20} /><span>Mesa IA</span></button>
      </div>
    </aside>
  );
}
