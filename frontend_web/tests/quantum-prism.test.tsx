import { http, HttpResponse } from "msw";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppRouter } from "../src/app/router";
import { investorProfileActionLabel } from "../src/features/investorProfile/presentation";
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

describe("Quantum Prism", () => {
  it("compara ativos visualmente pelo endpoint de análise em lote", async () => {
    const snapshot = (symbol: string) => ({ symbol, name: symbol, current_price: "10", currency: "BRL", valuation_score: "70", income_score: null, growth_score: "60", risk_score: "40", liquidity_score: "80", data_quality_score: "90", market_updated_at: "2026-08-14T01:00:00Z", coverage_percentage: "75", confidence: "high", positive_reasons: [], warning_reasons: [] });
    server.use(
      http.get(`${api}/assets`, () => HttpResponse.json([])),
      http.get(`${api}/market/search`, ({request}) => { const q=new URL(request.url).searchParams.get("q")?.toUpperCase(); return HttpResponse.json(q?[{ticker:q,name:q,current_price:"10",currency:"BRL",asset_type:"STOCK"}]:[]); }),
      http.get(`${api}/intelligence/assets/:symbol`, ({params}) => HttpResponse.json(snapshot(String(params.symbol)))),
      http.post(`${api}/intelligence/assets/analyze`, async ({request}) => { const body=await request.json() as {symbols:string[]}; return HttpResponse.json({snapshots:body.symbols.map(snapshot),errors:[],provider_calls:1,calculated_at:"2026-08-14T01:00:00Z"}); }),
    );
    const user = await openAuthenticated("/ativos");
    const search = await screen.findByPlaceholderText("PETR4 ou Petrobras");
    // timeout maior: SearchAutocomplete agora tem debounce real (~300ms,
    // ver Correção interface) antes de disparar a busca.
    await user.type(search,"PETR4"); await user.click(await screen.findByRole("button",{name:/PETR4/}, {timeout:10_000}));
    await user.clear(search); await user.type(search,"VALE3"); await user.click(await screen.findByRole("button",{name:/VALE3/}, {timeout:10_000}));
    await user.click(screen.getByRole("button",{name:"Comparar ativos"}));
    expect(await screen.findByRole("cell",{name:"PETR4"})).toBeInTheDocument();
    expect(screen.getByRole("cell",{name:"VALE3"})).toBeInTheDocument();
    expect(screen.getAllByText("Indisponível").length).toBeGreaterThan(0);
  });

  it("abre Configurações pelo Header e separa estados reais, locais e planejados", async () => {
    server.use(http.get(`${api}/market/provider-capabilities`, () => HttpResponse.json({ provider: "hybrid", configured: true, reachable: null, supported_domains: ["quotes"], accessible_domains: [], restricted_domains: ["fundamentals"], last_checked_at: "2026-08-14T01:00:00Z" })));
    const user = await openAuthenticated();
    await user.click(screen.getByRole("link", { name: "Configurações" }));
    expect(await screen.findByRole("heading", { name: "Configurações", level: 2 })).toBeInTheDocument();
    expect(screen.getAllByText("Conta e Perfil").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Real").length).toBeGreaterThan(0);
    expect(screen.getByText("Local")).toBeInTheDocument();
    expect(screen.getAllByText("Planejado").length).toBeGreaterThan(0);
    await user.selectOptions(screen.getByLabelText("Perfil visual"), "compact");
    expect(JSON.parse(localStorage.getItem("mesa_quant_visual_preferences_v1") ?? "{}").profile).toBe("compact");
  });

  it("descarta preferências visuais inválidas do storage", async () => {
    localStorage.setItem("mesa_quant_visual_preferences_v1", JSON.stringify({ profile: "inexistente", reducedMotion: "não" }));
    await openAuthenticated("/configuracoes");
    expect(await screen.findByLabelText("Perfil visual")).toHaveValue("workstation");
  });

  it("descarta um perfil visual legado 'analytical' (removido da UI) com segurança", async () => {
    // Correção interface: "Analítico" nunca teve efeito CSS real (controle
    // falso) e foi removido das opções -- um valor legado salvo por um
    // usuário antigo precisa cair para o default, nunca quebrar o parse.
    localStorage.setItem("mesa_quant_visual_preferences_v1", JSON.stringify({ profile: "analytical" }));
    await openAuthenticated("/configuracoes");
    expect(await screen.findByLabelText("Perfil visual")).toHaveValue("workstation");
    expect(screen.queryByRole("option", { name: "Analítico" })).not.toBeInTheDocument();
  });

  it("expõe a navegação principal e o contexto do dashboard", async () => {
    await openAuthenticated();
    expect(await screen.findByRole("heading", { name: /Seu universo financeiro/i })).toBeInTheDocument();
    const desktop = screen.getByTestId("desktop-primary-navigation");
    const mobile = screen.getByTestId("mobile-primary-navigation");
    expect(desktop.children).toHaveLength(5);
    expect(mobile.children).toHaveLength(5);
    for (const label of ["Início", "Carteira", "Mesa IA", "Mercado", "Planejar"]) {
      expect(desktop).toHaveTextContent(label);
      expect(mobile).toHaveTextContent(label);
    }
    const actions = within(document.querySelector(".quick-action-grid")!);
    expect(actions.getByRole("link", { name: /^Investir/i })).toHaveAttribute("href", "/investimentos/novo");
    expect(actions.getByRole("link", { name: /^Analisar/i })).toHaveAttribute("href", "/ativos");
    expect(actions.getByRole("link", { name: /^Planejar/i })).toHaveAttribute("href", "/planejar?secao=montar-carteira");
    expect(actions.getByRole("link", { name: /^Acompanhar/i })).toHaveAttribute("href", "/carteira");
  });

  it("abre a Mesa IA e envia uma pergunta ao endpoint real", async () => {
    const user = await openAuthenticated("/analisar");
    await user.click((await screen.findAllByRole("button", { name: /Mesa IA/i }))[0]);
    const input = await screen.findByLabelText("Pergunte à Mesa IA");
    await user.type(input, "Como está a concentração da carteira?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/Leitura educacional: Como está a concentração/i)).toBeInTheDocument();
    expect(screen.getByText("Análise da carteira")).toBeInTheDocument();
    expect(screen.getByText(/Não constitui recomendação/i)).toBeInTheDocument();
  });

  it("traduz indisponibilidade da Mesa IA sem perder a conversa", async () => {
    server.use(http.post(`${api}/ai-agent/chat`, () => HttpResponse.json({ detail: "disabled" }, { status: 503 })));
    const user = await openAuthenticated();
    await user.click((await screen.findAllByRole("button", { name: /Mesa IA/i }))[0]);
    await user.type(await screen.findByLabelText("Pergunte à Mesa IA"), "Analise minha carteira");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/desativada ou temporariamente indisponível/i);
    expect(screen.getByText("Analise minha carteira")).toBeInTheDocument();
  });

  it("contextualiza a Mesa IA sem alterar o payload V1", async () => {
    let body: unknown;
    server.use(http.post(`${api}/ai-agent/chat`, async ({request}) => { body = await request.json(); return HttpResponse.json({ answer: "Contexto explicado.", tools_used: [], warnings: [], data_quality_notes: [] }); }));
    const user = await openAuthenticated("/planejar?secao=futuro-financeiro");
    await user.click((await screen.findAllByRole("button", { name: /Mesa IA/i }))[0]);
    expect(screen.getByText(/Contexto · Futuro financeiro/)).toBeInTheDocument();
    await user.type(await screen.findByLabelText("Pergunte à Mesa IA"), "Explique esta tela");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    await screen.findByText("Contexto explicado.");
    expect(body).toEqual({ message: "Explique esta tela" });
  });

  it("redireciona Investir para a seção canônica de montagem", async () => {
    await openAuthenticated("/investir");
    expect(await screen.findByRole("tab", { name: "Montar carteira" })).toHaveAttribute("aria-selected", "true");
    // Correção interface: "Montar carteira" busca sua própria política de
    // forma independente e assíncrona -- o botão só aparece depois que
    // essa busca (rápida, mockada) resolve.
    expect(await screen.findAllByRole("button", { name: "Montar minha carteira" })).toHaveLength(1);
  });

  it("limita a inteligência a três áreas principais", async () => {
    await openAuthenticated("/planejar");
    expect(await screen.findAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: "Diagnóstico" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Montar carteira" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Futuro financeiro" })).toBeInTheDocument();
  });

  it("header reorganizado: sem badge API FastAPI, sem Mesa IA/Sair redundantes, com ação Prisma do usuário", async () => {
    await openAuthenticated();
    const topbar = document.querySelector<HTMLElement>(".topbar")!;
    expect(within(topbar).queryByText("API FastAPI")).not.toBeInTheDocument();
    expect(within(topbar).queryByRole("button", { name: /Mesa IA/i })).not.toBeInTheDocument();
    expect(within(topbar).queryByRole("button", { name: "Sair" })).not.toBeInTheDocument();
    // Mesa IA nunca desaparece -- continua acessível pelo Sidebar (desktop e mobile).
    expect(screen.getAllByRole("button", { name: /Mesa IA/i }).length).toBeGreaterThan(0);
    // Ação Prisma do usuário: nome real, leva a /configuracoes#conta.
    const userLink = within(topbar).getByRole("link", { name: /Abrir conta e perfil/i });
    expect(userLink).toHaveAttribute("href", "/configuracoes#conta");
    expect(userLink).toHaveTextContent("Ana Quant");
  });

  it("deep link #conta rola a seção Conta e Perfil para a visão", async () => {
    const scrollSpy = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = scrollSpy;
    await openAuthenticated("/configuracoes#conta");
    expect(await screen.findByRole("heading", { name: "Configurações", level: 2 })).toBeInTheDocument();
    expect(scrollSpy).toHaveBeenCalled();
  });

  it.each(["/inteligencia-carteira", "/analisar", "/analises", "/simulador-historico"])("mantém a rota histórica %s", async (path) => {
    await openAuthenticated(path);
    expect(await screen.findByRole("heading", { name: "Inteligência de Carteira" })).toBeInTheDocument();
  });
});

describe("investorProfileActionLabel", () => {
  it("indica revisão (não 'Continuar onboarding') para needs_review, já que esse status já dispara o fluxo de revisão", () => {
    expect(investorProfileActionLabel("needs_review")).toBe("Revisar perfil");
  });

  it("mantém 'Refazer avaliação' para complete", () => {
    expect(investorProfileActionLabel("complete")).toBe("Refazer avaliação");
  });

  it.each(["needs_onboarding", "in_progress", "pending_confirmation", null, undefined])(
    "usa 'Continuar questionário' para estado incompleto (%s)",
    (status) => {
      expect(investorProfileActionLabel(status)).toBe("Continuar questionário");
    },
  );
});
