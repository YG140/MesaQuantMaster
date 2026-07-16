import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRouter } from "../src/app/router";
import { server } from "./testServer";
import { renderWithProviders } from "./render";

describe("autenticacao", () => {
  it("mostra login primeiro", async () => {
    renderWithProviders(<AppRouter />, "/login");

    expect(await screen.findByRole("heading", { name: /Mesa Quant Master/i })).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
  });

  it("login redireciona para / e exibe Inicio", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/login");

    await user.type(await screen.findByLabelText("E-mail"), "ana@example.com");
    await user.type(screen.getByLabelText("Senha"), "senha-correta");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Patrimonio", {}, { timeout: 10_000 })).toBeInTheDocument();
  });

  it("mostra erro no login invalido", async () => {
    server.use(
      http.post("http://127.0.0.1:8000/auth/login", () =>
        HttpResponse.json({ detail: "Usuario ou senha invalidos." }, { status: 401 }),
      ),
    );
    renderWithProviders(<AppRouter />, "/login");

    const email = await screen.findByLabelText("E-mail");
    fireEvent.change(email, { target: { value: "ana@example.com" } });
    fireEvent.change(await screen.findByLabelText("Senha"), { target: { value: "errada" } });
    fireEvent.submit(email.closest("form") as HTMLFormElement);

    expect(await screen.findByRole("alert")).toHaveTextContent("Usuario ou senha invalidos");
  });

  it("redireciona rota privada sem token", async () => {
    sessionStorage.clear();
    renderWithProviders(<AppRouter />, "/");

    expect(await screen.findByRole("heading", { name: /Mesa Quant Master/i })).toBeInTheDocument();
  });

  it("limpa sessao e redireciona para login no erro 401", async () => {
    server.use(
      http.get("http://127.0.0.1:8000/dashboard", () =>
        HttpResponse.json({ detail: "Not authenticated" }, { status: 401 }),
      ),
    );
    sessionStorage.setItem("mesa_quant_session", "test-token");
    renderWithProviders(<AppRouter />, "/");

    expect(await screen.findByRole("heading", { name: /Mesa Quant Master/i })).toBeInTheDocument();
    expect(sessionStorage.getItem("mesa_quant_session")).toBeNull();
  });

  it("limpa sessao no logout", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("mesa_quant_session", "test-token");
    renderWithProviders(<AppRouter />, "/");
    await screen.findByText("Patrimonio", {}, { timeout: 10_000 });

    await user.click(screen.getByRole("button", { name: "Sair" }));
    expect(await screen.findByRole("heading", { name: /Mesa Quant Master/i })).toBeInTheDocument();
  });
});
