import { apiRequest } from "../apiClient";
import type {
  Asset,
  AssetIntelligenceSnapshot,
  BacktestingRequest,
  BacktestingResult,
  BatchAssetAnalysisResponse,
  Brokerage,
  BuildPortfolioRequest,
  BuildPortfolioResponse,
  WealthGoalSetting,
  FinancialFutureResponse,
  DashboardSummary,
  InitialPortfolioImport,
  InvestmentCreate,
  MarketAsset,
  MacroIndicatorSnapshot,
  ProviderCapabilities,
  AIAgentChatRequest,
  AIAgentChatResponse,
  MarketQuote,
  Operation,
  OperationUpdate,
  PositionDeleteResponse,
  PortfolioSummary,
  PortfolioIntelligence,
  PortfolioPolicy,
  PortfolioPolicyPayload,
} from "../../types/api";

export const endpoints = {
  dashboard: (token: string) => apiRequest<DashboardSummary>("/dashboard", { token }),
  portfolio: (token: string) => apiRequest<PortfolioSummary>("/portfolio", { token }),
  operations: (token: string) => apiRequest<Operation[]>("/operations", { token }),
  positionOperations: (token: string, assetId: string) =>
    apiRequest<Operation[]>(`/portfolio/positions/${assetId}/operations`, { token }),
  updateOperation: (token: string, operationId: string, payload: OperationUpdate) =>
    apiRequest<Operation>(`/operations/${operationId}`, { method: "PATCH", token, body: payload }),
  deleteOperation: (token: string, operationId: string) =>
    apiRequest<void>(`/operations/${operationId}`, { method: "DELETE", token }),
  deletePosition: (token: string, assetId: string, ticker: string, expectedOperations: number) =>
    apiRequest<PositionDeleteResponse>(`/portfolio/positions/${assetId}`, {
      method: "DELETE",
      token,
      body: { ticker, expected_operations: expectedOperations },
    }),
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
  usdBrlReference: (token: string) =>
    apiRequest<{
      pair: "USD/BRL";
      rate_brl_per_usd: string;
      quoted_at: string;
      source: string;
      indicative_only: boolean;
      disclaimer: string;
    }>("/market/fx/usd-brl", { token }),
  marketQuotes: (token: string, symbols: string[]) =>
    apiRequest<{ quotes: MarketQuote[]; unavailable_symbols: string[] }>(
      "/market/quotes",
      { method: "POST", token, body: { symbols } },
    ),
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
  portfolioIntelligence: (token: string) =>
    apiRequest<PortfolioIntelligence>("/intelligence/portfolio", { token, timeoutMs: 35_000 }),
  portfolioPolicy: (token: string) =>
    apiRequest<PortfolioPolicy | null>("/intelligence/policy", { token }),
  financialGoal: (token: string) =>
    apiRequest<WealthGoalSetting | null>("/intelligence/financial-goal", { token }),
  saveFinancialGoal: (token: string, amount: string) =>
    apiRequest<WealthGoalSetting>("/intelligence/financial-goal", {
      method: "PUT", token, body: { wealth_goal_amount: amount },
    }),
  financialFuture: (token: string) =>
    apiRequest<FinancialFutureResponse | null>("/intelligence/financial-future", { token, timeoutMs: 35_000 }),
  savePortfolioPolicy: (token: string, payload: PortfolioPolicyPayload) =>
    apiRequest<PortfolioPolicy>("/intelligence/policy", {
      method: "PUT",
      token,
      body: payload,
    }),
  buildPortfolio: (token: string, payload: BuildPortfolioRequest) =>
    apiRequest<BuildPortfolioResponse>("/intelligence/build-portfolio", {
      method: "POST",
      token,
      body: payload,
      timeoutMs: 120_000,
    }),
  assetIntelligence: (token: string, symbol: string) =>
    apiRequest<AssetIntelligenceSnapshot>(
      `/intelligence/assets/${encodeURIComponent(symbol)}`,
      { token },
    ),
  analyzeAssets: (token: string, symbols: string[]) =>
    apiRequest<BatchAssetAnalysisResponse>("/intelligence/assets/analyze", {
      method: "POST",
      token,
      body: { symbols },
    }),
  portfolioMarketRecommendations: (token: string) =>
    apiRequest<BatchAssetAnalysisResponse>(
      "/intelligence/portfolio/recommendations",
      { token },
    ),
  macroContext: (token: string) =>
    apiRequest<MacroIndicatorSnapshot[]>("/intelligence/macro", { token }),
  providerCapabilities: (token: string) =>
    apiRequest<ProviderCapabilities>("/market/provider-capabilities", { token, timeoutMs: 60_000 }),
  aiAgentChat: (token: string, payload: AIAgentChatRequest) =>
    apiRequest<AIAgentChatResponse>("/ai-agent/chat", {
      method: "POST",
      token,
      body: payload,
      timeoutMs: 45_000,
    }),
};
