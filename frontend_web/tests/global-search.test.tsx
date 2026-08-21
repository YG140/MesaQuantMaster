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

function asset(ticker: string, name = ticker) {
  return { ticker, name, current_price: "10", currency: "BRL", asset_type: "STOCK" };
}

describe("busca global do header", () => {
  it("a lupa abre um diálogo de busca com foco no campo", async () => {
    const user = await openAuthenticated();
    const trigger = screen.getByRole("button", { name: "Pesquisar" });
    await user.click(trigger);
    // GlobalSearchDialog é carregado via lazy()/Suspense -- só existe no
    // DOM depois que o import dinâmico resolve, nunca no mesmo tick do clique.
    expect(await screen.findByRole("dialog", { name: "Pesquisar" })).toBeInTheDocument();
    const input = await screen.findByLabelText("Ativo ou empresa");
    await waitFor(() => expect(input).toHaveFocus());
  });

  it("Escape fecha o diálogo e devolve o foco ao gatilho", async () => {
    const user = await openAuthenticated();
    const trigger = screen.getByRole("button", { name: "Pesquisar" });
    await user.click(trigger);
    expect(await screen.findByRole("dialog", { name: "Pesquisar" })).toBeInTheDocument();
    // Aguarda o foco chegar ao campo (timer de foco de GlobalSearchDialog)
    // antes de fechar, para garantir que o "foco anterior" restaurado seja
    // sempre o gatilho, nunca uma corrida com o efeito de foco inicial.
    await waitFor(() => expect(screen.getByLabelText("Ativo ou empresa")).toHaveFocus());
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("com sugestões abertas, Escape fecha só a lista primeiro -- não o diálogo inteiro", async () => {
    server.use(http.get(`${api}/market/search`, () => HttpResponse.json([asset("PETR4")])));
    const user = await openAuthenticated();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const input = await screen.findByLabelText("Ativo ou empresa");
    await user.type(input, "PETR4");
    await screen.findByRole("option", { name: /PETR4/ }, { timeout: 10_000 });

    // 1ª Escape: fecha só as sugestões (SearchAutocomplete intercepta e
    // interrompe a propagação) -- o diálogo continua aberto.
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("option", { name: /PETR4/ })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Pesquisar" })).toBeInTheDocument();

    // 2ª Escape: sugestões já fechadas, então o evento chega ao diálogo
    // (listener em document) e fecha a busca global.
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("aplica debounce real -- não dispara uma requisição por tecla digitada", async () => {
    let calls = 0;
    server.use(
      http.get(`${api}/market/search`, ({ request }) => {
        calls += 1;
        const q = new URL(request.url).searchParams.get("q")?.toUpperCase();
        return HttpResponse.json(q ? [asset(q)] : []);
      }),
    );
    const user = await openAuthenticated();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const input = await screen.findByLabelText("Ativo ou empresa");
    await user.type(input, "PETR4");
    expect(calls).toBe(0);
    await waitFor(() => expect(calls).toBe(1), { timeout: 10_000 });
    expect(await screen.findByRole("option", { name: /PETR4/ }, { timeout: 10_000 })).toBeInTheDocument();
  });

  it("mostra 'Nenhum ativo encontrado' quando a busca não retorna resultados", async () => {
    // Regressão: results.length > 0 não pode ser pré-requisito para
    // mostrar o feedback de busca vazia -- do contrário o estado nunca
    // aparece (results.length === 0 sempre implica painel fechado).
    server.use(http.get(`${api}/market/search`, () => HttpResponse.json([])));
    const user = await openAuthenticated();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const input = await screen.findByLabelText("Ativo ou empresa");
    await user.type(input, "ZZZZ9");

    expect(await screen.findByText("Nenhum ativo encontrado.", {}, { timeout: 10_000 })).toBeInTheDocument();
    // Sem listbox real: nenhuma role="option" e aria-expanded coerente
    // com a ausência de popup, mesmo com o feedback textual visível.
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("navega os resultados com as setas e seleciona com Enter", async () => {
    server.use(
      http.get(`${api}/market/search`, () => HttpResponse.json([asset("PETR4", "Petrobras PN"), asset("PETR3", "Petrobras ON")])),
    );
    const user = await openAuthenticated();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const input = await screen.findByLabelText("Ativo ou empresa");
    await user.type(input, "PETR");
    await screen.findByRole("option", { name: /PETR4/ }, { timeout: 10_000 });

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /PETR4/ })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: /PETR3/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("option", { name: /PETR4/ })).toHaveAttribute("aria-selected", "false");

    await user.keyboard("{Enter}");
    // Seleção fecha o diálogo e navega para Mercado com o ativo escolhido.
    // timeout maior: a rota de Mercado é carregada via lazy()/Suspense.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText("PETR3", {}, { timeout: 10_000 })).toBeInTheDocument();
  });

  it("expõe combobox/listbox acessíveis com aria-activedescendant estável", async () => {
    server.use(http.get(`${api}/market/search`, () => HttpResponse.json([asset("PETR4")])));
    const user = await openAuthenticated();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    const input = await screen.findByLabelText("Ativo ou empresa");
    expect(input).toHaveAttribute("role", "combobox");
    expect(input).toHaveAttribute("aria-expanded", "false");
    await user.type(input, "PETR4");
    const option = await screen.findByRole("option", { name: /PETR4/ }, { timeout: 10_000 });
    const listbox = screen.getByRole("listbox");
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(input.getAttribute("aria-controls")).toBe(listbox.id);
    await user.keyboard("{ArrowDown}");
    expect(input.getAttribute("aria-activedescendant")).toBe(option.id);
  });

  it("seleção navega para Mercado/ativos com o ativo escolhido (?ativo=)", async () => {
    server.use(http.get(`${api}/market/search`, () => HttpResponse.json([asset("VALE3", "Vale ON")])));
    const user = await openAuthenticated();
    await user.click(screen.getByRole("button", { name: "Pesquisar" }));
    await user.type(await screen.findByLabelText("Ativo ou empresa"), "VALE3");
    // O elemento clicável de fato é o <button> aninhado dentro do
    // role="option" -- clicar no <li> não dispararia o handler.
    await user.click(await screen.findByRole("button", { name: /VALE3/ }, { timeout: 10_000 }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Mercado e ativos" }, { timeout: 10_000 })).toBeInTheDocument();
    expect(screen.getAllByText("VALE3").length).toBeGreaterThan(0);
  });

  it("continua funcional nos usos existentes em Ativos e Novo investimento", async () => {
    const user = await openAuthenticated("/ativos");
    await user.type(await screen.findByLabelText("Ativo ou empresa"), "PETR4");
    expect(await screen.findByRole("option", { name: /PETR4/ }, { timeout: 10_000 })).toBeInTheDocument();
  });

  it("selecionar um novo ativo em Ativos depois de um deep link mantém a URL em sincronia sem refazer a busca do deep link", async () => {
    let searchCalls = 0;
    server.use(
      http.get(`${api}/market/search`, ({ request }) => {
        searchCalls += 1;
        const q = new URL(request.url).searchParams.get("q")?.toUpperCase();
        if (q === "PETR4") return HttpResponse.json([asset("PETR4")]);
        if (q === "VALE3") return HttpResponse.json([asset("VALE3")]);
        return HttpResponse.json([]);
      }),
    );
    const user = await openAuthenticated("/ativos?ativo=PETR4");
    // Seleção inicial via deep link (?ativo=PETR4): a resolução direta do
    // ticker também preenche o campo de busca, o que por sua vez dispara a
    // busca interna do próprio SearchAutocomplete para o mesmo ticker
    // (redundância pré-existente do Prompt 2, fora do escopo desta
    // correção). Aguarda essa segunda busca assentar -- opção do PETR4
    // renderizada -- antes de medir a contagem-base usada abaixo.
    expect(await screen.findByText("Código")).toBeInTheDocument();
    // role="option" é único à sugestão da lista -- o ticker também aparece
    // num <button> de comparação (adicionado pelo próprio efeito de deep
    // link), então um seletor role="button" aqui seria ambíguo.
    await screen.findByRole("option", { name: /PETR4/ }, { timeout: 10_000 });
    const deepLinkCalls = searchCalls;

    // Usuário busca e seleciona um ativo DIFERENTE diretamente na própria
    // página -- isso precisa atualizar a URL sem disparar uma segunda
    // busca redundante para o mesmo ativo já retornado por essa seleção
    // (regressão: o efeito de deep link reagindo à própria mudança de URL
    // que ele causou).
    const input = screen.getByLabelText("Ativo ou empresa");
    await user.clear(input);
    await user.type(input, "VALE3");
    await user.click(await screen.findByRole("button", { name: /VALE3/ }, { timeout: 10_000 }));

    expect(await screen.findAllByText("VALE3")).not.toHaveLength(0);
    // Só UMA busca nova (a digitação de VALE3) -- nunca uma busca extra
    // causada pelo efeito de deep link reagindo à própria mudança de URL
    // que a seleção manual provoca.
    await waitFor(() => expect(searchCalls).toBe(deepLinkCalls + 1));
  });
});
