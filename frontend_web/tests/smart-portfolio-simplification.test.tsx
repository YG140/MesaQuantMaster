import { http, HttpResponse, delay } from "msw";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRouter } from "../src/app/router";
import { renderWithProviders } from "./render";
import { server } from "./testServer";

const api = "http://127.0.0.1:8000";

async function openBuilder() {
  sessionStorage.setItem("mesa_quant_session", "test-token");
  const user = userEvent.setup();
  renderWithProviders(<AppRouter />, "/planejar?secao=montar-carteira");
  await user.click(await screen.findByRole("tab", { name: "Montar carteira" }, { timeout: 10_000 }));
  await screen.findByRole("heading", { name: "Monte uma carteira para o seu momento" });
  return user;
}

function responseWithAssets() {
  const asset = (symbol: string, percentage: string, amount: string) => ({
    symbol, name: symbol, asset_class: "Ações", sector: "Financeiro", issuer: symbol,
    recommended_percentage: percentage, recommended_amount: amount, score: "82", confidence: "high",
    reasons: ["Boa aderência à estratégia."], risks: ["Oscilação de mercado."], missing_data: [],
    valuation_status: symbol === "MAIOR4" ? "near_estimated_value" : "insufficient_data",
    valuation_confidence: "medium",
    estimated_range_low: symbol === "MAIOR4" ? "40" : null,
    estimated_range_high: symbol === "MAIOR4" ? "55" : null,
    peer_comparison: symbol === "MAIOR4" ? "Referência relativa a 3 empresas do setor." : null,
    valuation_methods: ["Medianas setoriais"],
    reference_price: "25", executable_quantity: "10", executable_amount: amount,
    effective_percentage: percentage, target_gap: "0", execution_impediments: [],
    trading_symbol: symbol, economic_identity: symbol, market_segment: null, quantity_step: "1",
    indicators_used: [{ key: "roe", label: "ROE", value: "18", unit: "percentage", status: "available", unavailable_reason: null, source: "CVM", source_type: "official", reference_date: "2026-06-30", valid_until: "2026-09-30", freshness_status: "current" }],
  });
  return {
    class_allocations: [{ asset_class: "Ações", percentage: "75", amount: "7500", explanation: "Conforme a política." }],
    selections: [{ asset_class: "Ações", message: "Classe compatível.", data_status: "available" }],
    assets: [asset("MENOR3", "25", "2500"), asset("MAIOR4", "50", "5000")], exclusions: [],
    total_allocated_percentage: "75", total_allocated_amount: "7500", unallocated_amount: "2500",
    confidence: "high", status: "available", missing_data: [], strategy_summary: "Carteira alinhada ao perfil.",
    diagnosis: { phase: "accumulation", estimated_monthly_capacity: "1000", reserve_months_covered: "6", reserve_target: "18000", debt_alerts: [], liquidity_assessment: "adequate", missing_data: [], priority_actions: ["Manter aportes."], confidence: "high" },
    contribution_plan: [], projections: [{ name: "central", annual_appreciation_rate: "5", annual_income_rate: "3", total_contributed: "10000", projected_wealth: "15000", estimated_appreciation: "4000", estimated_income: "1000", estimated_periodic_income: "80", real_projected_wealth: "14000", projected_without_reinvestment: "14500" }],
    freedom_goal: { desired_monthly_income: "5000", required_wealth: "1500000", current_wealth: "10000", gap: "1490000", achieved_percentage: "0.67", estimated_years: null, withdrawal_rate: "4", safety_margin: "20", risks: [], improvement_actions: ["Aportar com regularidade."], confidence: "medium" },
    disclaimer: "Simulação educacional, não constitui ordem de compra e não garante retorno.", generated_at: "2026-08-13T12:00:00Z",
  };
}

describe("simplificação da Carteira Inteligente", () => {
  it("mostra somente o essencial e mantém as configurações avançadas fechadas", async () => {
    await openBuilder();
    expect(screen.getByLabelText("Valor disponível para investir")).toBeVisible();
    expect(screen.getByLabelText("Aporte mensal")).toBeVisible();
    expect(screen.getByLabelText("Objetivo")).toBeVisible();
    expect(screen.getByLabelText("Horizonte")).toBeVisible();
    expect(screen.getByLabelText("Perfil de risco")).toBeVisible();
    expect(screen.getByLabelText("Quantidade máxima de ativos")).toBeVisible();
    expect(screen.getByText("Configurações avançadas").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByLabelText("Limite por ativo (%)")).not.toBeVisible();
    expect(screen.getByRole("button", { name: "Montar minha carteira" })).toBeEnabled();
  });

  it("preserva parâmetros avançados no payload e bloqueia envio duplicado", async () => {
    let calls = 0;
    let payload: Record<string, unknown> = {};
    server.use(http.post(`${api}/intelligence/build-portfolio`, async ({ request }) => {
      calls += 1;
      payload = await request.json() as Record<string, unknown>;
      await delay(250);
      return HttpResponse.json(responseWithAssets());
    }));
    const user = await openBuilder();
    await user.click(screen.getByText("Configurações avançadas"));
    const limit = screen.getByLabelText("Limite por ativo (%)");
    await user.clear(limit); await user.type(limit, "15");
    const button = screen.getByRole("button", { name: "Montar minha carteira" });
    await user.click(button);
    expect(screen.getByRole("button", { name: /Analisando dados e montando sua carteira/ })).toBeDisabled();
    expect(calls).toBe(1);
    await waitFor(() => expect(payload.max_percentage_per_asset).toBe("15"));
    expect(payload.available_amount).toBe("10000");
    expect(payload.max_percentage_per_class).toBe("40");
    expect(payload.projection_years).toBe(20);
    expect(payload.reinvest_income).toBe(true);
  });

  it("destaca e ordena ativos, preservando valores e detalhes", async () => {
    server.use(http.post(`${api}/intelligence/build-portfolio`, () => HttpResponse.json(responseWithAssets())));
    const user = await openBuilder();
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    expect(await screen.findByRole("heading", { name: "Sua carteira recomendada" })).toBeVisible();
    const assets = screen.getAllByRole("article");
    expect(within(assets[0]).getByText("MAIOR4")).toBeVisible();
    expect(within(assets[0]).getByText("50,00%")).toBeVisible();
    expect(within(within(assets[0]).getByText("Valor-alvo").parentElement!).getByText("R$ 5.000,00")).toBeVisible();
    expect(screen.getByText("Saldo não alocado")).toBeVisible();
    expect(within(assets[0]).getByText("Faixa de preço indicativa por múltiplos do setor")).toBeVisible();
    expect(within(assets[0]).getByText("R$ 40,00 – R$ 55,00")).toBeVisible();
    expect(within(assets[0]).getByText(/não preço justo intrínseco/)).toBeVisible();
    await user.click(within(assets[0]).getByText("Ver detalhes"));
    expect(within(assets[0]).getByText("Boa aderência à estratégia.")).toBeVisible();
    expect(screen.getByText("Carteira executável")).toBeVisible();
    expect(screen.getByText("Plano de aportes")).toBeVisible();
    expect(screen.getAllByText(/Simulação educacional/).some((item) => item.offsetParent !== null || item.textContent?.includes("Simulação"))).toBe(true);
  });

  it("mostra execução no cartão, valor dos indicadores e procedência secundária", async () => {
    const response = responseWithAssets();
    Object.assign(response.assets[1], {
      recommended_amount: "833.99",
      reference_price: "37.42",
      executable_quantity: "22",
      executable_amount: "823.24",
      target_gap: "10.75",
      trading_symbol: "MAIOR4F",
      economic_identity: "MAIOR4",
      market_segment: "fractional",
      confidence: "low",
      missing_data: ["Faltam dados atuais de liquidez e valuation."],
      indicators_used: [
        { key: "dividend_yield", label: "Dividend Yield", value: "0", unit: "percentage", status: "available", unavailable_reason: null, source: "CVM", source_type: "official", reference_date: "2026-06-30", valid_until: "2026-09-30", freshness_status: "current" },
        { key: "price_earnings", label: "P/L", value: null, unit: "ratio", status: "unavailable", unavailable_reason: "Indicador não fornecido.", source: "BRAPI", source_type: "provider", reference_date: null, valid_until: null, freshness_status: "unavailable" },
      ],
    });
    server.use(http.post(`${api}/intelligence/build-portfolio`, () => HttpResponse.json(response)));
    const user = await openBuilder();
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    await screen.findByRole("heading", { name: "Sua carteira recomendada" });
    const asset = screen.getAllByRole("article").find((item) => within(item).queryByText("MAIOR4", { selector: "strong" }))!;
    expect(within(asset).getByText("22 unidades")).toBeVisible();
    expect(within(asset).getByText("R$ 37,42")).toBeVisible();
    expect(within(asset).getByText("R$ 823,24")).toBeVisible();
    expect(within(asset).getByText("R$ 10,75 não alocados neste ativo")).toBeVisible();
    expect(within(asset).getByText("Mercado fracionário")).toBeVisible();
    expect(within(within(asset).getByText("Confiança nos dados").parentElement!).getByText("Baixa")).toBeVisible();
    const limitations = within(asset).getByText("Limitações e indicadores não disponíveis");
    await user.click(limitations);
    expect(within(asset.querySelector(".confidence-explanation")!).getByText("Faltam dados atuais de liquidez e valuation.")).toBeVisible();
    await user.click(within(asset).getByText("Ver detalhes"));
    expect(within(asset).getByText("0,00%")).toBeVisible();
    expect(within(asset).getAllByText("Indisponível").length).toBeGreaterThan(0);
    expect(within(asset.querySelector(".indicator-table")!).queryByRole("columnheader", { name: "Fonte" })).not.toBeInTheDocument();
    const provenance = within(asset).getByText("Ver procedência e qualidade dos dados");
    expect(provenance).toBeVisible();
    await user.click(provenance);
    expect(within(asset).getByRole("columnheader", { name: "Fonte" })).toBeVisible();
    expect(within(asset).getByText("CVM")).toBeVisible();
  });

  it.each([
    ["not_applicable", null, "Não aplicável"],
    ["unavailable", null, "Indisponível"],
    ["available", "0", "0,00%"],
  ])("distingue indicador %s com valor %s", async (status, value, expected) => {
    const response = responseWithAssets();
    Object.assign(response.assets[1].indicators_used[0], { status, value });
    server.use(http.post(`${api}/intelligence/build-portfolio`, () => HttpResponse.json(response)));
    const user = await openBuilder();
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    await screen.findByRole("heading", { name: "Sua carteira recomendada" });
    const asset = screen.getAllByRole("article")[0];
    await user.click(within(asset).getByText("Ver detalhes"));
    expect(asset.querySelector('.indicator-table td[data-label="Valor"]')).toHaveTextContent(expected!);
  });

  it("separa dados ausentes, confiança e impedimentos de execução", async () => {
    const response = responseWithAssets();
    Object.assign(response.assets[1], {
      confidence: "high", missing_data: ["Cobertura de analistas ausente."],
      executable_quantity: null, execution_impediments: ["Preço de referência indisponível."],
    });
    server.use(http.post(`${api}/intelligence/build-portfolio`, () => HttpResponse.json(response)));
    const user = await openBuilder();
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    await screen.findByRole("heading", { name: "Sua carteira recomendada" });
    const asset = screen.getAllByRole("article")[0];
    const missing = within(asset).getByLabelText("Dados ausentes");
    expect(missing).toHaveTextContent("Cobertura de analistas ausente.");
    expect(missing).not.toHaveTextContent("Preço de referência indisponível.");
    expect(missing).not.toHaveTextContent("Alta");
    expect(within(asset).getByRole("note")).toHaveTextContent("Preço de referência indisponível.");
    expect(within(within(asset).getByText("Confiança nos dados").parentElement!).getByText("Alta")).toBeVisible();
  });

  it("não apresenta ticker único para um lote misto", async () => {
    const response = responseWithAssets();
    Object.assign(response.assets[1], { market_segment: "mixed", trading_symbol: null });
    server.use(http.post(`${api}/intelligence/build-portfolio`, () => HttpResponse.json(response)));
    const user = await openBuilder();
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    await screen.findByRole("heading", { name: "Sua carteira recomendada" });
    const asset = screen.getAllByRole("article")[0];
    expect(within(asset).getByText(/exigem tickers distintos/)).toBeVisible();
    expect(within(asset).queryByText(/Ticker negociável:/)).not.toBeInTheDocument();
  });

  it("explica ausência de ativos e preserva o formulário após erro", async () => {
    const user = await openBuilder();
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    expect(await screen.findByText(/Ainda não há dados suficientes para recomendar ativos/)).toBeVisible();
    expect(screen.getByText("Insuficiente")).toBeVisible();
    server.use(http.post(`${api}/intelligence/build-portfolio`, () => HttpResponse.json({ detail: "internal" }, { status: 500 })));
    const amount = screen.getByLabelText("Valor disponível para investir");
    await user.clear(amount); await user.type(amount, "12345");
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Seus dados foram preservados/);
    expect(amount).toHaveValue("123,45");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeVisible();
  });
});
