import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { ErrorState } from "../components/feedback/ErrorState";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { useAuth } from "../features/auth/useAuth";

const schema = z
  .object({
    name: z.string().min(3, "Informe pelo menos 3 caracteres."),
    email: z.string().email("Informe um e-mail valido."),
    password: z.string().min(8, "A senha precisa ter pelo menos 8 caracteres."),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "As senhas precisam ser iguais.",
    path: ["confirmPassword"],
  });

type RegisterForm = z.infer<typeof schema>;

export function RegisterPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<RegisterForm>({ resolver: zodResolver(schema) });

  async function submit(values: RegisterForm) {
    setError(null);
    try {
      await auth.register({
        name: values.name,
        email: values.email,
        password: values.password,
      });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nao foi possivel criar a conta.");
    }
  }

  return (
    <main className="auth-page">
      <Card>
        <div className="auth-brand">
          <span>MQ</span>
          <h1>Criar conta</h1>
          <p>Configure seu acesso ao Mesa Quant Master.</p>
        </div>
        {error ? <ErrorState message={error} /> : null}
        <form onSubmit={form.handleSubmit(submit)} className="form-grid">
          <Input label="Nome" {...form.register("name")} error={form.formState.errors.name?.message} />
          <Input label="E-mail" type="email" {...form.register("email")} error={form.formState.errors.email?.message} />
          <Input label="Senha" type="password" {...form.register("password")} error={form.formState.errors.password?.message} />
          <Input label="Confirmar senha" type="password" {...form.register("confirmPassword")} error={form.formState.errors.confirmPassword?.message} />
          <Button type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Criando..." : "Criar conta"}
          </Button>
        </form>
        <p className="auth-link">
          Ja tem conta? <Link to="/login">Voltar para login</Link>
        </p>
      </Card>
    </main>
  );
}
