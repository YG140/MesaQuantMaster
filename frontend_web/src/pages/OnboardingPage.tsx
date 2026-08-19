import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { CurrencyInput } from "../components/ui/CurrencyInput";
import { Input } from "../components/ui/Input";
import { LoadingState } from "../components/feedback/LoadingState";
import { ErrorState } from "../components/feedback/ErrorState";
import { useAuth } from "../features/auth/useAuth";
import { investorProfileEndpoints } from "../services/endpoints/investorProfile";
import type {
  ContributionAnswer,
  FinancialSituationAnswer,
  HorizonAnswer,
  IncomeNeedAnswer,
  InvestorProfileEvaluation,
  KnowledgeAnswer,
  LiquidityAnswer,
  ObjectivesAnswer,
  RestrictionsAnswer,
  RiskToleranceAnswer,
} from "../types/api";
import { formatPercent, normalizeDecimalForApi } from "../utils/formatters";

const OBJECTIVE_OPTIONS = [
  { value: "crescimento_patrimonial", label: "Crescimento patrimonial" },
  { value: "renda_passiva", label: "Gerar renda passiva" },
  { value: "aposentadoria", label: "Aposentadoria" },
  { value: "preservacao", label: "Preservação de capital" },
  { value: "compra_futura", label: "Uma compra futura específica" },
  { value: "formacao_patrimonio", label: "Formação de patrimônio do zero" },
];

const HORIZON_OPTIONS = [
  { value: "menos_1_ano", label: "Menos de 1 ano" },
  { value: "1_a_3_anos", label: "1 a 3 anos" },
  { value: "3_a_5_anos", label: "3 a 5 anos" },
  { value: "5_a_10_anos", label: "5 a 10 anos" },
  { value: "mais_10_anos", label: "Mais de 10 anos" },
];

const INCOME_RANGE_OPTIONS = [
  { value: "ate_3000", label: "Até R$ 3.000" },
  { value: "3000_a_8000", label: "R$ 3.000 a R$ 8.000" },
  { value: "8000_a_20000", label: "R$ 8.000 a R$ 20.000" },
  { value: "acima_20000", label: "Acima de R$ 20.000" },
];

const NET_WORTH_OPTIONS = [
  { value: "ate_10000", label: "Até R$ 10.000" },
  { value: "10000_a_50000", label: "R$ 10.000 a R$ 50.000" },
  { value: "50000_a_200000", label: "R$ 50.000 a R$ 200.000" },
  { value: "acima_200000", label: "Acima de R$ 200.000" },
];

const LIQUIDITY_OPTIONS = [
  { value: "baixa", label: "Baixa — posso deixar o dinheiro investido por anos" },
  { value: "moderada", label: "Moderada — posso precisar em alguns meses" },
  { value: "alta", label: "Alta — posso precisar resgatar a qualquer momento" },
];

const INCOME_NEED_OPTIONS = [
  { value: "nenhuma", label: "Não preciso de renda dos investimentos agora" },
  { value: "complemento", label: "Complemento ocasional de renda" },
  { value: "renda_passiva", label: "Quero construir uma renda passiva relevante" },
  { value: "dependencia", label: "Dependo dos investimentos para minha renda" },
];

const KNOWLEDGE_QUESTIONS: {
  id: string;
  question: string;
  options: { value: string; label: string }[];
}[] = [
  {
    id: "volatilidade",
    question: "O que significa volatilidade de um investimento?",
    options: [
      { value: "a", label: "A garantia de retorno positivo" },
      { value: "b", label: "A intensidade das oscilações de preço no período" },
      { value: "c", label: "O valor total investido" },
      { value: "d", label: "A taxa de administração cobrada" },
    ],
  },
  {
    id: "diversificacao",
    question: "Qual o principal benefício de diversificar investimentos entre diferentes classes de ativos?",
    options: [
      { value: "a", label: "Reduzir o impacto de um único ativo ou classe no resultado total" },
      { value: "b", label: "Garantir que todos os ativos sempre subam juntos" },
      { value: "c", label: "Eliminar completamente o risco de perda" },
      { value: "d", label: "Aumentar a taxa de administração paga" },
    ],
  },
  {
    id: "risco_perda",
    question: "Investimentos com potencial de maior retorno no longo prazo geralmente...",
    options: [
      { value: "a", label: "Nunca apresentam perdas no curto prazo" },
      { value: "b", label: "São sempre garantidos pelo FGC" },
      { value: "c", label: "Podem apresentar maior oscilação e risco de perda no curto prazo" },
      { value: "d", label: "São isentos de imposto de renda" },
    ],
  },
  {
    id: "renda_fixa_x_variavel",
    question: "Qual a principal diferença entre renda fixa e renda variável?",
    options: [
      { value: "a", label: "Na renda fixa a regra de remuneração é conhecida na aplicação; na variável, não" },
      { value: "b", label: "Renda variável nunca tem risco" },
      { value: "c", label: "Renda fixa sempre rende mais que renda variável" },
      { value: "d", label: "Não há diferença relevante entre elas" },
    ],
  },
  {
    id: "marcacao_a_mercado",
    question: "O que é 'marcação a mercado' em um investimento de renda fixa?",
    options: [
      { value: "a", label: "A taxa fixa contratada na aplicação, que nunca muda" },
      { value: "b", label: "A atualização diária do valor do ativo pelo preço de mercado, podendo oscilar antes do vencimento" },
      { value: "c", label: "Um imposto cobrado apenas no resgate" },
      { value: "d", label: "O valor mínimo de aplicação" },
    ],
  },
];

const RISK_SCENARIO_OPTIONS = [
  { value: "venderia_tudo", label: "Venderia tudo para evitar mais perdas" },
  { value: "venderia_parte", label: "Venderia parte da carteira para reduzir o risco" },
  { value: "manteria", label: "Manteria a carteira como está, sem alterações" },
  { value: "compraria_mais", label: "Aproveitaria para investir mais, já que os preços estão mais baixos" },
];

const RISK_SCENARIOS: { id: string; scenario: string }[] = [
  {
    id: "queda_20_curto_prazo",
    scenario:
      "Sua carteira de R$ 100.000 caiu para R$ 80.000 em poucas semanas, por causa de uma turbulência de mercado. O que você faria?",
  },
  {
    id: "queda_30_prolongada",
    scenario:
      "Sua carteira caiu 30% e a queda persiste há alguns meses, sem sinais claros de recuperação no curto prazo. Qual seria sua reação mais provável?",
  },
  {
    id: "volatilidade_mensal",
    scenario:
      "Você percebe que o valor da sua carteira oscila de forma perceptível todo mês. Como você reage a isso no dia a dia?",
  },
];

const RESTRICTABLE_CLASSES = [
  "Ações",
  "FIIs",
  "ETFs",
  "BDRs",
  "Criptomoedas",
  "Crédito privado",
];

type WizardAnswers = {
  objectives: ObjectivesAnswer;
  horizon: HorizonAnswer;
  contribution: ContributionAnswer;
  financial_situation: FinancialSituationAnswer;
  liquidity: LiquidityAnswer;
  income_need: IncomeNeedAnswer;
  knowledge: KnowledgeAnswer;
  risk_tolerance: RiskToleranceAnswer;
  restrictions: RestrictionsAnswer;
};

function emptyAnswers(): WizardAnswers {
  return {
    objectives: { primary_objective: null, secondary_objectives: [] },
    horizon: { horizon: null },
    contribution: { initial_contribution: null, monthly_contribution: null, contribution_stability: null },
    financial_situation: {
      income_range: null,
      investable_net_worth_range: null,
      emergency_reserve_months: null,
      has_relevant_debt: null,
      dependents: null,
    },
    liquidity: { liquidity_need: null },
    income_need: { income_need: null },
    knowledge: { answers: {} },
    risk_tolerance: { scenarios: {} },
    restrictions: { restricted_classes: [], allowed_classes: [] },
  };
}

const TOTAL_STEPS = 9;

export function OnboardingPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<WizardAnswers>(emptyAnswers());
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<InvestorProfileEvaluation | null>(null);
  const [showReview, setShowReview] = useState(false);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    investorProfileEndpoints
      .get(token)
      .then((profile) => {
        setAnswers((current) => ({
          ...current,
          objectives: {
            primary_objective: profile.primary_objective,
            secondary_objectives: profile.secondary_objectives ?? [],
          },
          horizon: { horizon: profile.horizon },
          contribution: {
            initial_contribution: profile.initial_contribution,
            monthly_contribution: profile.monthly_contribution,
            contribution_stability: profile.contribution_stability as WizardAnswers["contribution"]["contribution_stability"],
          },
          financial_situation: {
            income_range: profile.income_range,
            investable_net_worth_range: profile.investable_net_worth_range,
            emergency_reserve_months: profile.emergency_reserve_months,
            has_relevant_debt: profile.has_relevant_debt,
            dependents: profile.dependents,
          },
          liquidity: { liquidity_need: profile.liquidity_need },
          income_need: { income_need: profile.income_need },
          restrictions: {
            restricted_classes: profile.restricted_classes ?? [],
            allowed_classes: profile.allowed_classes ?? [],
          },
        }));
        if (profile.status === "pending_confirmation" && profile.dimensions && profile.policy_preview) {
          setEvaluation({
            dimensions: profile.dimensions,
            explanations: profile.explanations ?? [],
            policy_preview: profile.policy_preview,
            missing_sections: [],
          });
          setShowReview(true);
        }
      })
      .catch(() => setError("Não foi possível carregar seu progresso salvo."))
      .finally(() => setIsLoading(false));
  }, [token]);

  const progressLabel = useMemo(() => `Passo ${step + 1} de ${TOTAL_STEPS}`, [step]);

  async function persist(partial: Partial<WizardAnswers>) {
    if (!token) return;
    setIsSaving(true);
    setError(null);
    try {
      await investorProfileEndpoints.saveAnswers(token, partial);
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : "Não foi possível salvar sua resposta agora. Tente novamente.";
      setError(message);
      throw new Error("save_failed");
    } finally {
      setIsSaving(false);
    }
  }

  async function goNext(partial: Partial<WizardAnswers>) {
    const merged = { ...answers, ...partial } as WizardAnswers;
    setAnswers(merged);
    try {
      await persist(partial);
    } catch {
      return;
    }
    if (step + 1 >= TOTAL_STEPS) {
      await runEvaluation();
    } else {
      setStep((current) => current + 1);
    }
  }

  function goBack() {
    setStep((current) => Math.max(0, current - 1));
  }

  async function runEvaluation() {
    if (!token) return;
    setIsSaving(true);
    setError(null);
    try {
      const result = await investorProfileEndpoints.evaluate(token);
      setEvaluation(result);
      setShowReview(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Não foi possível calcular seu perfil agora.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function confirm() {
    if (!token) return;
    setIsSaving(true);
    setError(null);
    try {
      await investorProfileEndpoints.confirm(token);
      navigate("/", { replace: true });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Não foi possível confirmar seu perfil agora.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  function editAgain() {
    setShowReview(false);
    setStep(TOTAL_STEPS - 1);
  }

  if (isLoading) {
    return <LoadingState label="Carregando seu onboarding..." />;
  }

  return (
    <main className="page-stack onboarding-page">
      <Card className="onboarding-card">
        {error ? <ErrorState message={error} /> : null}
        {showReview && evaluation ? (
          <ReviewStep evaluation={evaluation} isSaving={isSaving} onEdit={editAgain} onConfirm={confirm} />
        ) : (
          <>
            <p className="onboarding-progress" role="status">
              {progressLabel}
            </p>
            {renderStep({
              step,
              answers,
              isSaving,
              onNext: goNext,
              onBack: step > 0 ? goBack : undefined,
            })}
          </>
        )}
      </Card>
    </main>
  );
}

function renderStep({
  step,
  answers,
  isSaving,
  onNext,
  onBack,
}: {
  step: number;
  answers: WizardAnswers;
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  switch (step) {
    case 0:
      return <ObjectivesStep value={answers.objectives} isSaving={isSaving} onNext={onNext} />;
    case 1:
      return <HorizonStep value={answers.horizon} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
    case 2:
      return <ContributionStep value={answers.contribution} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
    case 3:
      return (
        <FinancialSituationStep value={answers.financial_situation} isSaving={isSaving} onNext={onNext} onBack={onBack} />
      );
    case 4:
      return <LiquidityStep value={answers.liquidity} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
    case 5:
      return <IncomeNeedStep value={answers.income_need} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
    case 6:
      return <KnowledgeStep value={answers.knowledge} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
    case 7:
      return <RiskToleranceStep value={answers.risk_tolerance} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
    default:
      return <RestrictionsStep value={answers.restrictions} isSaving={isSaving} onNext={onNext} onBack={onBack} />;
  }
}

function StepActions({
  isSaving,
  canContinue,
  onBack,
  isLast,
}: {
  isSaving: boolean;
  canContinue: boolean;
  onBack?: () => void;
  isLast?: boolean;
}) {
  return (
    <div className="onboarding-actions">
      {onBack ? (
        <Button type="button" variant="ghost" onClick={onBack} disabled={isSaving}>
          Voltar
        </Button>
      ) : (
        <span />
      )}
      <Button type="submit" disabled={!canContinue || isSaving}>
        {isSaving ? "Salvando..." : isLast ? "Calcular meu perfil" : "Continuar"}
      </Button>
    </div>
  );
}

function ObjectivesStep({
  value,
  isSaving,
  onNext,
}: {
  value: WizardAnswers["objectives"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
}) {
  const [selected, setSelected] = useState(value.primary_objective ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ objectives: { primary_objective: selected as never, secondary_objectives: [] } });
      }}
    >
      <h1>Qual é o seu principal objetivo com esse patrimônio?</h1>
      <div className="onboarding-options" role="radiogroup" aria-label="Objetivo principal">
        {OBJECTIVE_OPTIONS.map((option) => (
          <label key={option.value} className={`onboarding-option ${selected === option.value ? "selected" : ""}`}>
            <input
              type="radio"
              name="primary_objective"
              value={option.value}
              checked={selected === option.value}
              onChange={() => setSelected(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
      <StepActions isSaving={isSaving} canContinue={Boolean(selected)} />
    </form>
  );
}

function HorizonStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["horizon"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [selected, setSelected] = useState(value.horizon ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ horizon: { horizon: selected as never } });
      }}
    >
      <h1>Por quanto tempo pretende manter esse dinheiro investido?</h1>
      <div className="onboarding-options" role="radiogroup" aria-label="Horizonte de investimento">
        {HORIZON_OPTIONS.map((option) => (
          <label key={option.value} className={`onboarding-option ${selected === option.value ? "selected" : ""}`}>
            <input
              type="radio"
              name="horizon"
              value={option.value}
              checked={selected === option.value}
              onChange={() => setSelected(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
      <p className="onboarding-hint">Você poderá alterar isso depois.</p>
      <StepActions isSaving={isSaving} canContinue={Boolean(selected)} onBack={onBack} />
    </form>
  );
}

function ContributionStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["contribution"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [monthly, setMonthly] = useState(value.monthly_contribution ?? "0");
  const [initial, setInitial] = useState(value.initial_contribution ?? "0");
  const [stability, setStability] = useState(value.contribution_stability ?? "fixo");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({
          contribution: {
            monthly_contribution: normalizeDecimalForApi(monthly),
            initial_contribution: normalizeDecimalForApi(initial),
            contribution_stability: stability as never,
          },
        });
      }}
    >
      <h1>Quanto você pretende investir por mês?</h1>
      <CurrencyInput label="Aporte mensal" name="monthly_contribution" value={monthly} onChange={(e) => setMonthly(e.target.value)} />
      <CurrencyInput label="Investimento inicial (se houver)" name="initial_contribution" value={initial} onChange={(e) => setInitial(e.target.value)} />
      <div className="onboarding-options" role="radiogroup" aria-label="Estabilidade do aporte">
        <label className={`onboarding-option ${stability === "fixo" ? "selected" : ""}`}>
          <input type="radio" name="stability" checked={stability === "fixo"} onChange={() => setStability("fixo")} />
          Aporte fixo, previsível
        </label>
        <label className={`onboarding-option ${stability === "variavel" ? "selected" : ""}`}>
          <input type="radio" name="stability" checked={stability === "variavel"} onChange={() => setStability("variavel")} />
          Aporte variável, conforme sobra no mês
        </label>
      </div>
      <p className="onboarding-hint">Você poderá alterar este valor depois.</p>
      <StepActions isSaving={isSaving} canContinue onBack={onBack} />
    </form>
  );
}

function FinancialSituationStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["financial_situation"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [incomeRange, setIncomeRange] = useState(value.income_range ?? "");
  const [netWorthRange, setNetWorthRange] = useState(value.investable_net_worth_range ?? "");
  const [reserveMonths, setReserveMonths] = useState(String(value.emergency_reserve_months ?? 0));
  const [hasDebt, setHasDebt] = useState<boolean | null>(value.has_relevant_debt);
  const [dependents, setDependents] = useState(String(value.dependents ?? 0));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({
          financial_situation: {
            income_range: incomeRange as never,
            investable_net_worth_range: netWorthRange as never,
            emergency_reserve_months: Number(reserveMonths) || 0,
            has_relevant_debt: hasDebt,
            dependents: Number(dependents) || 0,
          },
        });
      }}
    >
      <h1>Um pouco sobre sua situação financeira</h1>
      <p className="onboarding-hint">Usamos isso apenas para avaliar sua capacidade de assumir risco.</p>
      <div className="onboarding-field-group">
        <span>Faixa de renda mensal</span>
        <div className="onboarding-options" role="radiogroup" aria-label="Faixa de renda">
          {INCOME_RANGE_OPTIONS.map((option) => (
            <label key={option.value} className={`onboarding-option ${incomeRange === option.value ? "selected" : ""}`}>
              <input type="radio" name="income_range" checked={incomeRange === option.value} onChange={() => setIncomeRange(option.value)} />
              {option.label}
            </label>
          ))}
        </div>
      </div>
      <div className="onboarding-field-group">
        <span>Patrimônio disponível para investir</span>
        <div className="onboarding-options" role="radiogroup" aria-label="Patrimônio investível">
          {NET_WORTH_OPTIONS.map((option) => (
            <label key={option.value} className={`onboarding-option ${netWorthRange === option.value ? "selected" : ""}`}>
              <input type="radio" name="net_worth_range" checked={netWorthRange === option.value} onChange={() => setNetWorthRange(option.value)} />
              {option.label}
            </label>
          ))}
        </div>
      </div>
      <Input
        label="Reserva de emergência atual (em meses de despesas)"
        type="number"
        min={0}
        max={60}
        value={reserveMonths}
        onChange={(e) => setReserveMonths(e.target.value)}
      />
      <Input label="Número de dependentes" type="number" min={0} max={20} value={dependents} onChange={(e) => setDependents(e.target.value)} />
      <div className="onboarding-field-group">
        <span>Possui dívidas de alto custo (cartão, cheque especial)?</span>
        <div className="onboarding-options" role="radiogroup" aria-label="Dívidas relevantes">
          <label className={`onboarding-option ${hasDebt === true ? "selected" : ""}`}>
            <input type="radio" name="has_debt" checked={hasDebt === true} onChange={() => setHasDebt(true)} />
            Sim
          </label>
          <label className={`onboarding-option ${hasDebt === false ? "selected" : ""}`}>
            <input type="radio" name="has_debt" checked={hasDebt === false} onChange={() => setHasDebt(false)} />
            Não
          </label>
        </div>
      </div>
      <StepActions isSaving={isSaving} canContinue={Boolean(incomeRange && netWorthRange && hasDebt !== null)} onBack={onBack} />
    </form>
  );
}

function LiquidityStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["liquidity"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [selected, setSelected] = useState(value.liquidity_need ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ liquidity: { liquidity_need: selected as never } });
      }}
    >
      <h1>Qual sua necessidade de liquidez?</h1>
      <div className="onboarding-options" role="radiogroup" aria-label="Necessidade de liquidez">
        {LIQUIDITY_OPTIONS.map((option) => (
          <label key={option.value} className={`onboarding-option ${selected === option.value ? "selected" : ""}`}>
            <input type="radio" name="liquidity_need" checked={selected === option.value} onChange={() => setSelected(option.value)} />
            {option.label}
          </label>
        ))}
      </div>
      <StepActions isSaving={isSaving} canContinue={Boolean(selected)} onBack={onBack} />
    </form>
  );
}

function IncomeNeedStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["income_need"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [selected, setSelected] = useState(value.income_need ?? "");
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ income_need: { income_need: selected as never } });
      }}
    >
      <h1>Você depende (ou pretende depender) da renda gerada pelos investimentos?</h1>
      <div className="onboarding-options" role="radiogroup" aria-label="Necessidade de renda">
        {INCOME_NEED_OPTIONS.map((option) => (
          <label key={option.value} className={`onboarding-option ${selected === option.value ? "selected" : ""}`}>
            <input type="radio" name="income_need" checked={selected === option.value} onChange={() => setSelected(option.value)} />
            {option.label}
          </label>
        ))}
      </div>
      <StepActions isSaving={isSaving} canContinue={Boolean(selected)} onBack={onBack} />
    </form>
  );
}

function KnowledgeStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["knowledge"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [choices, setChoices] = useState<Record<string, string>>(value.answers ?? {});
  const allAnswered = KNOWLEDGE_QUESTIONS.every((question) => choices[question.id]);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ knowledge: { answers: choices as never } });
      }}
    >
      <h1>Um rápido teste de conhecimento</h1>
      <p className="onboarding-hint">Não existe resposta certa ou errada que te impeça de investir — isso só nos ajuda a explicar melhor os riscos.</p>
      {KNOWLEDGE_QUESTIONS.map((question) => (
        <div key={question.id} className="onboarding-field-group">
          <span>{question.question}</span>
          <div className="onboarding-options" role="radiogroup" aria-label={question.question}>
            {question.options.map((option) => (
              <label key={option.value} className={`onboarding-option ${choices[question.id] === option.value ? "selected" : ""}`}>
                <input
                  type="radio"
                  name={question.id}
                  checked={choices[question.id] === option.value}
                  onChange={() => setChoices((current) => ({ ...current, [question.id]: option.value }))}
                />
                {option.label}
              </label>
            ))}
          </div>
        </div>
      ))}
      <StepActions isSaving={isSaving} canContinue={allAnswered} onBack={onBack} />
    </form>
  );
}

function RiskToleranceStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["risk_tolerance"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [choices, setChoices] = useState<Record<string, string>>(value.scenarios ?? {});
  const allAnswered = RISK_SCENARIOS.every((scenario) => choices[scenario.id]);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ risk_tolerance: { scenarios: choices as never } });
      }}
    >
      <h1>Como você reagiria a estas situações?</h1>
      {RISK_SCENARIOS.map((scenario) => (
        <div key={scenario.id} className="onboarding-field-group">
          <span>{scenario.scenario}</span>
          <div className="onboarding-options" role="radiogroup" aria-label={scenario.scenario}>
            {RISK_SCENARIO_OPTIONS.map((option) => (
              <label key={option.value} className={`onboarding-option ${choices[scenario.id] === option.value ? "selected" : ""}`}>
                <input
                  type="radio"
                  name={scenario.id}
                  checked={choices[scenario.id] === option.value}
                  onChange={() => setChoices((current) => ({ ...current, [scenario.id]: option.value }))}
                />
                {option.label}
              </label>
            ))}
          </div>
        </div>
      ))}
      <StepActions isSaving={isSaving} canContinue={allAnswered} onBack={onBack} />
    </form>
  );
}

function RestrictionsStep({
  value,
  isSaving,
  onNext,
  onBack,
}: {
  value: WizardAnswers["restrictions"];
  isSaving: boolean;
  onNext: (partial: Partial<WizardAnswers>) => void;
  onBack?: () => void;
}) {
  const [restricted, setRestricted] = useState<string[]>(value.restricted_classes ?? []);

  function toggle(assetClass: string) {
    setRestricted((current) =>
      current.includes(assetClass) ? current.filter((item) => item !== assetClass) : [...current, assetClass],
    );
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onNext({ restrictions: { restricted_classes: restricted, allowed_classes: [] } });
      }}
    >
      <h1>Alguma classe de ativo que você prefere evitar?</h1>
      <p className="onboarding-hint">Opcional — marque apenas o que você não quer que apareça na sua política.</p>
      <div className="onboarding-options" role="group" aria-label="Classes a evitar">
        {RESTRICTABLE_CLASSES.map((assetClass) => (
          <label key={assetClass} className={`onboarding-option ${restricted.includes(assetClass) ? "selected" : ""}`}>
            <input type="checkbox" checked={restricted.includes(assetClass)} onChange={() => toggle(assetClass)} />
            {assetClass}
          </label>
        ))}
      </div>
      <StepActions isSaving={isSaving} canContinue isLast onBack={onBack} />
    </form>
  );
}

function ReviewStep({
  evaluation,
  isSaving,
  onEdit,
  onConfirm,
}: {
  evaluation: InvestorProfileEvaluation;
  isSaving: boolean;
  onEdit: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="onboarding-review">
      <h1>Seu perfil de investidor</h1>
      <p className="onboarding-classification">{evaluation.dimensions.overall_classification}</p>
      <ul className="onboarding-dimensions">
        <li>Tolerância psicológica ao risco: {evaluation.dimensions.risk_tolerance_score}/100</li>
        <li>Capacidade financeira de assumir risco: {evaluation.dimensions.risk_capacity_score}/100</li>
        <li>Horizonte: {evaluation.dimensions.horizon_score}/100</li>
        <li>Necessidade de liquidez: {evaluation.dimensions.liquidity_need_score}/100</li>
        <li>Necessidade de renda: {evaluation.dimensions.income_need_score}/100</li>
        <li>Conhecimento: {evaluation.dimensions.knowledge_score}/100</li>
        <li>Adequação da reserva de emergência: {evaluation.dimensions.emergency_reserve_adequacy_score}/100</li>
      </ul>
      <h2>Por que essa classificação?</h2>
      <ul className="onboarding-explanations">
        {evaluation.explanations.map((item) => (
          <li key={item.dimension}>{item.message}</li>
        ))}
      </ul>
      <h2>Política proposta</h2>
      <table className="onboarding-policy-table">
        <tbody>
          {evaluation.policy_preview.allocations.map((allocation) => (
            <tr key={allocation.asset_class}>
              <td>{allocation.asset_class}</td>
              <td>{formatPercent(allocation.target_percentage)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="onboarding-hint">
        Esta política define limites e metas por classe — a seleção dos ativos continua sendo feita pelos
        motores quantitativos da Carteira Inteligente. Você pode revisar ou refazer essa avaliação quando quiser em Configurações.
      </p>
      <div className="onboarding-actions">
        <Button type="button" variant="ghost" onClick={onEdit} disabled={isSaving}>
          Revisar respostas
        </Button>
        <Button type="button" onClick={onConfirm} disabled={isSaving}>
          {isSaving ? "Confirmando..." : "Confirmar e continuar"}
        </Button>
      </div>
    </div>
  );
}
