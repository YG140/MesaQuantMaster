import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { AssetsPage } from "../pages/AssetsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { ImportPortfolioPage } from "../pages/ImportPortfolioPage";
import { LoginPage } from "../pages/LoginPage";
import { NewInvestmentPage } from "../pages/NewInvestmentPage";
import { PortfolioIntelligencePage } from "../pages/PortfolioIntelligencePage";
import { PortfolioPage } from "../pages/PortfolioPage";
import { RegisterPage } from "../pages/RegisterPage";
import { VerifyEmailPage } from "../pages/VerifyEmailPage";
import { ForgotPasswordPage } from "../pages/ForgotPasswordPage";
import { ResetPasswordPage } from "../pages/ResetPasswordPage";

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
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/carteira" element={<PortfolioPage />} />
          <Route path="/investimentos/novo" element={<NewInvestmentPage />} />
          <Route path="/carteira/importar" element={<ImportPortfolioPage />} />
          <Route path="/inteligencia-carteira" element={<PortfolioIntelligencePage />} />
          <Route path="/analises" element={<Navigate to="/inteligencia-carteira" replace />} />
          <Route path="/simulador-historico" element={<Navigate to="/inteligencia-carteira" replace />} />
          <Route path="/ativos" element={<AssetsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
