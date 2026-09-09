import { expect, test } from "@playwright/test";

const policy = {
  id: "policy-1", user_id: "user-1", name: "Estratégia determinística",
  objective: "crescimento patrimonial", risk_profile: "moderado",
  investment_horizon: "longo prazo", monthly_contribution: "900",
  liquidity_need: "média", income_need: false, emergency_reserve_months: 6,
  maximum_weight_per_asset: "60", maximum_weight_per_sector: "70",
  maximum_weight_per_issuer: "60", rebalance_tolerance: "5",
  allocations: [{ id: "allocation-1", asset_class: "Ações", target_percentage: "100", minimum_percentage: "80", maximum_percentage: "100", enabled: true }],
  created_at: "2026-08-30T12:00:00Z", updated_at: "2026-08-30T12:00:00Z",
};

const response = {
  class_allocations: [{ asset_class: "Ações", percentage: "100", amount: "10000", explanation: "Conforme a política confirmada." }],
  selections: [{ asset_class: "Ações", message: "Classe compatível com a política.", data_status: "available" }],
  assets: [
    {
      symbol: "PETR4", name: "Petrobras PN", asset_class: "Ações", sector: "Energia", issuer: "B3:PETR4",
      recommended_percentage: "50", recommended_amount: "833.99", score: "82", confidence: "medium",
      reasons: ["Preço atualizado e fundamentos disponíveis."], risks: ["Oscilação de mercado."],
      missing_data: ["Cobertura de analistas ausente."], reference_price: "37.42",
      executable_quantity: "22", executable_amount: "823.24", effective_percentage: "49.36",
      target_gap: "10.75", execution_impediments: [], trading_symbol: "PETR4F",
      economic_identity: "PETR4", market_segment: "fractional", quantity_step: "1",
      indicators_used: [
        { key: "current_price", label: "Preço atual", value: "37.42", unit: "currency", status: "available", unavailable_reason: null, source: "BRAPI", source_type: "provider", reference_date: "2026-08-30T12:00:00Z", valid_until: "2026-08-31T12:00:00Z", freshness_status: "current" },
        { key: "dividend_yield", label: "Dividend Yield", value: "10.24", unit: "percentage", status: "available", unavailable_reason: null, source: "CVM", source_type: "official", reference_date: "2026-06-30T12:00:00Z", valid_until: "2026-09-30T12:00:00Z", freshness_status: "current" },
      ],
    },
    {
      symbol: "VALE3", name: "Vale ON", asset_class: "Ações", sector: "Mineração", issuer: "B3:VALE3",
      recommended_percentage: "50", recommended_amount: "5000", score: "76", confidence: "high",
      reasons: ["Cobertura obrigatória e indicadores atuais disponíveis."], risks: ["Exposição a commodities."],
      missing_data: [], reference_price: "64.92", executable_quantity: "77", executable_amount: "4998.84",
      effective_percentage: "49.99", target_gap: "1.16", execution_impediments: [], trading_symbol: "VALE3F",
      economic_identity: "VALE3", market_segment: "fractional", quantity_step: "1",
      indicators_used: [{ key: "price_earnings", label: "P/L", value: "6.7", unit: "ratio", status: "available", unavailable_reason: null, source: "BRAPI", source_type: "provider", reference_date: "2026-08-30T12:00:00Z", valid_until: "2026-08-31T12:00:00Z", freshness_status: "current" }],
    },
  ],
  exclusions: [], total_allocated_percentage: "100", total_allocated_amount: "5833.99",
  unallocated_amount: "4166.01", confidence: "medium", status: "available", missing_data: [],
  strategy_summary: "Carteira educacional alinhada à política confirmada.",
  diagnosis: { phase: "accumulation", estimated_monthly_capacity: "900", reserve_months_covered: "6", reserve_target: "18000", debt_alerts: [], liquidity_assessment: "adequate", missing_data: [], priority_actions: ["Manter aportes."], confidence: "high" },
  contribution_plan: [],
  projections: [{ name: "central", annual_appreciation_rate: "5", annual_income_rate: "3", total_contributed: "10000", projected_wealth: "15000", estimated_appreciation: "4000", estimated_income: "1000", estimated_periodic_income: "80", real_projected_wealth: "14000", projected_without_reinvestment: "14500" }],
  freedom_goal: { desired_monthly_income: "5000", required_wealth: "1500000", current_wealth: "10000", gap: "1490000", achieved_percentage: "0.67", estimated_years: null, withdrawal_rate: "4", safety_margin: "20", risks: [], improvement_actions: ["Aportar com regularidade."], confidence: "medium" },
  disclaimer: "Simulação educacional, não constitui ordem de compra e não garante retorno.", generated_at: "2026-08-30T12:00:00Z",
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("mesa_quant_session", "planejar-visual-token"));
  await page.route("**/users/me", route => route.fulfill({ json: { id: "user-1", name: "Yury Gabriel", email: "yury@example.com", is_active: true, is_superuser: false, created_at: "2026-07-15T00:00:00Z" } }));
  await page.route("**/investor-profile/status", route => route.fulfill({ json: { status: "complete", version: 1, last_reviewed_at: null, confirmed_at: "2026-08-30T12:00:00Z", updated_at: "2026-08-30T12:00:00Z" } }));
  await page.route("**/intelligence/policy", route => route.fulfill({ json: policy }));
  await page.route("**/intelligence/build-portfolio", route => route.fulfill({ json: response }));
  await page.emulateMedia({ reducedMotion: "reduce" });
});

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`captura Planejar quantidades ${viewport.name}`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/planejar?secao=montar-carteira", { waitUntil: "domcontentloaded", timeout: 120_000 });
    await expect(page.getByRole("heading", { name: "Monte uma carteira para o seu momento" })).toBeVisible();
    await page.getByRole("button", { name: "Montar minha carteira" }).click();
    const result = page.getByRole("heading", { name: "Sua carteira recomendada" });
    await expect(result).toBeVisible();
    await result.scrollIntoViewIfNeeded();
    await expect(page.getByText("22 unidades")).toBeVisible();
    await expect(page.getByText("Mercado fracionário").first()).toBeVisible();
    await expect(page.getByText("R$ 10,75 não alocados neste ativo")).toBeVisible();
    await page.locator(".recommended-asset").first().scrollIntoViewIfNeeded();
    await expect(page.locator("body")).not.toContainText("undefined");
    await expect(page.locator("body")).not.toContainText("NaN");
    const screenshot = await page.screenshot({ path: `test-results/planejar-quantidades-${viewport.name}.png`, fullPage: false });
    expect(screenshot.length).toBeGreaterThan(0);
    expect(page.viewportSize()).toEqual({ width: viewport.width, height: viewport.height });
  });
}

test("detalhes e procedência permanecem dentro da viewport mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/planejar?secao=montar-carteira", { waitUntil: "domcontentloaded", timeout: 120_000 });
  await page.getByRole("button", { name: "Montar minha carteira" }).click();

  const asset = page.locator(".recommended-asset").first();
  await asset.locator("details.asset-details > summary").click();
  await asset.locator("details.indicator-provenance > summary").click();

  const rootGeometry = await page.locator("html").evaluate((root) => ({
    clientWidth: root.clientWidth,
    scrollWidth: root.scrollWidth,
  }));
  const cellBounds = await page.locator(
    ".indicator-table td:visible, .indicator-provenance td:visible",
  ).evaluateAll((cells) => cells.map((cell) => cell.getBoundingClientRect().toJSON()));
  const tolerance = 1;
  const outsideViewport = cellBounds.filter((bounds) => (
    bounds.left < -tolerance || bounds.right > rootGeometry.clientWidth + tolerance
  )).length;

  expect(rootGeometry.scrollWidth).toBeLessThanOrEqual(rootGeometry.clientWidth);
  expect(outsideViewport).toBe(0);
});
