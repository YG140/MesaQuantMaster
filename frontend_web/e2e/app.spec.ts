import { expect, test } from "@playwright/test";

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
    await route.fulfill({ json: { patrimonio_total: "0", valor_investido: "0", lucro_prejuizo: "0", rentabilidade: "0", ativos: 0, operacoes: 0, caixa: "0", proventos: "0" } });
  });
  await page.route("**/portfolio", async (route) => {
    await route.fulfill({ json: { total_invested: "0", total_market_value: "0", total_profit: "0", profitability: "0", allocation: [], valuation_basis: null, positions: [] } });
  });
  await page.route("**/operations", async (route) => {
    await route.fulfill({ json: [] });
  });

  await page.goto("/carteira");
  await expect(page.getByRole("heading", { name: "Mesa Quant Master" })).toBeVisible();
  await page.getByLabel("E-mail").fill("ana@example.com");
  await page.getByLabel("Senha").fill("password123");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByText("Inicio")).toBeVisible();
  await page.getByRole("link", { name: "Minha carteira" }).click();
  await expect(page.getByRole("heading", { name: "Minha carteira" })).toBeVisible();
  await expect(page.getByText("Sua carteira ainda esta vazia.")).toBeVisible();
  await page.getByRole("button", { name: "Sair" }).click();
  await expect(page.getByRole("heading", { name: "Mesa Quant Master" })).toBeVisible();
});
