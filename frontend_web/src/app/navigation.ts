import {
  Activity,
  BrainCircuit,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  Compass,
  Plus,
  Search,
  Upload,
  WalletCards,
} from "lucide-react";

export const objectiveNavigation = [
  {
    label: "Acompanhar",
    to: "/",
    icon: Activity,
    description: "Patrimônio, carteira e dados de mercado",
  },
  {
    label: "Investir",
    to: "/investir",
    icon: WalletCards,
    description: "Aportes, importação e carteira inteligente",
  },
  {
    label: "Analisar",
    to: "/analisar",
    icon: ChartNoAxesCombined,
    description: "Diagnóstico, risco e oportunidades",
  },
  {
    label: "Planejar",
    to: "/planejar",
    icon: Compass,
    description: "Política, projeções e objetivos",
  },
] as const;

export const secondaryNavigation = [
  { label: "Minha carteira", to: "/carteira", icon: BriefcaseBusiness },
  { label: "Adicionar investimento", to: "/investimentos/novo", icon: Plus },
  { label: "Importar carteira", to: "/carteira/importar", icon: Upload },
  { label: "Inteligência de Carteira", to: "/inteligencia-carteira", icon: BrainCircuit },
  { label: "Ativos", to: "/ativos", icon: Search },
] as const;

export const routeContext: Record<string, { eyebrow: string; title: string; description: string }> = {
  "/": {
    eyebrow: "Acompanhar",
    title: "Visão orbital",
    description: "Seu patrimônio e os sinais essenciais da carteira em uma única órbita.",
  },
  "/carteira": {
    eyebrow: "Acompanhar",
    title: "Minha carteira",
    description: "Posições, movimentações e distribuição do patrimônio.",
  },
  "/investir": {
    eyebrow: "Investir",
    title: "Central de investimentos",
    description: "Aportes, importação e construção inteligente de carteira.",
  },
  "/investimentos/novo": {
    eyebrow: "Investir",
    title: "Novo investimento",
    description: "Registre um investimento com dados reais do MesaQuantMaster.",
  },
  "/carteira/importar": {
    eyebrow: "Investir",
    title: "Importar carteira",
    description: "Traga suas posições atuais para a inteligência quantitativa.",
  },
  "/analisar": {
    eyebrow: "Analisar",
    title: "Inteligência prismática",
    description: "Diagnóstico, risco, qualidade dos dados e oportunidades.",
  },
  "/inteligencia-carteira": {
    eyebrow: "Analisar",
    title: "Inteligência prismática",
    description: "Diagnóstico, risco, qualidade dos dados e oportunidades.",
  },
  "/planejar": {
    eyebrow: "Planejar",
    title: "Horizonte financeiro",
    description: "Política, projeções e liberdade financeira em perspectiva.",
  },
  "/ativos": {
    eyebrow: "Analisar",
    title: "Radar de ativos",
    description: "Pesquise e interprete ativos com dados do backend.",
  },
};

export const aiSuggestions: Record<string, string[]> = {
  acompanhar: [
    "Analise minha carteira e explique os principais riscos.",
    "Minha carteira está muito concentrada?",
  ],
  investir: [
    "Tenho R$ 5.000. Como esse valor poderia ser distribuído considerando minha estratégia?",
    "Consulte minha política de investimento.",
  ],
  analisar: [
    "Compare PETR4 e VALE3 para minha estratégia.",
    "Quais são os pontos fracos da minha carteira?",
  ],
  planejar: [
    "Explique minha política de investimento em linguagem simples.",
    "Como minha estratégia influencia os próximos aportes?",
  ],
};
