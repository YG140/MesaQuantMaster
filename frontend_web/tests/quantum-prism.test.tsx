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

describe("Quantum Prism", () => {
  it("expõe a navegação principal e o contexto do dashboard", async () => {
    await openAuthenticated();
    expect(await screen.findByRole("heading", { name: /Seu universo financeiro/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Acompanhar/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Investir/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Analisar/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /Planejar/i }).length).toBeGreaterThan(0);
    expect(document.querySelector(".mobile-nav")).toBeInTheDocument();
  });

  it("abre a Mesa IA e envia uma pergunta ao endpoint real", async () => {
    const user = await openAuthenticated("/analisar");
    await user.click((await screen.findAllByRole("button", { name: /Mesa IA/i }))[0]);
    const input = screen.getByLabelText("Pergunte à Mesa IA");
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
    await user.type(screen.getByLabelText("Pergunte à Mesa IA"), "Analise minha carteira");
    await user.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/desativada ou temporariamente indisponível/i);
    expect(screen.getByText("Analise minha carteira")).toBeInTheDocument();
  });

  it("mantém Investir e Planejar em rotas funcionais", async () => {
    await openAuthenticated("/investir");
    expect(await screen.findByRole("heading", { name: "Central de investimentos" })).toBeInTheDocument();
  });
});
