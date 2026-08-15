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
  it("edita a operação que forma uma posição sem editar o agregado", async () => {
    let patchBody: unknown;
    server.use(
      http.patch(`${api}/operations/:operationId`, async ({ request }) => {
        patchBody = await request.json();
        return HttpResponse.json({
          id: "op-1",
          asset_id: "asset-1",
          brokerage_id: "brokerage-1",
          operation_type: "BUY",
          operation_date: "2026-07-15",
          quantity: "12.50000000",
          unit_price: "37.10",
          fees: "1",
          taxes: "0",
          notes: null,
        });
      }),
    );
    const user = await login("/carteira");
    await user.click((await screen.findAllByText("Editar"))[0]);
    await user.click(await screen.findByRole("button", { name: /Compra em 2026-07-15/ }));
    const quantity = screen.getByLabelText("Quantidade");
    await user.clear(quantity);
    await user.type(quantity, "12.50000000");
    await user.click(screen.getByRole("button", { name: "Salvar alterações" }));

    await waitFor(() => expect(patchBody).toMatchObject({ quantity: "12.50000000" }));
    expect(await screen.findByText("Operação atualizada e posição recalculada.")).toBeInTheDocument();
  });

  it("confirma e exclui somente a posição da carteira", async () => {
    let deleteBody: unknown;
    server.use(
      http.delete(`${api}/portfolio/positions/:assetId`, async ({ request }) => {
        deleteBody = await request.json();
        return HttpResponse.json({
          asset_id: "asset-1",
          ticker: "PETR4",
          operations_deleted: 1,
          message: "Posição excluída da carteira.",
        });
      }),
    );
    const user = await login("/carteira");
    await user.click((await screen.findAllByText("Excluir da carteira"))[0]);

    expect(await screen.findByText(/O ativo global e os dados de mercado serão preservados/)).toBeInTheDocument();
    expect(screen.getByText("Operações afetadas")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Excluir da minha carteira" }));

    await waitFor(() => expect(deleteBody).toEqual({ ticker: "PETR4", expected_operations: 1 }));
    expect(await screen.findByText(/PETR4: 1 operação/)).toBeInTheDocument();
  });

  it("mostra menu correto e nao mostra nomes incorretos", async () => {
    await login();
    expect(screen.getByTestId("desktop-primary-navigation").children).toHaveLength(5);
    expect(screen.getByTestId("desktop-primary-navigation")).toHaveTextContent("Início");
    expect(screen.getByTestId("desktop-primary-navigation")).toHaveTextContent("Carteira");
    expect(screen.getByTestId("desktop-primary-navigation")).toHaveTextContent("Mesa IA");
    expect(screen.getByTestId("desktop-primary-navigation")).toHaveTextContent("Mercado");
    expect(screen.getByTestId("desktop-primary-navigation")).toHaveTextContent("Planejar");
    expect(screen.queryByText("Analises")).not.toBeInTheDocument();
    expect(screen.queryByText("Simulador historico")).not.toBeInTheDocument();
    expect(screen.queryByText("Operas")).not.toBeInTheDocument();
    expect(screen.queryByText("Backtesting")).not.toBeInTheDocument();
  });

  it("mantem a rota / protegida e renderiza dashboard com dados", async () => {
    await login("/");
    expect((await screen.findAllByText("Patrimônio")).length).toBeGreaterThan(0);
    expect(screen.getByText("Resumo de risco")).toBeInTheDocument();
    expect(screen.getByText(/Cotações atualizadas em/)).toBeInTheDocument();
    expect(screen.getAllByText("R$ 521,00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });

  it("mostra estado vazio para usuario novo", async () => {
    mockEmptyPortfolio();
    await login();

    expect(await screen.findByText("Sua carteira ainda está vazia.")).toBeInTheDocument();
    expect(screen.getAllByText("Adicionar investimento").length).toBeGreaterThan(0);
    expect(screen.getByText("Importar carteira existente")).toBeInTheDocument();
    expect(screen.queryByLabelText("Gráfico de alocação")).not.toBeInTheDocument();
    expect(screen.queryByText("Patrimônio")).not.toBeInTheDocument();
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
    expect(await screen.findByText("Ainda não há informação de alocação para exibir.")).toBeInTheDocument();
    expect(screen.getAllByText("Não informado").length).toBeGreaterThan(0);
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
    expect(await screen.findByText("Ainda não há informação de alocação para exibir.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Gráfico de alocação")).not.toBeInTheDocument();
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
    expect(await screen.findByText("Ainda não há informação de alocação para exibir.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Gráfico de alocação")).not.toBeInTheDocument();
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });

  it("mostra erro 500 com botao tentar novamente", async () => {
    server.use(http.get(`${api}/dashboard`, () => HttpResponse.json({ detail: "Erro interno" }, { status: 500 })));
    await login();

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar o início");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("mostra erro quando backend esta indisponivel", async () => {
    server.use(http.get(`${api}/dashboard`, () => HttpResponse.error()));
    await login();

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar o início");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  });

  it("botao Tentar novamente recarrega o dashboard", async () => {
    const user = userEvent.setup();
    let shouldFail = true;
    server.use(
      http.get(`${api}/dashboard`, () => {
        if (shouldFail) {
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

    const retryButton = await screen.findByRole("button", { name: "Tentar novamente" });
    shouldFail = false;
    await user.click(retryButton);
    expect((await screen.findAllByText("Patrimônio")).length).toBeGreaterThan(0);
  });

  it("renderiza carteira e historico", async () => {
    await login("/carteira");
    expect((await screen.findAllByText("Petrobras PN")).length).toBeGreaterThan(0);
    expect(screen.getByText("Histórico de movimentações")).toBeInTheDocument();
  });

  it("pesquisa PETR4 e Petrobras, separa preco atual de preco de compra e salva", async () => {
    const user = await login("/investimentos/novo");
    await user.type(await screen.findByLabelText("Ativo ou empresa"), "PETR4");
    await user.click(await screen.findByText("PETR4"));
    expect(screen.getByText("Última cotação disponível")).toBeInTheDocument();
    expect(screen.getByText("Variação")).toBeInTheDocument();
    expect(screen.queryByText("STOCK")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Preço de compra")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Corretora"), "brokerage-1");
    await user.type(screen.getByLabelText("Quantidade"), "10");
    await user.type(screen.getByLabelText("Preço de compra"), "37.10");
    await user.click(screen.getByRole("button", { name: "Salvar investimento" }));
    expect(await screen.findByText("Investimento salvo com sucesso.")).toBeInTheDocument();
  });

  it("permite cadastrar corretora dentro do formulario e seleciona automaticamente", async () => {
    server.use(http.get(`${api}/brokerages`, () => HttpResponse.json([])));
    const user = await login("/investimentos/novo");

    expect(await screen.findByText("Você ainda não cadastrou uma corretora.")).toBeInTheDocument();
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
    const user = await login("/investimentos/novo");
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

    expect(await screen.findByText(/Alguns ativos estão sem cotação atual/)).toBeInTheDocument();
    expect(screen.getByText(/VALE3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Atualizar cotações" })).toBeInTheDocument();
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
    const user = await login("/investimentos/novo");
    await user.type(await screen.findByLabelText("Ativo ou empresa"), "PETR4");

    expect(await screen.findByText(/Limite de consultas ao mercado atingido/)).toBeInTheDocument();
  });

  it("importa carteira com revisao de linhas", async () => {
    const user = await login("/carteira/importar");
    await user.selectOptions(await screen.findByLabelText("Corretora"), "brokerage-1");
    await user.type(screen.getByLabelText("Ativo"), "PETR4");
    await user.type(screen.getByLabelText("Quantidade atual"), "10");
    await user.type(screen.getByLabelText("Preço médio"), "37.10");
    expect(screen.getByText(/1 linhas válidas/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar importação" }));
    expect(await screen.findByText("Carteira importada com sucesso.")).toBeInTheDocument();
  });

  it("renderiza inteligencia de carteira com diagnostico e recomendacoes", async () => {
    const user = await login("/planejar");

    expect(await screen.findByRole("heading", { name: "Inteligência de Carteira" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Futuro financeiro" }));
    expect(screen.getAllByText("Minha estratégia").length).toBeGreaterThan(0);
    expect(await screen.findByText("Total da alocação: 100,00%")).toBeInTheDocument();
    expect(screen.getAllByText("Minha estratégia").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Salvar estratégia" }));
    expect(await screen.findByText("Estratégia salva com sucesso.")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Diagnóstico" }));
    expect(screen.getByText("Patrimônio atual")).toBeInTheDocument();
    expect(screen.getByText("Carteira em formação")).toBeInTheDocument();

    await user.click(screen.getAllByText("Diagnóstico")[0]);
    expect(screen.getByText("Pontuação da carteira")).toBeInTheDocument();
    expect(screen.getAllByText("Há concentração relevante em uma única posição.").length).toBeGreaterThan(0);

    await user.click(screen.getAllByText("Recomendações")[0]);
    expect(await screen.findByText("PETR4 - Dados insuficientes")).toBeInTheDocument();
    expect(screen.getByText(/P\/L: O provedor atual/)).toBeInTheDocument();
    expect(screen.getAllByText("Dados insuficientes").length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });

  it("monta carteira com dados determinísticos", async () => {
    const user = await login("/planejar?secao=montar-carteira");
    await user.click(await screen.findByRole("tab", { name: "Montar carteira" }));
    await user.click(screen.getByRole("button", { name: "Montar minha carteira" }));

    expect(await screen.findByRole("heading", { name: "Sua carteira recomendada" })).toBeInTheDocument();
    await user.click(screen.getByText("Distribuição por classe"));
    expect(screen.getAllByText("Ações").length).toBeGreaterThan(0);
    expect(screen.getByText("R$ 6.000,00")).toBeInTheDocument();
    expect(screen.getByText("R$ 4.000,00")).toBeInTheDocument();
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });

  it("redireciona rotas antigas de analise para inteligencia de carteira", async () => {
    await login("/analises");
    expect(await screen.findByRole("heading", { name: "Inteligência de Carteira" })).toBeInTheDocument();

    await login("/simulador-historico");
    expect(await screen.findByRole("heading", { name: "Inteligência de Carteira" })).toBeInTheDocument();
  });

  it("formata valores monetarios e percentuais", () => {
    expect(formatMoney("1234.5")).toBe("R$ 1.234,50");
    expect(formatPercent("12.345")).toBe("12,35%");
  });

  it("atualizar / nao causa tela branca no roteador", async () => {
    sessionStorage.setItem("mesa_quant_session", "test-token");
    renderWithProviders(<AppRouter />, "/");
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument(), { timeout: 10_000 });
    expect((await screen.findAllByText("Patrimônio")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/NaN|undefined|null/)).not.toBeInTheDocument();
  });
});
