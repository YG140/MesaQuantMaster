import {
  Activity,
  Bot,
  BriefcaseBusiness,
  Compass,
  Search,
} from "lucide-react";

export const primaryNavigation = [
  { kind: "link", label: "Início", to: "/", icon: Activity },
  { kind: "link", label: "Carteira", to: "/carteira", icon: BriefcaseBusiness },
  { kind: "action", label: "Mesa IA", icon: Bot },
  { kind: "link", label: "Mercado", to: "/ativos", icon: Search },
  { kind: "link", label: "Planejar", to: "/planejar", icon: Compass },
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
  "/configuracoes": { eyebrow: "Workstation", title: "Configurações", description: "Conta, aparência, fontes e capacidades da plataforma." },
};

export const aiSuggestions: Record<string, string[]> = {
  carteira: ["Explique a alocação atual da minha carteira.", "Quais riscos devo acompanhar na carteira?"],
  mercado: ["Quais dados estão disponíveis para analisar um ativo?", "Explique como comparar ativos sem inventar dados."],
  diagnostico: ["Explique o diagnóstico da minha carteira.", "Quais pontos de atenção aparecem nos dados?"],
  montar: ["Explique como minha política influencia a carteira sugerida.", "Quais dados faltam para uma sugestão mais confiável?"],
  futuro: ["Explique meus cenários financeiros em linguagem simples.", "Quais premissas afetam minhas projeções?"],
  configuracoes: ["Explique a qualidade e as fontes dos meus dados.", "Quais recursos da Mesa IA estão disponíveis?"],
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
