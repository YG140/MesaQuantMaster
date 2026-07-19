import { expect, test } from "@playwright/test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const policy = {
  id: "policy-1",
  user_id: "user-1",
  name: "Minha estrat\u00e9gia",
  objective: "crescimento patrimonial",
  risk_profile: "moderado",
  investment_horizon: "longo prazo",
  monthly_contribution: "900",
  liquidity_need: "m\u00e9dia",
  income_need: false,
  emergency_reserve_months: 6,
  maximum_weight_per_asset: "20",
  maximum_weight_per_sector: "30",
  maximum_weight_per_issuer: "30",
  rebalance_tolerance: "5",
  allocations: [
    { id: "allocation-1", asset_class: "A\u00e7\u00f5es", target_percentage: "60", minimum_percentage: "50", maximum_percentage: "70", enabled: true },
    { id: "allocation-2", asset_class: "Tesouro Direto", target_percentage: "40", minimum_percentage: "30", maximum_percentage: "50", enabled: true },
  ],
  created_at: "2026-07-16T18:30:00Z",
  updated_at: "2026-07-16T18:30:00Z",
};

test("fluxo principal de navegacao autenticada com mocks", async ({ page }) => {
  await page.route("**/auth/login", async (route) => {
    await route.fulfill({ json: { access_token: "e2e-token", token_type: "bearer" } });
  });
  await page.route("**/users/me", async (route) => {
    await route.fulfill({
      json: {
        id: "user-1",
        name: "Ana Quant",
        email: "ana@example.com",
        is_active: true,
        is_superuser: false,
        created_at: "2026-07-15T00:00:00",
      },
    });
  });
  await page.route("**/dashboard", async (route) => {
    await route.fulfill({ json: { patrimonio_total: "0", valor_investido: "0", lucro_prejuizo: "0", rentabilidade: "0", ativos: 0, operacoes: 0, caixa: "0", proventos: "0", market_data_status: "unavailable", quote_updated_at: null, unpriced_symbols: [] } });
  });
  await page.route("**/portfolio", async (route) => {
    await route.fulfill({ json: { total_invested: "0", total_market_value: "0", total_profit: "0", profitability: "0", allocation: [], valuation_basis: null, market_data_status: "unavailable", quote_updated_at: null, unpriced_symbols: [], positions: [] } });
  });
  await page.route("**/operations", async (route) => {
    await route.fulfill({ json: [] });
  });
  await page.route("**/intelligence/portfolio", async (route) => {
    await route.fulfill({
      json: {
        policy,
        overview: {
          current_equity: "521.00",
          total_invested: "521.00",
          profit_loss: "0",
          profitability: "0",
          received_income: null,
          investments_count: 1,
          fixed_income_percentage: "0",
          variable_income_percentage: "100",
          portfolio_classification: "Carteira em forma\u00e7\u00e3o",
          risk_level: "Alto",
          data_quality: "Boa",
          last_updated_at: "2026-07-16T18:30:00Z",
          market_data_status: "live",
          insufficient_data_message: "Dados insuficientes para calcular.",
        },
        diagnosis: {
          portfolio_score: "56.67",
          risk_level: "Alto",
          diversification_score: "20.00",
          concentration_score: "50.00",
          liquidity_score: null,
          income_score: null,
          data_quality: "Boa",
          warnings: ["H\u00e1 concentra\u00e7\u00e3o relevante em uma \u00fanica posi\u00e7\u00e3o."],
          strengths: ["Carteira possui posi\u00e7\u00f5es consolidadas."],
          weaknesses: ["H\u00e1 concentra\u00e7\u00e3o relevante em uma \u00fanica posi\u00e7\u00e3o."],
          class_allocations: [
            { asset_class: "A\u00e7\u00f5es", current_value: "521.00", current_percentage: "100", target_percentage: "60", minimum_percentage: "50", maximum_percentage: "70", difference_percentage: "-40", status: "Acima da estrat\u00e9gia" },
            { asset_class: "Tesouro Direto", current_value: "0", current_percentage: "0", target_percentage: "40", minimum_percentage: "30", maximum_percentage: "50", difference_percentage: "40", status: "Abaixo da estrat\u00e9gia" },
          ],
          unclassified_assets: [],
          calculated_at: "2026-07-16T18:30:00Z",
        },
        recommendations: [
          {
            asset_id: null,
            symbol: "A\u00e7\u00f5es",
            name: "A\u00e7\u00f5es",
            asset_class: "A\u00e7\u00f5es",
            recommendation: "Reduzir exposi\u00e7\u00e3o",
            valuation_status: "Dados insuficientes",
            confidence: "M\u00e9dia",
            current_weight: "100",
            target_weight: "60",
            current_value: "521.00",
            suggested_value: null,
            positive_reasons: ["Compara\u00e7\u00e3o feita contra a pol\u00edtica de investimentos salva."],
            risk_reasons: ["Classe acima da estrat\u00e9gia."],
            missing_data: [],
            indicators: [],
            generated_at: "2026-07-16T18:30:00Z",
            data_updated_at: null,
          },
        ],
        rebalancing: [
          { asset_class: "A\u00e7\u00f5es", current_percentage: "100", target_percentage: "60", difference_percentage: "-40", current_value: "521.00", target_value: "312.60", suggested_contribution: "0", missing_value: "0", excess_value: "208.40", status: "Acima da estrat\u00e9gia", explanation: "Classe acima da pol\u00edtica; evite novos aportes por enquanto." },
          { asset_class: "Tesouro Direto", current_percentage: "0", target_percentage: "40", difference_percentage: "40", current_value: "0", target_value: "208.40", suggested_contribution: "900.00", missing_value: "208.40", excess_value: "0", status: "Abaixo da estrat\u00e9gia", explanation: "Classe abaixo da pol\u00edtica; priorize novos aportes." },
        ],
        opportunities: [],
        available_indicators: { acoes: ["P/L", "P/VP"] },
        unavailable_indicators: { acoes: ["ROE"] },
        generated_at: "2026-07-16T18:30:00Z",
      },
    });
  });
  await page.route("**/intelligence/policy", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: policy });
      return;
    }
    const body = route.request().postDataJSON();
    await route.fulfill({ json: { ...body, id: "policy-1", user_id: "user-1", created_at: "2026-07-16T18:30:00Z", updated_at: "2026-07-16T18:30:00Z" } });
  });
  await page.route("**/intelligence/build-portfolio", async (route) => {
    await route.fulfill({
      json: {
        class_allocations: [
          { asset_class: "A\u00e7\u00f5es", percentage: "60", amount: "12000.00", explanation: "Distribui\u00e7\u00e3o baseada na sua pol\u00edtica de investimentos salva." },
          { asset_class: "Tesouro Direto", percentage: "40", amount: "8000.00", explanation: "Distribui\u00e7\u00e3o baseada na sua pol\u00edtica de investimentos salva." },
        ],
        selections: [
          { asset_class: "A\u00e7\u00f5es", message: "A sele\u00e7\u00e3o dos investimentos de cada classe ser\u00e1 feita quando houver dados suficientes e crit\u00e9rios espec\u00edficos integrados.", data_status: "indispon\u00edvel" },
        ],
        generated_at: "2026-07-16T18:30:00Z",
      },
    });
  });

  await page.goto("/carteira");
  await expect(page.getByRole("heading", { name: "Mesa Quant Master" })).toBeVisible();
  await page.getByLabel("E-mail").fill("ana@example.com");
  await page.getByLabel("Senha").fill("password123");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: /In.cio/ })).toBeVisible();
  await page.getByRole("link", { name: "Minha carteira" }).click();
  await expect(page.getByRole("heading", { name: "Minha carteira" })).toBeVisible();
  await expect(page.getByText(/Sua carteira ainda.*vazia/)).toBeVisible();
  await page.getByRole("link", { name: /Intelig.ncia de Carteira/ }).click();
  await expect(page.getByRole("heading", { name: /Intelig.ncia de Carteira/ })).toBeVisible();
  await page.getByRole("button", { name: /Minha estrat.gia/ }).click();
  await expect(page.getByText(/Total da aloca..o: 100,00%/)).toBeVisible();
  await page.getByRole("button", { name: /Salvar estrat.gia/ }).click();
  await expect(page.getByText(/Estrat.gia salva com sucesso/)).toBeVisible();
  await page.getByRole("button", { name: /Diagn.stico/ }).click();
  await expect(page.getByText(/Pontua..o da carteira/)).toBeVisible();
  await page.getByRole("button", { name: "Rebalanceamento" }).click();
  await expect(page.getByText("R$ 900,00")).toBeVisible();
  await page.getByRole("button", { name: /Recomenda..es/ }).click();
  await expect(page.getByText(/A..es - Reduzir exposi..o/)).toBeVisible();
  await page.getByRole("button", { name: "Montar carteira" }).click();
  await page.getByLabel(/Valor dispon.vel/).fill("20000");
  await page.getByRole("button", { name: "Gerar resultado" }).click();
  await expect(page.getByText(/Etapa 1 - Aloca..o entre classes/)).toBeVisible();
  await expect(page.getByText("R$ 12.000,00")).toBeVisible();
  await expect(page.getByText("R$ 8.000,00")).toBeVisible();
  await expect(page.getByText(/JSON|undefined|null|NaN/)).not.toBeVisible();
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page.getByRole("heading", { name: "Mesa Quant Master" })).toBeVisible();
});

test("bundle nao expoe chave BRAPI", async () => {
  const distPath = join(process.cwd(), "dist");
  if (!existsSync(distPath)) {
    test.skip(true, "dist ainda nao foi gerado");
  }
  const files = readdirSync(distPath, { recursive: true })
    .map((file) => join(distPath, String(file)))
    .filter((file) => /\.(js|css|html)$/.test(file));
  const bundle = files.map((file) => readFileSync(file, "utf8")).join("\n");

  expect(bundle).not.toContain(["BRAPI", "API", "KEY"].join("_"));
  expect(bundle).not.toContain("VITE_BRAPI");
});
