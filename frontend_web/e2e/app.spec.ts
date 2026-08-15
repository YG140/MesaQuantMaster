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
  await page.route("**/assets", async (route) => {
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
  await page.route("**/intelligence/portfolio/recommendations", async (route) => {
    await route.fulfill({
      json: {
        snapshots: [
          {
            asset_id: "asset-1",
            symbol: "PETR4",
            name: "Petrobras PN",
            asset_class: "stock",
            current_price: "38.42",
            currency: "BRL",
            market_updated_at: "2026-07-16T18:30:00Z",
            indicators: [
              { key: "current_price", label: "Pre\u00e7o atual", value: "38.42", display_value: "BRL 38.42", unit: "currency", status: "available", source: "BRAPI", reference_date: "2026-07-16T18:30:00Z", collected_at: "2026-07-16T18:30:00Z", confidence: "medium", period: "\u00faltima cota\u00e7\u00e3o", unavailable_reason: null },
              { key: "price_earnings", label: "P/L", value: null, display_value: null, unit: "ratio", status: "unavailable", source: "BRAPI", reference_date: "2026-07-16T18:30:00Z", collected_at: "2026-07-16T18:30:00Z", confidence: "insufficient", period: null, unavailable_reason: "O provedor atual n\u00e3o entrega este indicador para o ativo." },
            ],
            quality_score: null,
            valuation_score: null,
            income_score: null,
            growth_score: null,
            risk_score: null,
            liquidity_score: null,
            strategy_fit_score: "25",
            overall_score: null,
            recommendation: "insufficient_data",
            valuation_status: "insufficient_data",
            valuation: { status: "insufficient_data", methods: [], used_indicators: [], missing_indicators: ["P/L"], historical_comparison: null, peer_comparison: null, estimated_range_low: null, estimated_range_high: null, confidence: "insufficient", data_date: null },
            confidence: "insufficient",
            coverage_percentage: "25",
            available_indicators_count: 1,
            missing_indicators_count: 1,
            stale_indicators_count: 0,
            positive_reasons: ["Cota\u00e7\u00e3o real dispon\u00edvel no provedor de mercado."],
            warning_reasons: ["N\u00e3o existem dados suficientes para uma an\u00e1lise confi\u00e1vel deste investimento."],
            missing_data: ["P/L"],
            calculated_at: "2026-07-16T18:30:00Z",
          },
        ],
        errors: [],
        provider_calls: 1,
        calculated_at: "2026-07-16T18:30:00Z",
      },
    });
  });
  await page.route("**/intelligence/macro", async (route) => {
    await route.fulfill({
      json: [
        {
          key: "selic",
          label: "Selic",
          value: null,
          period: null,
          source: "Provedor macroecon\u00f4mico ainda n\u00e3o integrado",
          updated_at: null,
          frequency: "mensal",
          history_available: false,
          state: "unavailable",
        },
        {
          key: "ipca",
          label: "IPCA",
          value: null,
          period: null,
          source: "Provedor macroecon\u00f4mico ainda n\u00e3o integrado",
          updated_at: null,
          frequency: "mensal",
          history_available: false,
          state: "unavailable",
        },
      ],
    });
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
        assets: [],
        exclusions: [],
        total_allocated_percentage: "0",
        total_allocated_amount: "0",
        unallocated_amount: "20000",
        confidence: "insufficient",
        status: "unavailable",
        diagnosis: {
          phase: "accumulation", estimated_monthly_capacity: "2500", reserve_months_covered: "6",
          reserve_target: "21000", debt_alerts: [], liquidity_assessment: "alta", missing_data: [],
          priority_actions: ["Manter aportes periódicos."], confidence: "high",
        },
        contribution_plan: [],
        projections: [{ name: "central", annual_appreciation_rate: "5", annual_income_rate: "3", total_contributed: "20000", projected_wealth: "30000", estimated_appreciation: "7000", estimated_income: "3000", estimated_periodic_income: "75", real_projected_wealth: "25000", projected_without_reinvestment: "27000" }],
        freedom_goal: {
          desired_monthly_income: "5000", required_wealth: "1800000", current_wealth: "20000",
          gap: "1780000", achieved_percentage: "1.11", estimated_years: null,
          withdrawal_rate: "4", safety_margin: "20", risks: ["Retornos são hipóteses."],
          improvement_actions: ["Manter aportes."], confidence: "medium",
        },
        missing_data: ["Cobertura insuficiente."],
        strategy_summary: "Estratégia educacional simulada.",
        disclaimer: "Simulação educacional, não constitui ordem de compra e não garante retorno.",
        generated_at: "2026-07-16T18:30:00Z",
      },
    });
  });

  await page.goto("/carteira");
  await expect(page.getByRole("heading", { name: "Mesa Quant Master" })).toBeVisible();
  await page.getByLabel("E-mail").fill("ana@example.com");
  await page.getByLabel("Senha", { exact: true }).fill("password123");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { name: /In.cio/ })).toBeVisible();
  await page.getByTestId("desktop-primary-navigation").getByRole("link", { name: "Carteira" }).click();
  await expect(page.getByRole("heading", { name: "Minha carteira" })).toBeVisible();
  await expect(page.getByText(/Sua carteira ainda.*vazia/)).toBeVisible();
  await page.goto("/planejar");
  await expect(page.getByRole("heading", { name: /Intelig.ncia de Carteira/ })).toBeVisible();
  await page.getByRole("tab", { name: "Futuro financeiro" }).click();
  await expect(page.getByText(/Total da aloca..o: 100,00%/)).toBeVisible();
  await page.getByRole("button", { name: /Salvar estrat.gia/ }).click();
  await expect(page.getByText(/Estrat.gia salva com sucesso/)).toBeVisible();
  await page.getByRole("tab", { name: "Diagnóstico" }).click();
  await page.locator(".intelligence-sections summary").filter({ hasText: /Diagn.stico/ }).click();
  await expect(page.getByText(/Pontua..o da carteira/)).toBeVisible();
  await page.locator(".intelligence-sections summary").filter({ hasText: "Rebalanceamento" }).click();
  await expect(page.getByText("R$ 900,00")).toBeVisible();
  await page.locator(".intelligence-sections summary").filter({ hasText: /Recomenda..es/ }).click();
  await expect(page.getByText(/PETR4 - Dados insuficientes/)).toBeVisible();
  await expect(page.getByText(/Indicadores por categoria/)).toBeVisible();
  await expect(page.getByText(/P\/L: O provedor atual/)).toBeVisible();
  await expect(page.locator("details.details-panel").first()).toBeVisible();
  await page.getByRole("tab", { name: "Montar carteira" }).click();
  await page.getByLabel(/Valor dispon.*investir/).fill("20000");
  await page.getByRole("button", { name: /Montar minha carteira/ }).click();
  await expect(page.getByRole("heading", { name: /Sua carteira recomendada/ })).toBeVisible();
  await page.getByText(/Distribui..o por classe/).click();
  await expect(page.getByText("R$ 12.000,00")).toBeVisible();
  await expect(page.getByText("R$ 8.000,00")).toBeVisible();
  await page.getByTestId("desktop-primary-navigation").getByRole("link", { name: "Mercado" }).click();
  await expect(page.getByText(/Grupos de an.lise/)).toBeVisible();
  await expect(page.getByText(/Tracking error: diferen.a/)).toBeVisible();
  await expect(page.getByRole("heading", { name: /Cen.rio econ.mico/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Mercado e ativos", exact: true })).toBeVisible();
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
