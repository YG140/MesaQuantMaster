import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { OnboardingGate } from "../features/auth/OnboardingGate";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { DashboardPage } from "../pages/DashboardPage";
import { ImportPortfolioPage } from "../pages/ImportPortfolioPage";
import { LoginPage } from "../pages/LoginPage";
import { NewInvestmentPage } from "../pages/NewInvestmentPage";
import { PortfolioPage } from "../pages/PortfolioPage";
import { RegisterPage } from "../pages/RegisterPage";
import { VerifyEmailPage } from "../pages/VerifyEmailPage";
import { ForgotPasswordPage } from "../pages/ForgotPasswordPage";
import { ResetPasswordPage } from "../pages/ResetPasswordPage";
import { LoadingState } from "../components/feedback/LoadingState";

const AssetsPage = lazy(() => import("../pages/AssetsPage").then(module => ({ default: module.AssetsPage })));
const PortfolioIntelligencePage = lazy(() => import("../pages/PortfolioIntelligencePage").then(module => ({ default: module.PortfolioIntelligencePage })));
const SettingsPage = lazy(() => import("../pages/SettingsPage").then(module => ({ default: module.SettingsPage })));
const OnboardingPage = lazy(() => import("../pages/OnboardingPage").then(module => ({ default: module.OnboardingPage })));

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/cadastro" element={<RegisterPage />} />
      <Route path="/verifique-seu-email" element={<VerifyEmailPage />} />
      <Route path="/verificar-email" element={<VerifyEmailPage />} />
      <Route path="/esqueci-minha-senha" element={<ForgotPasswordPage />} />
      <Route path="/redefinir-senha" element={<ResetPasswordPage />} />
      <Route element={<ProtectedRoute />}>
        <Route
          path="/onboarding"
          element={
            <Suspense fallback={<LoadingState label="Carregando onboarding…" />}>
              <OnboardingPage />
            </Suspense>
          }
        />
        <Route element={<OnboardingGate />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="/carteira" element={<PortfolioPage />} />
            <Route path="/investimentos/novo" element={<NewInvestmentPage />} />
            <Route path="/carteira/importar" element={<ImportPortfolioPage />} />
            <Route path="/planejar" element={<Suspense fallback={<LoadingState label="Carregando Planejar…"/>}><PortfolioIntelligencePage /></Suspense>} />
            <Route path="/inteligencia-carteira" element={<Navigate to="/planejar" replace />} />
            <Route path="/investir" element={<Navigate to="/planejar?secao=montar-carteira" replace />} />
            <Route path="/analisar" element={<Navigate to="/planejar?secao=diagnostico" replace />} />
            <Route path="/analises" element={<Navigate to="/planejar?secao=diagnostico" replace />} />
            <Route path="/simulador-historico" element={<Navigate to="/planejar?secao=futuro-financeiro" replace />} />
            <Route path="/ativos" element={<Suspense fallback={<LoadingState label="Carregando Mercado…"/>}><AssetsPage /></Suspense>} />
            <Route path="/configuracoes" element={<Suspense fallback={<LoadingState label="Carregando Configurações…"/>}><SettingsPage /></Suspense>} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
