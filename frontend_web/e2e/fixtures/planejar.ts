export const policy = {
  id: "policy-1", user_id: "user-1", name: "Estratégia determinística",
  objective: "crescimento patrimonial", risk_profile: "moderado",
  investment_horizon: "longo prazo", monthly_contribution: "900",
  liquidity_need: "média", income_need: false, emergency_reserve_months: 6,
  maximum_weight_per_asset: "60", maximum_weight_per_sector: "70",
  maximum_weight_per_issuer: "60", rebalance_tolerance: "5",
  allocations: [{ id: "allocation-1", asset_class: "Ações", target_percentage: "100", minimum_percentage: "80", maximum_percentage: "100", enabled: true }],
  created_at: "2026-08-30T12:00:00Z", updated_at: "2026-08-30T12:00:00Z",
};

export const response = {
  class_allocations: [{ asset_class: "Ações", percentage: "100", amount: "10000", explanation: "Conforme a política confirmada." }],
  selections: [{ asset_class: "Ações", message: "Classe compatível com a política.", data_status: "available" }],
  assets: [
    {
      symbol: "PETR4", name: "Petrobras PN", asset_class: "Ações", sector: "Energia", issuer: "B3:PETR4",
      recommended_percentage: "50", recommended_amount: "5000", score: "82", confidence: "medium",
      reasons: ["Preço atualizado e fundamentos disponíveis."], risks: ["Oscilação de mercado."],
      missing_data: ["Cobertura de analistas ausente."], reference_price: "37.42",
      executable_quantity: "133", executable_amount: "4976.86", effective_percentage: "49.77",
      target_gap: "23.14", execution_impediments: [], trading_symbol: null,
      economic_identity: "PETR4", market_segment: "mixed", quantity_step: "1",
      indicators_used: [
        { key: "current_price", label: "Preço atual", value: "37.42", unit: "currency", status: "available", unavailable_reason: null, source: "BRAPI", source_type: "provider", reference_date: "2026-08-30T12:00:00Z", valid_until: "2026-08-31T12:00:00Z", freshness_status: "current" },
        { key: "dividend_yield", label: "Dividend Yield", value: "10.24", unit: "percentage", status: "available", unavailable_reason: null, source: "CVM", source_type: "official", reference_date: "2026-06-30T12:00:00Z", valid_until: "2026-09-30T12:00:00Z", freshness_status: "current" },
      ],
    },
    {
      symbol: "VALE3", name: "Vale ON", asset_class: "Ações", sector: "Mineração", issuer: "B3:VALE3",
      recommended_percentage: "50", recommended_amount: "5000", score: "76", confidence: "high",
      reasons: ["Cobertura obrigatória e indicadores atuais disponíveis."], risks: ["Exposição a commodities."],
      missing_data: [], reference_price: "64.92", executable_quantity: "77", executable_amount: "4998.84",
      effective_percentage: "49.99", target_gap: "1.16", execution_impediments: [], trading_symbol: "VALE3F",
      economic_identity: "VALE3", market_segment: "fractional", quantity_step: "1",
      indicators_used: [{ key: "price_earnings", label: "P/L", value: "6.7", unit: "ratio", status: "available", unavailable_reason: null, source: "BRAPI", source_type: "provider", reference_date: "2026-08-30T12:00:00Z", valid_until: "2026-08-31T12:00:00Z", freshness_status: "current" }],
    },
  ],
  exclusions: [], total_allocated_percentage: "99.76", total_allocated_amount: "9975.70",
  unallocated_amount: "24.30", confidence: "medium", status: "available", missing_data: ["Cobertura de analistas ausente."],
  strategy_summary: "Carteira educacional alinhada à política confirmada.",
  diagnosis: { phase: "accumulation", estimated_monthly_capacity: "900", reserve_months_covered: "6", reserve_target: "18000", debt_alerts: [], liquidity_assessment: "adequate", missing_data: [], priority_actions: ["Manter aportes."], confidence: "high" },
  contribution_plan: [],
  projections: [{ name: "central", annual_appreciation_rate: "5", annual_income_rate: "3", total_contributed: "10000", projected_wealth: "15000", estimated_appreciation: "4000", estimated_income: "1000", estimated_periodic_income: "80", real_projected_wealth: "14000", projected_without_reinvestment: "14500" }],
  freedom_goal: { desired_monthly_income: "5000", required_wealth: "1500000", current_wealth: "10000", gap: "1490000", achieved_percentage: "0.67", estimated_years: null, withdrawal_rate: "4", safety_margin: "20", risks: [], improvement_actions: ["Aportar com regularidade."], confidence: "medium" },
  disclaimer: "Simulação educacional, não constitui ordem de compra e não garante retorno.", generated_at: "2026-08-30T12:00:00Z",
};
