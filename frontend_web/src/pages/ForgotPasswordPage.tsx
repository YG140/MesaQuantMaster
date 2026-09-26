import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { forgotPassword } from "../services/endpoints/auth";
import { ErrorState } from "../components/feedback/ErrorState";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (sending) return;
    setSending(true);
    setMessage(null);
    setError(null);
    try {
      setMessage((await forgotPassword(email)).message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível solicitar a recuperação. Tente novamente.");
    } finally {
      setSending(false);
    }
  }
  return <main className="auth-page"><Card>
    <div className="auth-brand"><span>MQ</span><h1>Esqueci minha senha</h1><p>Informe seu e-mail para receber as instruções.</p></div>
    {message ? <div className="state" role="status">{message}</div> : null}
    {error ? <ErrorState message={error} /> : null}
    <form onSubmit={submit} className="form-grid">
      <Input label="E-mail" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
      <Button type="submit" disabled={sending}>{sending ? "Enviando..." : "Enviar instruções"}</Button>
    </form>
    <p className="auth-link"><Link to="/login">Voltar para o login</Link></p>
  </Card></main>;
}
