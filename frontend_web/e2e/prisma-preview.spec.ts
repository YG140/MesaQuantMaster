import { expect, test } from "@playwright/test";

const dashboard = {
  patrimonio_total: "1245890.32",
  valor_investido: "1102340.00",
  lucro_prejuizo: "143550.32",
  rentabilidade: "12.34",
  ativos: 3,
  operacoes: 8,
  market_data_status: "live",
  quote_updated_at: "2026-08-21T10:32:00-03:00",
  unpriced_symbols: [],
};

const portfolio = {
  total_invested: "1102340.00",
  total_market_value: "1245890.32",
  total_profit: "143550.32",
  profitability: "12.34",
  allocation: [
    { ticker: "Renda variável", allocation: "46.7" },
    { ticker: "Fundos imobiliários", allocation: "32.5" },
    { ticker: "Renda fixa", allocation: "20.8" },
  ],
  market_data_status: "live",
  quote_updated_at: "2026-08-21T10:32:00-03:00",
  unpriced_symbols: [],
  positions: [
    { asset_id: "1", ticker: "PETR4", asset_name: "Petrobras PN", quantity: "2500", average_price: "36.87", invested_amount: "92175", current_price: "37.42", market_value: "93550", unrealized_profit: "1375", unrealized_profit_percent: "1.49", allocation: "46.7", weight: "46.7", valuation_basis: "market_value" },
    { asset_id: "2", ticker: "HGLG11", asset_name: "CSHG Logística FII", quantity: "1000", average_price: "156.20", invested_amount: "156200", current_price: "162.48", market_value: "162480", unrealized_profit: "6280", unrealized_profit_percent: "4.02", allocation: "32.5", weight: "32.5", valuation_basis: "market_value" },
    { asset_id: "3", ticker: "Tesouro Selic", asset_name: "Tesouro Selic 2027", quantity: "1000", average_price: "130", invested_amount: "130000", current_price: "137.98", market_value: "137980", unrealized_profit: "7980", unrealized_profit_percent: "6.14", allocation: "20.8", weight: "20.8", valuation_basis: "market_value" },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("mesa_quant_session", "visual-token"));
  await page.route("**/users/me", route => route.fulfill({ json: { id: "user-1", name: "Yury Gabriel", email: "yury@example.com", is_active: true, is_superuser: false, created_at: "2026-07-15T00:00:00" } }));
  await page.route("**/investor-profile/status", route => route.fulfill({ json: { status: "complete", version: 1, last_reviewed_at: null, confirmed_at: "2026-07-16T18:30:00Z", updated_at: "2026-07-16T18:30:00Z" } }));
  await page.route("**/dashboard", route => route.fulfill({ json: dashboard }));
  await page.route("**/portfolio", route => route.fulfill({ json: portfolio }));
  await page.emulateMedia({ reducedMotion: "reduce" });
});

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`captura Quantum Prism ${viewport.name}`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/prisma-preview", { waitUntil: "domcontentloaded", timeout: 120_000 });
    await expect(page.getByRole("heading", { name: "O que você quer fazer hoje?" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByLabel("Avatar do usuário autenticado: YG")).toHaveText("YG");
    await expect(page.locator(".qp-topbar")).not.toContainText("Dados atualizados");
    const titleBox = await page.locator(".qp-topbar h1").boundingBox();
    const avatarBox = await page.locator(".qp-user-avatar").boundingBox();
    expect(titleBox).not.toBeNull();
    expect(avatarBox).not.toBeNull();
    const headerElementsOverlap = titleBox!.x < avatarBox!.x + avatarBox!.width && titleBox!.x + titleBox!.width > avatarBox!.x && titleBox!.y < avatarBox!.y + avatarBox!.height && titleBox!.y + titleBox!.height > avatarBox!.y;
    expect(headerElementsOverlap).toBe(false);
    expect(avatarBox!.x + avatarBox!.width).toBeLessThanOrEqual(viewport.width);
    await expect(page.getByText("Mesa IA — pausada")).toBeVisible();
    await expect(page.getByLabel("Mesa IA pausada")).toHaveAttribute("aria-disabled", "true");
    if (viewport.name === "mobile") {
      for (const label of ["Início", "Carteira", "Mesa IA", "Mercado", "Planejar"]) {
        await expect(page.locator(".qp-mobile-nav").getByText(label, { exact: true })).toBeVisible();
      }
      const navigationBox = await page.locator(".qp-mobile-nav").boundingBox();
      const allocationBox = await page.getByRole("heading", { name: "Composição da carteira" }).boundingBox();
      expect(navigationBox).not.toBeNull();
      expect(allocationBox).not.toBeNull();
      const contentIsClear = allocationBox!.y >= viewport.height || allocationBox!.y + allocationBox!.height <= navigationBox!.y;
      expect(contentIsClear).toBe(true);
    }
    await expect(page.locator("body")).not.toContainText("undefined");
    await expect(page.locator("body")).not.toContainText("NaN");
    const screenshot = await page.screenshot({ path: `test-results/prisma-preview-${viewport.name}.png`, fullPage: false });
    expect(screenshot.length).toBeGreaterThan(0);
    expect(page.viewportSize()).toEqual({ width: viewport.width, height: viewport.height });
  });
}
