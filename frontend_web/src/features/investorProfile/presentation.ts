import { investorProfileEndpoints } from "../../services/endpoints/investorProfile";

// Rótulos de APRESENTAÇÃO compartilhados entre Configurações e Planejar --
// nunca duplica perguntas/etapas/scoring/classificação do wizard
// canônico (ver OnboardingPage.tsx, intencionalmente não tocado nesta
// tarefa). Os valores em `OBJECTIVE_LABELS` espelham os `value`s reais de
// `OBJECTIVE_OPTIONS` em OnboardingPage.tsx -- se um objetivo novo for
// adicionado lá, o rótulo aqui precisa ser atualizado manualmente (não há
// forma de reexportar sem tocar naquele arquivo, o que esta tarefa proíbe
// explicitamente).
const ONBOARDING_STATUS_LABELS: Record<string, string> = {
  needs_onboarding: "Onboarding não iniciado",
  in_progress: "Onboarding em andamento",
  pending_confirmation: "Aguardando sua confirmação",
  complete: "Concluído",
  needs_review: "Revisão recomendada",
};

const OBJECTIVE_LABELS: Record<string, string> = {
  crescimento_patrimonial: "Crescimento patrimonial",
  renda_passiva: "Gerar renda passiva",
  aposentadoria: "Aposentadoria",
  preservacao: "Preservação de capital",
  compra_futura: "Uma compra futura específica",
  formacao_patrimonio: "Formação de patrimônio do zero",
};

// Traduz códigos internos para rótulos legíveis; não modifica a política persistida
// nem os valores enviados ao backend ao montar a carteira.
const HORIZON_LABELS: Record<string, string> = {
  menos_1_ano: "Menos de 1 ano",
  "1_a_3_anos": "1 a 3 anos",
  "3_a_5_anos": "3 a 5 anos",
  "5_a_10_anos": "5 a 10 anos",
  mais_10_anos: "Mais de 10 anos",
  "curto prazo": "Curto prazo",
  "médio prazo": "Médio prazo",
  "medio prazo": "Médio prazo",
  "longo prazo": "Longo prazo",
};

const RISK_LABELS: Record<string, string> = {
  conservador: "Conservador",
  "moderado-conservador": "Moderado a conservador",
  moderado: "Moderado",
  "moderado-arrojado": "Moderado a arrojado",
  arrojado: "Arrojado",
};

const LIQUIDITY_LABELS: Record<string, string> = {
  baixa: "Baixa",
  moderada: "Moderada",
  alta: "Alta",
};

export function investorProfileHorizonLabel(horizon?: string | null): string {
  if (!horizon?.trim()) return "Não informado";
  const cleaned = horizon.trim();
  return HORIZON_LABELS[cleaned.toLocaleLowerCase("pt-BR")] ?? cleaned;
}

export function investorProfileRiskLabel(risk?: string | null): string {
  if (!risk?.trim()) return "Não informado";
  const cleaned = risk.trim();
  return RISK_LABELS[cleaned.toLocaleLowerCase("pt-BR")] ?? cleaned;
}

export function investorProfileLiquidityLabel(liquidity?: string | null): string {
  if (!liquidity?.trim()) return "Não informado";
  const cleaned = liquidity.trim();
  return LIQUIDITY_LABELS[cleaned.toLocaleLowerCase("pt-BR")] ?? cleaned;
}

export function investorProfileStatusLabel(status?: string | null): string {
  return ONBOARDING_STATUS_LABELS[status ?? ""] ?? "Não informado";
}

export function investorProfileObjectiveLabel(objective?: string | null): string {
  if (!objective) return "Não informado";
  return OBJECTIVE_LABELS[objective] ?? objective;
}

export function investorProfileActionLabel(status?: string | null): string {
  if (status === "complete") return "Refazer avaliação";
  // "needs_review" já executa o fluxo de revisão (ver REVIEWABLE_STATUSES
  // abaixo) -- o rótulo precisa indicar isso, não o mesmo texto genérico
  // usado para quem ainda nem começou o questionário.
  if (status === "needs_review") return "Revisar perfil";
  return "Continuar questionário";
}

const REVIEWABLE_STATUSES = new Set(["complete", "needs_review"]);

/**
 * Ação única de "continuar/revisar" reutilizada por Configurações e
 * Planejar -- nunca reimplementa o fluxo de revisão em si (que já existe
 * em InvestorProfileService.review no backend), apenas decide quando
 * chamá-lo antes de navegar para o wizard canônico.
 */
export async function continueOrReviewInvestorProfile(
  token: string,
  status: string | null | undefined,
  navigate: (path: string) => void,
): Promise<void> {
  if (status && REVIEWABLE_STATUSES.has(status)) {
    await investorProfileEndpoints.review(token);
  }
  navigate("/onboarding");
}
