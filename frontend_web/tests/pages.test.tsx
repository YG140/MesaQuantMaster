import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRouter } from "../src/app/router";
import { renderWithProviders } from "./render";
import { server } from "./testServer";
import { formatMoney, formatPercent } from "../src/utils/formatters";

const api = "http://127.0.0.1:8000";

async function login(path = "/") {
  const user = userEvent.setup();
  sessionStorage.setItem("mesa_quant_session", "test-token");
  renderWithProviders(<AppRouter />, path);
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument(), { timeout: 10_000 });
  return user;
}

function mockEmptyPortfolio() {
  server.use(
    http.get(`${api}/dashboard`, () =>
      HttpResponse.json({
        patrimonio_total: "0",
        valor_investido: "0",
        lucro_prejuizo: "0",
        rentabilidade: "0",
        ativos: 0,
        operacoes: 0,
        caixa: "0",
        proventos: "0",
        market_data_status: "unavailable",
        quote_updated_at: null,
        unpriced_symbols: [],
      }),
    ),
    http.get(`${api}/portfolio`, () =>
      HttpResponse.json({
        total_invested: "0",
        total_market_value: "0",
        total_profit: "0",
        profitability: "0",
        allocation: [],
        valuation_basis: null,
        market_data_status: "unavailable",
        quote_updated_at: null,
        unpriced_symbols: [],
        positions: [],
      }),
    ),
  );
}

describe("paginas autenticadas", () => {
  it("mostra menu correto e nao mostra nomes incorretos", async () => {
    await login();
    expect(screen.getByText("Minha carteira")).toBeInTheDocument();
    expect(screen.getByText("Adicionar investimento")).toBeInTheDocument();
    expect(screen.queryByText("Operas")).not.toBeInTheDocument();
    expect(screen.queryByText("Backtesting")).not.toBeInTheDocument();
  });

  it("mantem a rota / protegida e renderiza dashboard com dados", async () => {
    await login("/");
    expect(await screen.findByText("Patrimonio")).toBeInTheDocument();
    expect(screen.getByText("Resumo de risco")).toBeInTheDocument();
    expect(screen.getByText(/Cotacoes atualizadas em/)).toBeInTheDocument();
    expect(screen.getAllByText("R$ 521,00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });

  it("mostra estado vazio para usuario novo", async () => {
    mockEmptyPortfolio();
    await login();

    expect(await screen.findByText("Sua carteira ainda esta vazia.")).toBeInTheDocument();
    expect(screen.getAllByText("Adicionar investimento").length).toBeGreaterThan(0);
    expect(screen.getByText("Importar carteira existente")).toBeInTheDocument();
    expect(screen.queryByLabelText("Grafico de alocacao")).not.toBeInTheDocument();
    expect(screen.queryByText("Patrimonio")).not.toBeInTheDocument();
  });

  it("renderiza metricas com valores numericos recebidos como string", async () => {
    await login();

    expect(screen.getAllByText("R$ 521,00").length).toBeGreaterThan(0);
    expect(screen.getByText("0,00%")).toBeInTheDocument();
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });

  it("lida com campos opcionais nulos sem vazar NaN ou undefined", async () => {
    server.use(
      http.get(`${api}/portfolio`, () =>
        HttpResponse.json({
          total_invested: null,
          total_market_value: null,
          total_profit: null,
          profitability: null,
          allocation: [{ ticker: "PETR4", allocation: null }],
          valuation_basis: null,
          market_data_status: "unavailable",
          quote_updated_at: null,
          unpriced_symbols: ["PETR4"],
          positions: [
            {
              asset_id: "asset-1",
              ticker: "PETR4",
              asset_name: "Petrobras PN",
              quantity: "10",
              average_price: "37.10",
              invested_amount: "371.00",
              current_price: null,
              market_value: null,
              unrealized_profit: null,
              unrealized_profit_percent: null,
              allocation: null,
              weight: null,
              valuation_basis: null,
              valuation_status: "unpriced",
              quote_updated_at: null,
            },
          ],
        }),
      ),
    );

    await login();
    expect(await screen.findByText("Ainda nao ha informacao de alocacao para exibir.")).toBeInTheDocument();
    expect(screen.getAllByText("Nao informado").length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });

  it("nao renderiza grafico com allocation vazia", async () => {
    server.use(
      http.get(`${api}/portfolio`, () =>
        HttpResponse.json({
          total_invested: "371.00",
          total_market_value: "384.20",
          total_profit: "13.20",
          profitability: "3.55",
          allocation: [],
          valuation_basis: "invested_amount",
          market_data_status: "live",
          quote_updated_at: "2026-07-16T18:30:00Z",
          unpriced_symbols: [],
          positions: [
            {
              asset_id: "asset-1",
              ticker: "PETR4",
              asset_name: "Petrobras PN",
              quantity: "10",
              average_price: "37.10",
              invested_amount: "371.00",
              current_price: "38.42",
              market_value: "384.20",
              unrealized_profit: "13.20",
              unrealized_profit_percent: "3.55",
              allocation: null,
              weight: null,
              valuation_basis: "invested_amount",
              valuation_status: "live",
              quote_updated_at: "2026-07-16T18:30:00Z",
            },
          ],
        }),
      ),
    );

    await login();
    expect(await screen.findByText("Ainda nao ha informacao de alocacao para exibir.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Grafico de alocacao")).not.toBeInTheDocument();
  });

  it("nao renderiza grafico com dados invalidos", async () => {
    server.use(
      http.get(`${api}/portfolio`, () =>
        HttpResponse.json({
          total_invested: "371.00",
          total_market_value: "384.20",
          total_profit: "13.20",
          profitability: "3.55",
          allocation: [{ ticker: "PETR4", allocation: "valor-invalido" }, { ticker: "", allocation: "10" }],
          valuation_basis: "invested_amount",
          market_data_status: "live",
          quote_updated_at: "2026-07-16T18:30:00Z",
          unpriced_symbols: [],
          positions: [
            {
              asset_id: "asset-1",
              ticker: "PETR4",
              asset_name: "Petrobras PN",
              quantity: "10",
              average_price: "37.10",
              invested_amount: "371.00",
              current_price: "38.42",
              market_value: "384.20",
              unrealized_profit: "13.20",
              unrealized_profit_percent: "3.55",
              allocation: "valor-invalido",
              weight: null,
              valuation_basis: "invested_amount",
              valuation_status: "live",
              quote_updated_at: "2026-07-16T18:30:00Z",
            },
          ],
        }),
      ),
    );

    await login();
    expect(await screen.findByText("Ainda nao ha informacao de alocacao para exibir.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Grafico de alocacao")).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });

  it("mostra erro 500 com botao tentar novamente", async () => {
    server.use(http.get(`${api}/dashboard`, () => HttpResponse.json({ detail: "Erro interno" }, { status: 500 })));
    await login();

    expect(await screen.findByRole("alert")).toHaveTextContent("Nao foi possivel carregar o inicio");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("mostra erro quando backend esta indisponivel", async () => {
    server.use(http.get(`${api}/dashboard`, () => HttpResponse.error()));
    await login();

    expect(await screen.findByRole("alert")).toHaveTextContent("Nao foi possivel carregar o inicio");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("botao Tentar novamente recarrega o dashboard", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    server.use(
      http.get(`${api}/dashboard`, () => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json({ detail: "Erro temporario" }, { status: 500 });
        }
        return HttpResponse.json({
          patrimonio_total: "521.00",
          valor_investido: "521.00",
          lucro_prejuizo: "0",
          rentabilidade: "0",
          ativos: 2,
          operacoes: 2,
          caixa: "0",
          proventos: "0",
          market_data_status: "live",
          quote_updated_at: "2026-07-16T18:30:00Z",
          unpriced_symbols: [],
        });
      }),
    );
    sessionStorage.setItem("mesa_quant_session", "test-token");
    renderWithProviders(<AppRouter />, "/");

    await user.click(await screen.findByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("Patrimonio")).toBeInTheDocument();
  });

  it("renderiza carteira e historico", async () => {
    const user = await login();
    await user.click(screen.getByText("Minha carteira"));
    expect(await screen.findByText("Petrobras PN")).toBeInTheDocument();
    expect(screen.getByText("Historico de movimentacoes")).toBeInTheDocument();
  });

  it("pesquisa PETR4 e Petrobras, separa preco atual de preco de compra e salva", async () => {
    const user = await login();
    await user.click(screen.getByText("Adicionar investimento"));
    await user.type(await screen.findByLabelText("Ativo ou empresa"), "PETR4");
    await user.click(await screen.findByText("PETR4"));
    expect(screen.getByText("Ultima cotacao disponivel")).toBeInTheDocument();
    expect(screen.getByText("Variacao")).toBeInTheDocument();
    expect(screen.queryByText("STOCK")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Preco de compra")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Corretora"), "brokerage-1");
    await user.type(screen.getByLabelText("Quantidade"), "10");
    await user.type(screen.getByLabelText("Preco de compra"), "37.10");
    await user.click(screen.getByRole("button", { name: "Salvar investimento" }));
    expect(await screen.findByText("Investimento salvo com sucesso.")).toBeInTheDocument();
  });

  it("permite cadastrar corretora dentro do formulario e seleciona automaticamente", async () => {
    server.use(http.get(`${api}/brokerages`, () => HttpResponse.json([])));
    const user = await login();
    await user.click(screen.getByText("Adicionar investimento"));

    expect(await screen.findByText("Voce ainda nao cadastrou uma corretora.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "+ Cadastrar corretora" }));
    await user.click(screen.getByRole("button", { name: "Salvar corretora" }));
    expect(await screen.findByText("Informe o nome da corretora.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Nome da corretora"), "Nubank Investimentos");
    await user.click(screen.getByRole("button", { name: "Salvar corretora" }));

    const brokerage = await screen.findByLabelText("Corretora");
    expect(brokerage).toHaveValue("brokerage-new");
    expect(screen.getByRole("option", { name: "Nubank Investimentos" })).toBeInTheDocument();
  });

  it("mostra erro de corretora duplicada sem perder o formulario", async () => {
    const user = await login();
    await user.click(screen.getByText("Adicionar investimento"));
    await user.click(screen.getByRole("button", { name: "+ Cadastrar corretora" }));
    await user.type(screen.getByLabelText("Nome da corretora"), "XP");
    await user.click(screen.getByRole("button", { name: "Salvar corretora" }));

    expect(await screen.findByText("Corretora ja cadastrada.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome da corretora")).toHaveValue("XP");
  });

  it("mostra dashboard com dados parciais e botao Atualizar cotacoes", async () => {
    server.use(
      http.get(`${api}/dashboard`, () =>
        HttpResponse.json({
          patrimonio_total: "571.00",
          valor_investido: "521.00",
          lucro_prejuizo: "13.20",
          rentabilidade: "3.55",
          ativos: 2,
          operacoes: 2,
          caixa: "0",
          proventos: "0",
          market_data_status: "partial",
          quote_updated_at: "2026-07-16T18:30:00Z",
          unpriced_symbols: ["VALE3"],
        }),
      ),
      http.get(`${api}/portfolio`, () =>
        HttpResponse.json({
          total_invested: "521.00",
          total_market_value: "384.20",
          total_profit: "13.20",
          profitability: "3.55",
          allocation: [{ ticker: "PETR4", allocation: "71.05" }],
          valuation_basis: "mixed",
          market_data_status: "partial",
          quote_updated_at: "2026-07-16T18:30:00Z",
          unpriced_symbols: ["VALE3"],
          positions: [
            {
              asset_id: "asset-1",
              ticker: "PETR4",
              asset_name: "Petrobras PN",
              quantity: "10",
              average_price: "37.10",
              invested_amount: "371.00",
              current_price: "38.42",
              market_value: "384.20",
              unrealized_profit: "13.20",
              unrealized_profit_percent: "3.55",
              allocation: "71.05",
              weight: "71.05",
              valuation_basis: "mixed",
              valuation_status: "live",
              quote_updated_at: "2026-07-16T18:30:00Z",
            },
          ],
        }),
      ),
    );

    await login();

    expect(await screen.findByText(/Alguns ativos estao sem cotacao atual/)).toBeInTheDocument();
    expect(screen.getByText(/VALE3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Atualizar cotacoes" })).toBeInTheDocument();
  });

  it("mostra limite de consultas ao mercado no autocomplete", async () => {
    server.use(
      http.get(`${api}/market/search`, () =>
        HttpResponse.json(
          { detail: "Limite de consultas ao mercado atingido. Tente novamente mais tarde." },
          { status: 429 },
        ),
      ),
    );
    const user = await login();
    await user.click(screen.getByText("Adicionar investimento"));
    await user.type(await screen.findByLabelText("Ativo ou empresa"), "PETR4");

    expect(await screen.findByText(/Limite de consultas ao mercado atingido/)).toBeInTheDocument();
  });

  it("importa carteira com revisao de linhas", async () => {
    const user = await login();
    await user.click(screen.getByText("Importar carteira"));
    await user.selectOptions(await screen.findByLabelText("Corretora"), "brokerage-1");
    await user.type(screen.getByLabelText("Ativo"), "PETR4");
    await user.type(screen.getByLabelText("Quantidade atual"), "10");
    await user.type(screen.getByLabelText("Preco medio"), "37.10");
    expect(screen.getByText(/1 linhas validas/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar importacao" }));
    expect(await screen.findByText("Carteira importada com sucesso.")).toBeInTheDocument();
  });

  it("formata valores monetarios e percentuais", () => {
    expect(formatMoney("1234.5")).toBe("R$ 1.234,50");
    expect(formatPercent("12.345")).toBe("12,35%");
  });

  it("atualizar / nao causa tela branca no roteador", async () => {
    sessionStorage.setItem("mesa_quant_session", "test-token");
    renderWithProviders(<AppRouter />, "/");
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument(), { timeout: 10_000 });
    expect(await screen.findByText("Patrimonio")).toBeInTheDocument();
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });
});
