import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ErrorState } from "../components/feedback/ErrorState";
import { resendVerification, verifyEmail } from "../services/endpoints/auth";

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const email = params.get("email") ?? "";
  const [message, setMessage] = useState(
    token ? "Confirmando seu e-mail..." : "Enviamos um link de confirmação. Verifique sua caixa de entrada.",
  );
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!token) return;
    void verifyEmail(token).then(({ message: value }) => setMessage(value)).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "O link é inválido, expirou ou já foi utilizado.");
    });
  }, [token]);

  async function resend() {
    if (!email || sending) return;
    setSending(true);
    setError(null);
    try {
      const response = await resendVerification(email);
      setMessage(response.message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível reenviar agora.");
    } finally {
      setSending(false);
    }
  }

  return <main className="auth-page"><Card>
    <div className="auth-brand"><span>MQ</span><h1>Verifique seu e-mail</h1><p>{message}</p></div>
    {error ? <ErrorState message={error} /> : null}
    {!token && email ? <Button onClick={resend} disabled={sending}>{sending ? "Enviando..." : "Reenviar e-mail"}</Button> : null}
    <p className="auth-link"><Link to="/login">Voltar para o login</Link></p>
  </Card></main>;
}
