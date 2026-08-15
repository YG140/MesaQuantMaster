import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PasswordInput } from "../components/ui/PasswordInput";
import { ErrorState } from "../components/feedback/ErrorState";
import { resetPassword } from "../services/endpoints/auth";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(token ? null : "Link de redefinição inválido.");
  const [sending, setSending] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (sending || !token) return;
    if (password.length < 8 || password !== confirmation) {
      setError("Use ao menos 8 caracteres e confirme a mesma senha.");
      return;
    }
    setSending(true); setError(null);
    try {
      setMessage((await resetPassword(token, password)).message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "O link é inválido, expirou ou já foi utilizado.");
    } finally { setSending(false); }
  }
  return <main className="auth-page"><Card>
    <div className="auth-brand"><span>MQ</span><h1>Redefinir senha</h1><p>Cadastre uma nova senha para sua conta.</p></div>
    {message ? <div className="success-box">{message}</div> : null}
    {error ? <ErrorState message={error} /> : null}
    {!message ? <form onSubmit={submit} className="form-grid">
      <PasswordInput label="Nova senha" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
      <PasswordInput label="Confirmar nova senha" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
      <Button type="submit" disabled={sending || !token}>{sending ? "Salvando..." : "Salvar nova senha"}</Button>
    </form> : null}
    <p className="auth-link"><Link to="/login">Voltar para o login</Link></p>
  </Card></main>;
}
