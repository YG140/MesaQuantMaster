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

export function investorProfileStatusLabel(status?: string | null): string {
  return ONBOARDING_STATUS_LABELS[status ?? ""] ?? "Não informado";
}

export function investorProfileObjectiveLabel(objective?: string | null): string {
  if (!objective) return "Não informado";
  return OBJECTIVE_LABELS[objective] ?? objective;
}

export function investorProfileActionLabel(status?: string | null): string {
  return status === "complete" ? "Refazer avaliação" : "Continuar onboarding";
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
