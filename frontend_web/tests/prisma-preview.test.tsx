import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppRouter } from "../src/app/router";
import { renderWithProviders } from "./render";
import { server } from "./testServer";

const api = "http://127.0.0.1:8000";
async function renderPreview() {
  sessionStorage.setItem("mesa_quant_session", "test-token");
  renderWithProviders(<AppRouter />, "/prisma-preview");
  await waitFor(() => expect(screen.queryByText("Validando sessao...")).not.toBeInTheDocument());
}

describe("Quantum Prism preview", () => {
  it("usa dashboard e portfolio e mantém Mesa IA pausada", async () => {
    let aiCalls = 0;
    server.use(
      http.get(`${api}/users/me`, () => HttpResponse.json({ id: "user-1", name: "  Yury   Gabriel  ", email: "yury@example.com", is_active: true, is_superuser: false, created_at: "2026-07-15T00:00:00" })),
      http.post(`${api}/ai-agent/chat`, () => { aiCalls += 1; return HttpResponse.json({}); }),
    );
    await renderPreview();
    expect(await screen.findByRole("heading", { name: "O que você quer fazer hoje?" }, { timeout: 10_000 })).toBeInTheDocument();
    expect(screen.getByLabelText("Avatar do usuário autenticado: YG")).toHaveTextContent("YG");
    expect(screen.queryByText("Dados atualizados")).not.toBeInTheDocument();
    expect(screen.getByText(/Confirmado em 16\/07\/2026/)).toBeInTheDocument();
    expect(screen.getAllByText("Mesa IA — pausada").length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: /Prisma patrimonial informativo/ })).toBeInTheDocument();
    expect(aiCalls).toBe(0);
  });

  it("usa uma inicial quando o usuário possui nome único", async () => {
    server.use(http.get(`${api}/users/me`, () => HttpResponse.json({ id: "user-1", name: " Yury ", email: "yury@example.com", is_active: true, is_superuser: false, created_at: "2026-07-15T00:00:00" })));
    await renderPreview();
    expect(await screen.findByLabelText("Avatar do usuário autenticado: Y")).toHaveTextContent("Y");
  });

  it("usa ícone neutro quando o nome está ausente", async () => {
    server.use(http.get(`${api}/users/me`, () => HttpResponse.json({ id: "user-1", name: "   ", email: "yury@example.com", is_active: true, is_superuser: false, created_at: "2026-07-15T00:00:00" })));
    await renderPreview();
    const avatar = await screen.findByLabelText("Avatar do usuário autenticado");
    expect(avatar).toHaveTextContent("");
    expect(avatar.querySelector("svg")).toBeInTheDocument();
  });

  it("trata carteira vazia sem apresentar patrimônio zero", async () => {
    server.use(
      http.get(`${api}/dashboard`, () => HttpResponse.json({ patrimonio_total: "0", market_data_status: "unavailable" })),
      http.get(`${api}/portfolio`, () => HttpResponse.json({ total_invested: "0", total_market_value: "0", total_profit: "0", profitability: "0", allocation: [], positions: [], market_data_status: "unavailable" })),
    );
    await renderPreview();
    expect(await screen.findByText("Carteira vazia")).toBeInTheDocument();
    expect(screen.getByText(/Nenhum valor foi interpretado como zero/)).toBeInTheDocument();
    expect(screen.queryByText("R$ 0,00")).not.toBeInTheDocument();
  });

  it("explicita concentração quando existe uma única posição", async () => {
    await renderPreview();
    expect(await screen.findByText("Concentração relevante")).toBeInTheDocument();
    expect(screen.getByText(/Uma única posição representa toda a carteira/)).toBeInTheDocument();
  });

  it("preserva dados parciais e cotações indisponíveis", async () => {
    server.use(
      http.get(`${api}/dashboard`, () => HttpResponse.json({ patrimonio_total: "521", valor_investido: "521", lucro_prejuizo: null, rentabilidade: null, market_data_status: "partial", quote_updated_at: null, unpriced_symbols: ["VALE3"] })),
      http.get(`${api}/portfolio`, () => HttpResponse.json({ total_invested: "521", total_market_value: "521", total_profit: null, profitability: null, allocation: [{ ticker: "PETR4", allocation: "71.05" }], market_data_status: "partial", quote_updated_at: null, unpriced_symbols: ["VALE3"], positions: [{ asset_id: "asset-1", ticker: "PETR4", asset_name: "Petrobras PN", quantity: "10", average_price: "37.10", invested_amount: "371", current_price: null, market_value: null, unrealized_profit: null, unrealized_profit_percent: null, allocation: "71.05", weight: "71.05", valuation_basis: "invested_amount" }] })),
    );
    await renderPreview();
    expect(await screen.findByText(/Sem cotação: VALE3/)).toBeInTheDocument();
    expect(screen.getAllByText(/informado/i).length).toBeGreaterThan(0);
  });

  it("mantém a composição quando somente um contrato falha", async () => {
    server.use(http.get(`${api}/dashboard`, () => HttpResponse.json({ detail: "temporariamente indisponível" }, { status: 503 })));
    await renderPreview();
    expect(await screen.findByText(/Parte dos dados está indisponível/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "O que você quer fazer hoje?" })).toBeInTheDocument();
  });

  it("mostra erro recuperável quando os dois contratos falham", async () => {
    server.use(http.get(`${api}/dashboard`, () => HttpResponse.json({ detail: "erro" }, { status: 503 })), http.get(`${api}/portfolio`, () => HttpResponse.json({ detail: "erro" }, { status: 503 })));
    await renderPreview();
    expect(await screen.findByRole("alert")).toHaveTextContent("A workstation não pôde ser carregada");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("não transforma posições indisponíveis em zero quando somente a carteira falha", async () => {
    server.use(http.get(`${api}/portfolio`, () => HttpResponse.json({ detail: "erro" }, { status: 503 })));
    await renderPreview();
    expect(await screen.findByText("Posições indisponíveis")).toBeInTheDocument();
    expect(screen.queryByText("0 posições consolidadas")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("expõe cinco destinos e navegação essencial acessível", async () => {
    await renderPreview();
    const navigation = await screen.findByRole("navigation", { name: "Destinos principais" });
    expect(navigation.children).toHaveLength(5);
    expect(document.querySelectorAll('nav[aria-label="Destinos principais"]')).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Ir para o conteúdo" })).toHaveAttribute("href", "#qp-main");
  });
});
