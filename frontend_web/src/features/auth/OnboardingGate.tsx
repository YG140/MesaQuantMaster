import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { LoadingState } from "../../components/feedback/LoadingState";
import { investorProfileEndpoints } from "../../services/endpoints/investorProfile";
import type { OnboardingStatus } from "../../types/api";
import { useAuth } from "./useAuth";

const ONBOARDING_PENDING_STATUSES = new Set<OnboardingStatus>([
  "needs_onboarding",
  "in_progress",
  "pending_confirmation",
]);

/**
 * Protege as rotas normais da aplicação (dentro do AppShell) contra um
 * usuário autenticado que ainda não concluiu o onboarding — mesmo em
 * acesso direto (deep link) ou refresh, sem depender de localStorage: o
 * status vem sempre do backend.
 */
export function OnboardingGate() {
  const { token } = useAuth();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setIsLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setIsLoading(true);
    investorProfileEndpoints
      .status(token)
      .then((response) => {
        if (!cancelled) setStatus(response.status);
      })
      .catch(() => {
        // Diagnóstico indisponível: não bloqueia a navegação normal.
        if (!cancelled) setStatus("complete");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (isLoading) {
    return <LoadingState label="Carregando seu perfil..." />;
  }

  if (status && ONBOARDING_PENDING_STATUSES.has(status)) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}
