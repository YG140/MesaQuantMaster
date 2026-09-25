import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ForgotPasswordPage } from "../src/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "../src/pages/ResetPasswordPage";
import { renderWithProviders } from "./render";
import { server } from "./testServer";

const api = "http://127.0.0.1:8000";
describe("recuperação de senha", () => {
  it.each([503, 422, "network"] as const)("não mostra sucesso quando a solicitação falha: %s", async status => {
    server.use(http.post(`${api}/auth/forgot-password`, () => status === "network" ? HttpResponse.error() : HttpResponse.json({detail:{message:"Envio indisponível."}}, {status})));
    renderWithProviders(<ForgotPasswordPage />);
    const user=userEvent.setup();
    await user.type(screen.getByLabelText("E-mail"), "test@example.com");
    await user.click(screen.getByRole("button", {name:"Enviar instruções"}));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(document.querySelector(".success-box")).toBeNull();
    expect(screen.getByRole("button", {name:"Enviar instruções"})).toBeEnabled();
  });
  it("exibe resposta neutra e remove a mensagem anterior se a nova tentativa falhar", async () => {
    let fail=false;
    server.use(http.post(`${api}/auth/forgot-password`, () => fail ? HttpResponse.json({detail:{message:"Indisponível."}}, {status:503}) : HttpResponse.json({message:"Esta resposta não confirma cadastro nem entrega de e-mail."})));
    renderWithProviders(<ForgotPasswordPage />);const user=userEvent.setup();
    await user.type(screen.getByLabelText("E-mail"), "test@example.com");
    await user.click(screen.getByRole("button", {name:"Enviar instruções"}));
    expect(await screen.findByRole("status")).toHaveTextContent("não confirma");
    expect(document.querySelector(".success-box")).toBeNull();
    fail=true;await user.click(screen.getByRole("button", {name:"Enviar instruções"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Indisponível");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
  it.each(["Token inválido.","Token expirado.","Token já utilizado."])("mostra rejeição do link sem sucesso: %s", async message => {
    server.use(http.post(`${api}/auth/reset-password`, () => HttpResponse.json({detail:{message}}, {status:400})));
    renderWithProviders(<ResetPasswordPage />, "/redefinir-senha?token=isolated-test-token-12345");
    const user=userEvent.setup();
    await user.type(screen.getByLabelText("Nova senha", {exact:true}), "test-password-only");
    await user.type(screen.getByLabelText("Confirmar nova senha", {exact:true}), "test-password-only");
    await user.click(screen.getByRole("button", {name:"Salvar nova senha"}));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(document.querySelector(".success-box")).toBeNull();
  });
  it("desabilita redefinição sem token", () => {
    renderWithProviders(<ResetPasswordPage />, "/redefinir-senha");
    expect(screen.getByRole("alert")).toHaveTextContent("Link de redefinição inválido");
    expect(screen.getByRole("button", {name:"Salvar nova senha"})).toBeDisabled();
  });
});
