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

    expect(
      await screen.findByRole(
        "heading",
        { name: /Mesa Quant Master/i },
        { timeout: 10_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Visualizar senha" })).toHaveAttribute("aria-pressed", "false");
  });

  it("alterna a visibilidade da senha por clique e teclado sem perder o valor", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/login");
    const password = await screen.findByLabelText("Senha");
    const toggle = screen.getByRole("button", { name: "Visualizar senha" });
    await user.type(password, "senha-preservada");
    expect(password).toHaveAttribute("type", "password");
    await user.click(toggle);
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("senha-preservada");
    expect(screen.getByRole("button", { name: "Ocultar senha" })).toHaveAttribute("aria-pressed", "true");
    await user.tab();
    await user.keyboard("{Shift>}{Tab}{/Shift}{Enter}");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("senha-preservada");
    expect(screen.getByRole("button", { name: "Visualizar senha" })).toHaveAttribute("aria-pressed", "false");
  });

  it("login redireciona para / e exibe Inicio", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/login");

    await user.type(await screen.findByLabelText("E-mail"), "ana@example.com");
    await user.type(screen.getByLabelText("Senha"), "senha-correta");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect((await screen.findAllByText("Patrimônio", {}, { timeout: 10_000 })).length).toBeGreaterThan(0);
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

    expect(
      await screen.findByRole(
        "heading",
        { name: /Mesa Quant Master/i },
        { timeout: 10_000 },
      ),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem("mesa_quant_session")).toBeNull();
  });

  it("limpa sessao no logout", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("mesa_quant_session", "test-token");
    renderWithProviders(<AppRouter />, "/");
    await screen.findAllByText("Patrimônio", {}, { timeout: 10_000 });

    await user.click(screen.getByRole("button", { name: "Sair" }));
    expect(await screen.findByRole("heading", { name: /Mesa Quant Master/i })).toBeInTheDocument();
  });

  it("cadastro orienta verificacao e permite reenvio", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/cadastro");
    await user.type(await screen.findByLabelText("Nome"), "Ana Quant");
    await user.type(screen.getByLabelText("E-mail"), "ana@example.com");
    await user.type(screen.getByLabelText("Senha"), "senha-segura");
    await user.type(screen.getByLabelText("Confirmar senha"), "senha-segura");
    await user.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByRole("heading", { name: "Verifique seu e-mail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reenviar e-mail" }));
    expect(await screen.findByText(/Se o e-mail estiver cadastrado/)).toBeInTheDocument();
  });

  it("solicita recuperacao com resposta generica", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/esqueci-minha-senha");
    await user.type(await screen.findByLabelText("E-mail"), "ana@example.com");
    await user.click(screen.getByRole("button", { name: "Enviar instruções" }));
    expect(await screen.findByText(/Se o e-mail estiver cadastrado/)).toBeInTheDocument();
  });

  it("redefine a senha por token", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AppRouter />, "/redefinir-senha?token=token-seguro-comprido");
    await user.type(await screen.findByLabelText("Nova senha"), "senha-nova");
    await user.type(screen.getByLabelText("Confirmar nova senha"), "senha-nova");
    await user.click(screen.getByRole("button", { name: "Salvar nova senha" }));
    expect(await screen.findByText("Senha redefinida com sucesso.")).toBeInTheDocument();
  });
});
