import { apiRequest } from "../apiClient";
import type {
  Asset,
  BacktestingRequest,
  BacktestingResult,
  Brokerage,
  DashboardSummary,
  InitialPortfolioImport,
  InvestmentCreate,
  MarketAsset,
  Operation,
  PortfolioSummary,
} from "../../types/api";

export const endpoints = {
  dashboard: (token: string) => apiRequest<DashboardSummary>("/dashboard", { token }),
  portfolio: (token: string) => apiRequest<PortfolioSummary>("/portfolio", { token }),
  operations: (token: string) => apiRequest<Operation[]>("/operations", { token }),
  brokerages: (token: string) => apiRequest<Brokerage[]>("/brokerages", { token }),
  createBrokerage: (token: string, name: string) =>
    apiRequest<Brokerage>("/brokerages", {
      method: "POST",
      token,
      body: { name },
    }),
  marketSearch: (token: string, query: string) =>
    apiRequest<MarketAsset[]>(
      `/market/search?q=${encodeURIComponent(query)}&limit=8`,
      { token },
    ),
  marketAsset: (token: string, code: string) =>
    apiRequest<MarketAsset>(`/market/assets/${encodeURIComponent(code)}`, { token }),
  addInvestment: (token: string, payload: InvestmentCreate) =>
    apiRequest<{ asset_id: string; operation_id: string; asset_created: boolean }>(
      "/portfolio/investments",
      { method: "POST", token, body: payload },
    ),
  importPortfolio: (token: string, payload: InitialPortfolioImport) =>
    apiRequest<{ operations_created: number; assets_created: number }>(
      "/portfolio/import-initial",
      { method: "POST", token, body: payload },
    ),
  assets: (token: string) => apiRequest<Asset[]>("/assets", { token }),
  createAsset: (token: string, payload: {
    ticker: string;
    name: string;
    asset_type: string;
    sector: string | null;
    country: string | null;
    currency: string;
    exchange: string | null;
  }) => apiRequest<Asset>("/assets", { method: "POST", token, body: payload }),
  runSimulation: (token: string, payload: BacktestingRequest) =>
    apiRequest<BacktestingResult>("/backtesting/run", {
      method: "POST",
      token,
      body: payload,
    }),
};
