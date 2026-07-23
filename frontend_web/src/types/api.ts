export type User = {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
};

export type Brokerage = {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type MarketAsset = {
  ticker: string;
  symbol?: string | null;
  name: string | null;
  long_name?: string | null;
  asset_type: string | null;
  asset_subtype?: string | null;
  sector: string | null;
  subsector?: string | null;
  country: string | null;
  exchange: string | null;
  currency: string | null;
  logo_url?: string | null;
  current_price: string | null;
  change_value?: string | null;
  change_percent?: string | null;
  last_updated: string | null;
  updated_at?: string | null;
  provider: string;
  cache_hit?: boolean;
  limited_mode?: boolean;
};

export type MarketQuote = {
  ticker: string;
  symbol?: string | null;
  requested_symbol?: string | null;
  symbol_changed?: boolean;
  current_price: string | null;
  price?: string | null;
  previous_close?: string | null;
  change?: string | null;
  change_value?: string | null;
  change_percent?: string | null;
  currency: string;
  market_time?: string | null;
  provider?: string | null;
  cache_hit?: boolean;
  limited_mode?: boolean;
};

export type PortfolioPosition = {
  asset_id: string;
  ticker: string;
  asset_name: string;
  asset_type?: string | null;
  quantity: string;
  average_price: string;
  invested_amount: string;
  current_price: string | null;
  market_value: string | null;
  unrealized_profit: string | null;
  unrealized_profit_percent: string | null;
  allocation: string | null;
  weight: string | null;
  valuation_basis: string | null;
  valuation_status?: string | null;
  quote_updated_at?: string | null;
};

export type PortfolioSummary = {
  total_invested: string | number | null;
  total_market_value: string | number | null;
  total_profit: string | number | null;
  profitability: string | number | null;
  allocation: Array<{
    ticker?: string | null;
    asset?: string | null;
    name?: string | null;
    allocation?: string | number | null;
    weight?: string | number | null;
  }>;
  valuation_basis?: string | null;
  market_data_status?: "live" | "partial" | "unavailable" | string | null;
  quote_updated_at?: string | null;
  unpriced_symbols?: string[];
  positions?: PortfolioPosition[] | null;
};

export type DashboardSummary = {
  patrimonio_total?: string | number | null;
  valor_investido?: string | number | null;
  lucro_prejuizo?: string | number | null;
  rentabilidade?: string | number | null;
  ativos?: number | null;
  operacoes?: number | null;
  operations_count?: number | null;
  caixa?: string | number | null;
  proventos?: string | number | null;
  ultima_atualizacao?: string | null;
  market_data_status?: "live" | "partial" | "unavailable" | string | null;
  quote_updated_at?: string | null;
  unpriced_symbols?: string[];
};

export type Operation = {
  id: string;
  asset_id: string;
  brokerage_id: string | null;
  operation_type: "BUY" | "SELL";
  operation_date: string;
  quantity: string;
  unit_price: string;
  fees: string;
  taxes: string;
  notes: string | null;
  source?: string | null;
};

export type OperationUpdate = {
  brokerage_id: string | null;
  operation_type: "BUY" | "SELL";
  operation_date: string;
  quantity: string;
  unit_price: string;
  fees: string;
  taxes: string;
  notes: string | null;
};

export type PositionDeleteResponse = {
  asset_id: string;
  ticker: string;
  operations_deleted: number;
  message: string;
};

export type Asset = {
  id: string;
  ticker: string;
  name: string;
  asset_type: string;
  sector: string | null;
  country: string | null;
  currency: string;
  exchange: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type InvestmentCreate = {
  brokerage_id: string;
  ticker: string;
  name: string;
  asset_type: string;
  operation_date: string;
  quantity: string;
  unit_price: string;
  fees: string;
  taxes: string;
  notes: string | null;
};

export type InitialPortfolioImport = {
  brokerage_id: string;
  positions: Array<{
    ticker: string;
    name: string | null;
    asset_type: string;
    quantity: string;
    average_price: string;
    reference_date: string | null;
    notes: string | null;
  }>;
};

export type BacktestingRequest = {
  initial_capital: string;
  historical_data: Array<{ timestamp: string; close: string }>;
  signals?: Array<{ timestamp: string; signal: "BUY" | "SELL" | "HOLD" }>;
  strategy?: { name: string; moving_average_window: number };
  fee_percent: string;
  fixed_fee: string;
  benchmark_data?: Array<{ timestamp: string; close: string }>;
};

export type BacktestingResult = {
  final_equity: string;
  total_return_percent: string;
  benchmark_return_percent: string | null;
  excess_return_percent: string | null;
  max_drawdown_percent: string;
  total_fees: string;
  trades_count: number;
  win_rate_percent: string | null;
  equity_curve: Array<{ timestamp: string; equity: string }>;
  trades: Array<{
    entry_date: string;
    entry_price: string;
    exit_date: string | null;
    exit_price: string | null;
    quantity: string;
    net_profit: string;
    return_percent: string;
  }>;
};

export type IndicatorStatus = {
  name: string;
  status: string;
  value?: string | number | null;
  explanation: string;
};

export type IntelligenceRecommendation = {
  asset_id: string | null;
  symbol: string;
  name: string;
  asset_class: string;
  recommendation: string;
  valuation_status: string;
  confidence: string;
  current_weight: string | number | null;
  target_weight: string | number | null;
  current_value: string | number | null;
  suggested_value: string | number | null;
  positive_reasons: string[];
  risk_reasons: string[];
  missing_data: string[];
  indicators: IndicatorStatus[];
  generated_at: string;
  data_updated_at: string | null;
};

export type IntelligenceOverview = {
  current_equity: string | number | null;
  total_invested: string | number | null;
  profit_loss: string | number | null;
  profitability: string | number | null;
  received_income: string | number | null;
  investments_count: number;
  fixed_income_percentage: string | number | null;
  variable_income_percentage: string | number | null;
  portfolio_classification: string;
  risk_level: string;
  data_quality: string;
  last_updated_at: string | null;
  market_data_status: string;
  insufficient_data_message: string;
};

export type PortfolioDiagnosis = {
  portfolio_score: string | number | null;
  risk_level: string;
  diversification_score: string | number | null;
  concentration_score: string | number | null;
  liquidity_score: string | number | null;
  income_score: string | number | null;
  data_quality: string;
  warnings: string[];
  strengths: string[];
  weaknesses: string[];
  class_allocations: ClassAllocationDiagnosis[];
  unclassified_assets: string[];
  calculated_at: string;
};

export type ClassAllocationDiagnosis = {
  asset_class: string;
  current_value: string | number | null;
  current_percentage: string | number | null;
  target_percentage: string | number | null;
  minimum_percentage: string | number | null;
  maximum_percentage: string | number | null;
  difference_percentage: string | number | null;
  status: string;
};

export type AllocationSuggestion = {
  asset_class: string;
  current_percentage: string | number;
  target_percentage: string | number;
  difference_percentage: string | number;
  current_value: string | number;
  target_value: string | number;
  suggested_contribution: string | number;
  missing_value: string | number;
  excess_value: string | number;
  status: string;
  explanation: string;
};

export type Opportunity = {
  asset_class: string;
  classification: string;
  indicators: IndicatorStatus[];
  highlight_reason: string;
  risks: string[];
  confidence: string;
  updated_at: string | null;
};

export type PortfolioIntelligence = {
  overview: IntelligenceOverview;
  diagnosis: PortfolioDiagnosis;
  recommendations: IntelligenceRecommendation[];
  rebalancing: AllocationSuggestion[];
  opportunities: Opportunity[];
  policy: PortfolioPolicy | null;
  available_indicators: Record<string, string[]>;
  unavailable_indicators: Record<string, string[]>;
  generated_at: string;
};

export type PortfolioPolicyAllocation = {
  id?: string | null;
  asset_class: string;
  target_percentage: string | number;
  minimum_percentage: string | number;
  maximum_percentage: string | number;
  enabled: boolean;
};

export type PortfolioPolicy = {
  id: string;
  user_id: string;
  name: string;
  objective: string;
  risk_profile: string;
  investment_horizon: string;
  monthly_contribution: string | number;
  liquidity_need: string;
  income_need: boolean;
  emergency_reserve_months: number;
  maximum_weight_per_asset: string | number;
  maximum_weight_per_sector: string | number;
  maximum_weight_per_issuer: string | number;
  rebalance_tolerance: string | number;
  allocations: PortfolioPolicyAllocation[];
  created_at: string;
  updated_at: string;
};

export type PortfolioPolicyPayload = Omit<PortfolioPolicy, "id" | "user_id" | "created_at" | "updated_at">;

export type BuildPortfolioRequest = {
  available_amount: string;
  objective: string;
  horizon: string;
  risk_profile: string;
  needs_emergency_reserve: boolean;
  emergency_months: number;
  monthly_contribution: string;
  needs_income: boolean;
  needs_liquidity: boolean;
  volatility_tolerance: string;
  max_percentage_per_asset: string;
  max_percentage_per_class: string;
  max_percentage_per_sector: string;
  allowed_classes: string[];
};

export type BuildPortfolioResponse = {
  class_allocations: Array<{
    asset_class: string;
    percentage: string | number;
    amount: string | number;
    explanation: string;
  }>;
  selections: Array<{
    asset_class: string;
    message: string;
    data_status: string;
  }>;
  generated_at: string;
};

export type NormalizedIndicator = {
  key: string;
  label: string;
  description?: string | null;
  category?: string | null;
  layer?: string | null;
  value: string | number | null;
  display_value: string | null;
  unit: string;
  status: string;
  impact?: string | null;
  source: string;
  reference_date: string | null;
  collected_at: string;
  confidence: string;
  period: string | null;
  unavailable_reason: string | null;
  sector_comparison?: string | null;
  historical_comparison?: string | null;
  explanation?: string | null;
};

export type DataQualityReport = {
  data_quality_score: string | number | null;
  data_completeness: string | number;
  data_freshness: string | number;
  anomaly_flags: string[];
  missing_indicators: string[];
  non_applicable_indicators: string[];
  recommendation_blocked: boolean;
  blocking_reason: string | null;
};

export type AssetValuationAssessment = {
  status: string;
  methods: string[];
  used_indicators: string[];
  missing_indicators: string[];
  historical_comparison: string | null;
  peer_comparison: string | null;
  estimated_range_low: string | number | null;
  estimated_range_high: string | number | null;
  confidence: string;
  data_date: string | null;
};

export type AssetIntelligenceSnapshot = {
  asset_id: string | null;
  symbol: string;
  name: string | null;
  asset_class: string;
  current_price: string | number | null;
  currency: string | null;
  market_updated_at: string | null;
  indicators: NormalizedIndicator[];
  quality_score: string | number | null;
  valuation_score: string | number | null;
  income_score: string | number | null;
  growth_score: string | number | null;
  debt_score: string | number | null;
  risk_score: string | number | null;
  liquidity_score: string | number | null;
  data_quality_score: string | number | null;
  strategy_fit_score: string | number | null;
  overall_score: string | number | null;
  recommendation: string;
  valuation_status: string;
  valuation: AssetValuationAssessment;
  confidence: string;
  coverage_percentage: string | number;
  available_indicators_count: number;
  missing_indicators_count: number;
  stale_indicators_count: number;
  non_applicable_indicators_count: number;
  anomaly_flags: string[];
  data_quality: DataQualityReport | null;
  positive_reasons: string[];
  warning_reasons: string[];
  missing_data: string[];
  calculated_at: string;
};

export type BatchAssetAnalysisResponse = {
  snapshots: AssetIntelligenceSnapshot[];
  errors: Array<{ symbol: string; message: string }>;
  provider_calls: number;
  calculated_at: string;
};

export type MacroIndicatorSnapshot = {
  key: string;
  label: string;
  value: string | number | null;
  period: string | null;
  source: string;
  updated_at: string | null;
  frequency: string;
  history_available: boolean;
  state: string;
};

export type ProviderCapabilities = {
  provider: string;
  configured: boolean;
  reachable: boolean | null;
  supported_domains: string[];
  accessible_domains: string[];
  restricted_domains: string[];
  last_checked_at: string;
};
