import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRouter } from "../src/app/router";
import { renderWithProviders } from "./render";
import { server } from "./testServer";

const api = "http://127.0.0.1:8000";

async function openAuthenticated(path = "/") {
  sessionStorage.setItem("mesa_quant_session", "test-token");
  const user = userEvent.setup();
  renderWithProviders(<AppRouter />, path);
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument(), { timeout: 10_000 });
  return user;
}

function failIntelligence(status: number, detail: string) {
  server.use(http.get(`${api}/intelligence/portfolio`, () => HttpResponse.json({ detail }, { status })));
}

describe("resiliência de /planejar", () => {
  it("não consulta diagnóstico pesado em outras abas", async () => {
    let calls = 0;
    server.use(http.get(`${api}/intelligence/portfolio`, () => {
      calls += 1;
      return HttpResponse.json({ detail: "Falha simulada" }, { status: 500 });
    }));
    const user = await openAuthenticated("/planejar?secao=montar-carteira");
    expect(await screen.findByRole("heading", { name: "Monte uma carteira para o seu momento" })).toBeInTheDocument();
    expect(calls).toBe(0);
    await user.click(screen.getByRole("tab", { name: "Futuro financeiro" }));
    expect(calls).toBe(0);
    await user.click(screen.getByRole("tab", { name: "Diagnóstico" }));
    await waitFor(() => expect(calls).toBe(1));
  });

  it("exibe falha de servidor do perfil separadamente do diagnóstico", async () => {
    server.use(http.get(`${api}/investor-profile`, () =>
      HttpResponse.json({ detail: "erro simulado" }, { status: 503 }),
    ));
    await openAuthenticated("/planejar?secao=montar-carteira");
    expect(await screen.findByText(/O servidor não conseguiu carregar o perfil/)).toBeInTheDocument();
  });

  it("shell, abas e Perfil do Investidor continuam quando /intelligence/portfolio falha (500)", async () => {
    failIntelligence(500, "erro interno simulado");
    await openAuthenticated("/planejar");

    expect(await screen.findByRole("heading", { name: "Inteligência de Carteira" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(4);
    // Perfil do Investidor tem query própria (investor-profile), independente.
    expect(await screen.findByText("Concluído")).toBeInTheDocument();

    // Área default (sem ?secao=) é Diagnóstico -- já mostra o erro localizado.
    expect(await screen.findByText(/erro interno ao calcular sua carteira/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("Montar carteira continua utilizável quando /intelligence/portfolio falha", async () => {
    failIntelligence(500, "erro interno simulado");
    const user = await openAuthenticated("/planejar?secao=montar-carteira");

    await user.click(await screen.findByRole("tab", { name: "Montar carteira" }));
    expect(await screen.findByRole("heading", { name: "Monte uma carteira para o seu momento" })).toBeInTheDocument();
    const submit = await screen.findByRole("button", { name: "Montar minha carteira" });
    expect(submit).toBeDisabled(); // Sem supor que aporte mensal = aporte de hoje.
    const daily = screen.getByLabelText("Valor de aporte desejável");
    await user.clear(daily);
    await user.type(daily, "90000");
    expect(submit).toBeEnabled();
  });

  it("Futuro financeiro (Estratégia) continua utilizável quando /intelligence/portfolio falha", async () => {
    failIntelligence(500, "erro interno simulado");
    const user = await openAuthenticated("/planejar?secao=futuro-financeiro");

    await user.click(await screen.findByRole("tab", { name: "Futuro financeiro" }));
    expect(await screen.findByText("Total da alocação: 100,00%")).toBeInTheDocument();
  });

  it("diferencia 422 (dados da carteira) de 500 (erro interno) na mensagem exibida", async () => {
    failIntelligence(422, "Quantidade solicitada para venda supera a disponivel.");
    await openAuthenticated("/planejar");

    expect(await screen.findByText(/problema nos dados da sua carteira/i)).toBeInTheDocument();
    expect(screen.getByText(/Quantidade solicitada para venda supera a disponivel/)).toBeInTheDocument();
  });

  it("retry localizado chama novamente somente a query de intelligence", async () => {
    let calls = 0;
    server.use(
      http.get(`${api}/intelligence/portfolio`, () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json({ detail: "instavel" }, { status: 500 });
        return HttpResponse.json({
          overview: { investments_count: 0, current_equity: "0", total_invested: "0", profit_loss: "0", profitability: "0", received_income: "0", fixed_income_percentage: "0", variable_income_percentage: "0", portfolio_classification: "Carteira em formação", risk_level: "Dados insuficientes", data_quality: "Dados insuficientes", market_data_status: "unavailable", last_updated_at: "2026-08-14T01:00:00Z", insufficient_data_message: "Dados insuficientes para calcular." },
          diagnosis: { portfolio_score: "0", diversification_score: "0", concentration_score: "0", liquidity_score: null, income_score: null, risk_level: "Dados insuficientes", data_quality: "Dados insuficientes", warnings: [], strengths: [], weaknesses: [], class_allocations: [], unclassified_assets: [] },
          recommendations: [], rebalancing: [], opportunities: [], policy: null,
          available_indicators: {}, unavailable_indicators: {}, generated_at: "2026-08-14T01:00:00Z",
        });
      }),
    );
    const user = await openAuthenticated("/planejar");

    expect(await screen.findByText(/erro interno ao calcular sua carteira/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("Carteira vazia")).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});
