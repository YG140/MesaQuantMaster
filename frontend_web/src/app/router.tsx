import { Route, Routes } from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { AnalysisPage } from "../pages/AnalysisPage";
import { AssetsPage } from "../pages/AssetsPage";
import { DashboardPage } from "../pages/DashboardPage";
import { HistoricalSimulatorPage } from "../pages/HistoricalSimulatorPage";
import { ImportPortfolioPage } from "../pages/ImportPortfolioPage";
import { LoginPage } from "../pages/LoginPage";
import { NewInvestmentPage } from "../pages/NewInvestmentPage";
import { PortfolioPage } from "../pages/PortfolioPage";
import { RegisterPage } from "../pages/RegisterPage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/cadastro" element={<RegisterPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/carteira" element={<PortfolioPage />} />
          <Route path="/investimentos/novo" element={<NewInvestmentPage />} />
          <Route path="/carteira/importar" element={<ImportPortfolioPage />} />
          <Route path="/analises" element={<AnalysisPage />} />
          <Route path="/simulador-historico" element={<HistoricalSimulatorPage />} />
          <Route path="/ativos" element={<AssetsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
