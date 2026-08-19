import { http, HttpResponse } from "msw";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRouter } from "../src/app/router";
import { renderWithProviders } from "./render";
import { server } from "./testServer";

const api = "http://127.0.0.1:8000";

function pendingStatus(status: string) {
  return HttpResponse.json({
    status,
    version: 1,
    last_reviewed_at: null,
    confirmed_at: null,
    updated_at: "2026-08-17T12:00:00Z",
  });
}

function authenticate() {
  sessionStorage.setItem("mesa_quant_session", "test-token");
}

// Mesma forma que o backend usa para validar `Decimal` (sem virgula, sem milhar).
function isBackendDecimalParseable(value: string) {
  return /^-?\d+(\.\d+)?$/.test(value);
}

type ContributionPayload = {
  contribution: {
    monthly_contribution: string;
    initial_contribution: string;
    contribution_stability: string;
  };
};

describe("onboarding do perfil do investidor", () => {
  it("usuário não autenticado não acessa /onboarding", async () => {
    renderWithProviders(<AppRouter />, "/onboarding");
    await waitFor(() => expect(screen.getByLabelText("E-mail")).toBeVisible());
  });

  it("usuário autenticado com onboarding pendente é redirecionado ao acessar rota protegida normal", async () => {
    server.use(http.get(`${api}/investor-profile/status`, () => pendingStatus("needs_onboarding")));
    authenticate();
    renderWithProviders(<AppRouter />, "/carteira");
    await screen.findByText("Qual é o seu principal objetivo com esse patrimônio?", {}, { timeout: 10_000 });
  });

  it("usuário com onboarding já completo não é reenviado ao onboarding", async () => {
    authenticate();
    renderWithProviders(<AppRouter />, "/carteira");
    await waitFor(
      () => expect(screen.queryByText("Qual é o seu principal objetivo com esse patrimônio?")).not.toBeInTheDocument(),
      { timeout: 10_000 },
    );
  });

  it("refresh durante onboarding preserva o estado pendente (sessão restaurada)", async () => {
    server.use(http.get(`${api}/investor-profile/status`, () => pendingStatus("in_progress")));
    authenticate();
    renderWithProviders(<AppRouter />, "/");
    await screen.findByText("Qual é o seu principal objetivo com esse patrimônio?", {}, { timeout: 10_000 });
  });

  it("percorre o wizard completo e confirma, direcionando ao Dashboard", async () => {
    // Estado mutável simples: reflete que, após confirm(), o próximo GET de
    // status deixa de ser "in_progress" — do contrário o OnboardingGate
    // redirecionaria de volta ao acessar "/" após a confirmação.
    let currentStatus = "in_progress";
    server.use(
      http.get(`${api}/investor-profile/status`, () => pendingStatus(currentStatus)),
      http.post(`${api}/investor-profile/confirm`, () => {
        currentStatus = "complete";
        return HttpResponse.json({
          id: "investor-profile-1",
          user_id: "user-1",
          status: "complete",
          version: 1,
          primary_objective: "crescimento_patrimonial",
          secondary_objectives: [],
          horizon: "mais_10_anos",
          initial_contribution: null,
          monthly_contribution: "1000",
          contribution_stability: "fixo",
          income_range: null,
          investable_net_worth_range: null,
          emergency_reserve_months: 6,
          has_relevant_debt: null,
          dependents: null,
          liquidity_need: "baixa",
          income_need: "nenhuma",
          allowed_classes: null,
          restricted_classes: null,
          dimensions: {
            risk_tolerance_score: 66,
            risk_capacity_score: 70,
            horizon_score: 90,
            liquidity_need_score: 20,
            income_need_score: 10,
            knowledge_score: 20,
            emergency_reserve_adequacy_score: 100,
            overall_classification: "Moderado",
          },
          explanations: [],
          policy_preview: null,
          evaluated_at: "2026-08-17T12:00:00Z",
          confirmed_at: "2026-08-17T12:00:00Z",
          last_reviewed_at: null,
          created_at: "2026-08-17T12:00:00Z",
          updated_at: "2026-08-17T12:00:00Z",
        });
      }),
    );
    authenticate();
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/onboarding");

    await user.click(await screen.findByLabelText("Crescimento patrimonial", {}, { timeout: 10_000 }));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await user.click(await screen.findByLabelText("Mais de 10 anos"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Quanto você pretende investir por mês?");
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Um pouco sobre sua situação financeira");
    await user.click(screen.getByLabelText("Até R$ 3.000"));
    await user.click(screen.getByLabelText("Até R$ 10.000"));
    await user.click(screen.getByLabelText("Não"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await user.click(await screen.findByLabelText(/Baixa — posso deixar/));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await user.click(await screen.findByLabelText("Não preciso de renda dos investimentos agora"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Um rápido teste de conhecimento");
    for (const question of [
      "O que significa volatilidade de um investimento?",
      "Qual o principal benefício de diversificar investimentos entre diferentes classes de ativos?",
      "Investimentos com potencial de maior retorno no longo prazo geralmente...",
      "Qual a principal diferença entre renda fixa e renda variável?",
      "O que é 'marcação a mercado' em um investimento de renda fixa?",
    ]) {
      const group = screen.getByRole("radiogroup", { name: question });
      const firstOption = within(group).getAllByRole("radio")[0];
      await user.click(firstOption);
    }
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Como você reagiria a estas situações?");
    const scenarioGroups = screen.getAllByRole("radiogroup");
    for (const group of scenarioGroups) {
      await user.click(within(group).getAllByRole("radio")[2]);
    }
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Alguma classe de ativo que você prefere evitar?");
    await user.click(screen.getByRole("button", { name: "Calcular meu perfil" }));

    await screen.findByText("Seu perfil de investidor", {}, { timeout: 10_000 });
    expect(screen.getByText("Moderado")).toBeVisible();
    expect(screen.getByText(/Tolerância psicológica ao risco/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Confirmar e continuar/ }));
    expect((await screen.findAllByText("Patrimônio", {}, { timeout: 10_000 })).length).toBeGreaterThan(0);
  });

  it("converte aporte mensal e inicial de Real (pt-BR) para decimal antes de enviar ao backend (bug 422)", async () => {
    let capturedBody: ContributionPayload | null = null;
    server.use(
      http.get(`${api}/investor-profile/status`, () => pendingStatus("needs_onboarding")),
      http.put(`${api}/investor-profile/answers`, async ({ request }) => {
        capturedBody = (await request.json()) as ContributionPayload;
        return HttpResponse.json({ id: "investor-profile-1" });
      }),
    );
    authenticate();
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/onboarding");

    await user.click(await screen.findByLabelText("Crescimento patrimonial", {}, { timeout: 10_000 }));
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(await screen.findByLabelText("Mais de 10 anos"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Quanto você pretende investir por mês?");
    const monthlyInput = screen.getByLabelText("Aporte mensal");
    const initialInput = screen.getByLabelText("Investimento inicial (se houver)");
    await user.clear(monthlyInput);
    await user.type(monthlyInput, "50000");
    expect(monthlyInput).toHaveValue("500,00");
    await user.clear(initialInput);
    await user.type(initialInput, "000");
    expect(initialInput).toHaveValue("0,00");
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    // Cast (não narrowing): `waitFor` acima ja garante nao-nulo em runtime; o
    // TS estreita `let` reatribuido dentro do closure do MSW para `null`.
    const body = capturedBody as unknown as ContributionPayload;
    expect(body.contribution.monthly_contribution).toBe("500");
    expect(body.contribution.monthly_contribution).not.toMatch(/,/);
    expect(body.contribution.initial_contribution).toBe("0");
    expect(body.contribution.contribution_stability).toBe("fixo");
    expect(isBackendDecimalParseable(body.contribution.monthly_contribution)).toBe(true);
  });

  it("preserva casas decimais nao inteiras (1.500,50) e o modo de aporte variavel", async () => {
    let capturedBody: ContributionPayload | null = null;
    server.use(
      http.get(`${api}/investor-profile/status`, () => pendingStatus("needs_onboarding")),
      http.put(`${api}/investor-profile/answers`, async ({ request }) => {
        capturedBody = (await request.json()) as ContributionPayload;
        return HttpResponse.json({ id: "investor-profile-1" });
      }),
    );
    authenticate();
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/onboarding");

    await user.click(await screen.findByLabelText("Crescimento patrimonial", {}, { timeout: 10_000 }));
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(await screen.findByLabelText("Mais de 10 anos"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Quanto você pretende investir por mês?");
    const monthlyInput = screen.getByLabelText("Aporte mensal");
    await user.clear(monthlyInput);
    await user.type(monthlyInput, "150050");
    expect(monthlyInput).toHaveValue("1.500,50");
    await user.click(screen.getByLabelText("Aporte variável, conforme sobra no mês"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    // Cast (não narrowing): `waitFor` acima ja garante nao-nulo em runtime; o
    // TS estreita `let` reatribuido dentro do closure do MSW para `null`.
    const body = capturedBody as unknown as ContributionPayload;
    expect(body.contribution.monthly_contribution).toBe("1500.5");
    expect(body.contribution.contribution_stability).toBe("variavel");
  });

  it("round trip: aporte salvo como decimal da API aparece em Real e volta como decimal ao salvar de novo", async () => {
    let capturedBody: ContributionPayload | null = null;
    server.use(
      http.get(`${api}/investor-profile/status`, () => pendingStatus("in_progress")),
      http.get(`${api}/investor-profile`, () =>
        HttpResponse.json({
          id: "investor-profile-1",
          user_id: "user-1",
          status: "in_progress",
          version: 1,
          primary_objective: "crescimento_patrimonial",
          secondary_objectives: [],
          horizon: "mais_10_anos",
          initial_contribution: "0.00",
          monthly_contribution: "500.00",
          contribution_stability: "fixo",
          income_range: null,
          investable_net_worth_range: null,
          emergency_reserve_months: null,
          has_relevant_debt: null,
          dependents: null,
          liquidity_need: null,
          income_need: null,
          allowed_classes: null,
          restricted_classes: null,
          dimensions: null,
          explanations: [],
          policy_preview: null,
          evaluated_at: null,
          confirmed_at: null,
          last_reviewed_at: null,
          created_at: "2026-08-17T12:00:00Z",
          updated_at: "2026-08-17T12:00:00Z",
        }),
      ),
      http.put(`${api}/investor-profile/answers`, async ({ request }) => {
        capturedBody = (await request.json()) as ContributionPayload;
        return HttpResponse.json({ id: "investor-profile-1" });
      }),
    );
    authenticate();
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/onboarding");

    await user.click(await screen.findByLabelText("Crescimento patrimonial", {}, { timeout: 10_000 }));
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(await screen.findByLabelText("Mais de 10 anos"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Quanto você pretende investir por mês?");
    await waitFor(() => expect(screen.getByLabelText("Aporte mensal")).toHaveValue("500,00"));

    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    // Cast (não narrowing): `waitFor` acima ja garante nao-nulo em runtime; o
    // TS estreita `let` reatribuido dentro do closure do MSW para `null`.
    const body = capturedBody as unknown as ContributionPayload;
    expect(body.contribution.monthly_contribution).toBe("500");
    expect(body.contribution.monthly_contribution).not.toBe("50000");
    expect(body.contribution.monthly_contribution).not.toMatch(/,/);
    expect(isBackendDecimalParseable(body.contribution.monthly_contribution)).toBe(true);
  });

  it("exibe a mensagem real de validação da API em erro 422, sem cair no texto generico nem expor dados sensiveis", async () => {
    server.use(
      http.get(`${api}/investor-profile/status`, () => pendingStatus("needs_onboarding")),
      http.put(`${api}/investor-profile/answers`, async ({ request }) => {
        const body = (await request.json()) as { contribution?: unknown };
        if (!body.contribution) {
          return HttpResponse.json({ id: "investor-profile-1" });
        }
        return HttpResponse.json(
          {
            detail: [
              {
                loc: ["body", "contribution", "monthly_contribution"],
                msg: "Input should be a valid decimal",
                type: "decimal_parsing",
              },
            ],
          },
          { status: 422 },
        );
      }),
    );
    authenticate();
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/onboarding");

    await user.click(await screen.findByLabelText("Crescimento patrimonial", {}, { timeout: 10_000 }));
    await user.click(screen.getByRole("button", { name: "Continuar" }));
    await user.click(await screen.findByLabelText("Mais de 10 anos"));
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    await screen.findByText("Quanto você pretende investir por mês?");
    await user.click(screen.getByRole("button", { name: "Continuar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("contribution.monthly_contribution: Input should be a valid decimal");
    expect(alert).not.toHaveTextContent("Não foi possível salvar sua resposta agora. Tente novamente.");
    expect(document.body.textContent).not.toContain("test-token");
  });

  it("mostra a revisão diretamente quando o status já é pending_confirmation", async () => {
    server.use(
      http.get(`${api}/investor-profile/status`, () => pendingStatus("pending_confirmation")),
      http.get(`${api}/investor-profile`, () =>
        HttpResponse.json({
          id: "investor-profile-1",
          user_id: "user-1",
          status: "pending_confirmation",
          version: 1,
          primary_objective: "crescimento_patrimonial",
          secondary_objectives: [],
          horizon: "mais_10_anos",
          initial_contribution: null,
          monthly_contribution: "1000",
          contribution_stability: "fixo",
          income_range: null,
          investable_net_worth_range: null,
          emergency_reserve_months: 6,
          has_relevant_debt: null,
          dependents: null,
          liquidity_need: "baixa",
          income_need: "nenhuma",
          allowed_classes: null,
          restricted_classes: null,
          dimensions: {
            risk_tolerance_score: 66,
            risk_capacity_score: 70,
            horizon_score: 90,
            liquidity_need_score: 20,
            income_need_score: 10,
            knowledge_score: 20,
            emergency_reserve_adequacy_score: 100,
            overall_classification: "Moderado",
          },
          explanations: [
            { dimension: "overall_classification", rule: "min(66,70)", result: "Moderado", message: "Classificação Moderado." },
          ],
          policy_preview: {
            objective: "crescimento_patrimonial",
            risk_profile: "Moderado",
            investment_horizon: "mais_10_anos",
            monthly_contribution: "1000",
            liquidity_need: "baixa",
            income_need: false,
            emergency_reserve_months: 6,
            maximum_weight_per_asset: "20",
            maximum_weight_per_sector: "30",
            maximum_weight_per_issuer: "30",
            rebalance_tolerance: "5",
            allocations: [
              { asset_class: "Ações", target_percentage: "25.00", minimum_percentage: "17.50", maximum_percentage: "37.50", enabled: true },
            ],
          },
          evaluated_at: "2026-08-17T12:00:00Z",
          confirmed_at: null,
          last_reviewed_at: null,
          created_at: "2026-08-17T12:00:00Z",
          updated_at: "2026-08-17T12:00:00Z",
        }),
      ),
    );
    authenticate();
    renderWithProviders(<AppRouter />, "/onboarding");
    await screen.findByText("Seu perfil de investidor", {}, { timeout: 10_000 });
  });
});

describe("Configurações — Perfil do Investidor", () => {
  it("exibe status, classificação e ação de refazer avaliação", async () => {
    authenticate();
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/configuracoes");
    await user.click(await screen.findByRole("link", { name: "Perfil do Investidor" }, { timeout: 10_000 }));
    expect(await screen.findByText("Concluído")).toBeVisible();
    expect(screen.getByText("Moderado")).toBeVisible();
    expect(screen.getByRole("button", { name: "Refazer avaliação" })).toBeVisible();
  });
});
