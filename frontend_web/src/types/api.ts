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
