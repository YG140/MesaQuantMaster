import { BarChart3, Briefcase, Home, LineChart, Plus, Search, Upload } from "lucide-react";
import { NavLink } from "react-router-dom";

const primary = [
  { to: "/", label: "Inicio", icon: Home },
  { to: "/carteira", label: "Minha carteira", icon: Briefcase },
  { to: "/investimentos/novo", label: "Adicionar investimento", icon: Plus },
  { to: "/carteira/importar", label: "Importar carteira", icon: Upload },
];

const tools = [
  { to: "/analises", label: "Analises", icon: BarChart3 },
  { to: "/simulador-historico", label: "Simulador historico", icon: LineChart },
  { to: "/ativos", label: "Ativos", icon: Search },
];

export function Sidebar() {
  return (
    <aside className="sidebar" aria-label="Navegacao principal">
      <div className="brand">
        <strong>MQ</strong>
        <span>Mesa Quant</span>
      </div>
      <nav>
        <p>Principal</p>
        {primary.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"}>
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
        <p>Ferramentas</p>
        {tools.map((item) => (
          <NavLink key={item.to} to={item.to}>
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
