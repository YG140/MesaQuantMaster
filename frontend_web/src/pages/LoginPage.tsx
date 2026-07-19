import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { ErrorState } from "../components/feedback/ErrorState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { useAuth } from "../features/auth/useAuth";

const schema = z.object({
  email: z.string().email("Informe um e-mail valido."),
  password: z.string().min(1, "Informe sua senha."),
});

type LoginForm = z.infer<typeof schema>;

export function LoginPage() {
  const auth = useAuth();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<LoginForm>({ resolver: zodResolver(schema) });

  async function submit(values: LoginForm) {
    setError(null);
    try {
      await auth.login(values.email, values.password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar.");
    }
  }

  return (
    <main className="auth-page">
      <Card>
        <div className="auth-brand">
          <span>MQ</span>
          <h1>Mesa Quant Master</h1>
          <p>Entre para acessar sua carteira e ferramentas quantitativas.</p>
        </div>
        {error ? <ErrorState message={error} /> : null}
        <form onSubmit={form.handleSubmit(submit)} className="form-grid">
          <Input label="E-mail" type="email" {...form.register("email")} error={form.formState.errors.email?.message} />
          <Input label="Senha" type="password" {...form.register("password")} error={form.formState.errors.password?.message} />
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Entrando..." : "Entrar"}
          </Button>
        </form>
        <p className="auth-link">
          Ainda não tem conta? <Link to="/cadastro">Criar conta</Link>
        </p>
      </Card>
    </main>
  );
}
