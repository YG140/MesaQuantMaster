import { http, HttpResponse } from "msw";

const api = "http://127.0.0.1:8000";

export const handlers = [
  http.post(`${api}/auth/login`, async () =>
    HttpResponse.json({ access_token: "test-token", token_type: "bearer" }),
  ),
  http.post(`${api}/auth/register`, async () =>
    HttpResponse.json({
      id: "user-1",
      name: "Ana Quant",
      email: "ana@example.com",
      is_active: true,
      is_superuser: false,
      created_at: "2026-07-15T00:00:00",
    }, { status: 201 }),
  ),
  http.get(`${api}/users/me`, ({ request }) => {
    if (!request.headers.get("Authorization")) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    return HttpResponse.json({
      id: "user-1",
      name: "Ana Quant",
      email: "ana@example.com",
      is_active: true,
      is_superuser: false,
      created_at: "2026-07-15T00:00:00",
    });
  }),
  http.get(`${api}/dashboard`, () =>
    HttpResponse.json({
      patrimonio_total: "521.00",
      valor_investido: "521.00",
      lucro_prejuizo: "0",
      rentabilidade: "0",
      ativos: 2,
      operacoes: 2,
      caixa: "0",
      proventos: "0",
      market_data_status: "live",
      quote_updated_at: "2026-07-16T18:30:00Z",
      unpriced_symbols: [],
    }),
  ),
  http.get(`${api}/portfolio`, () =>
    HttpResponse.json({
      total_invested: "521.00",
      total_market_value: "521.00",
      total_profit: "0",
      profitability: "0",
      allocation: [{ ticker: "PETR4", allocation: "71.05" }],
      valuation_basis: "market_value",
      market_data_status: "live",
      quote_updated_at: "2026-07-16T18:30:00Z",
      unpriced_symbols: [],
      positions: [
        {
          asset_id: "asset-1",
          ticker: "PETR4",
          asset_name: "Petrobras PN",
          quantity: "10",
          average_price: "37.10",
          invested_amount: "371.00",
          current_price: "38.42",
          market_value: "384.20",
          unrealized_profit: "13.20",
          unrealized_profit_percent: "3.55",
          allocation: "71.05",
          weight: "71.05",
          valuation_basis: "market_value",
          valuation_status: "live",
          quote_updated_at: "2026-07-16T18:30:00Z",
        },
      ],
    }),
  ),
  http.get(`${api}/operations`, () =>
    HttpResponse.json([
      {
        id: "op-1",
        asset_id: "asset-1",
        brokerage_id: "brokerage-1",
        operation_type: "BUY",
        operation_date: "2026-07-15",
        quantity: "10",
        unit_price: "37.10",
        fees: "1",
        taxes: "0",
        notes: null,
      },
    ]),
  ),
  http.get(`${api}/brokerages`, () =>
    HttpResponse.json([
      {
        id: "brokerage-1",
        name: "XP",
        is_active: true,
        created_at: "2026-07-15T00:00:00",
        updated_at: "2026-07-15T00:00:00",
      },
    ]),
  ),
  http.post(`${api}/brokerages`, async ({ request }) => {
    const body = await request.json() as { name?: string };
    if (!body.name?.trim()) {
      return HttpResponse.json({ detail: "Informe o nome da corretora." }, { status: 400 });
    }
    if (body.name.trim().toLowerCase() === "xp") {
      return HttpResponse.json({ detail: "Corretora ja cadastrada." }, { status: 400 });
    }
    return HttpResponse.json({
      id: "brokerage-new",
      name: body.name.trim(),
      user_id: "user-1",
      is_active: true,
      created_at: "2026-07-15T00:00:00",
      updated_at: "2026-07-15T00:00:00",
    }, { status: 201 });
  }),
  http.get(`${api}/market/search`, ({ request }) => {
    const query = new URL(request.url).searchParams.get("q") ?? "";
    const assets = [
      {
        ticker: "PETR4",
        symbol: "PETR4",
        name: "Petrobras PN",
        long_name: "Petroleo Brasileiro S.A.",
        asset_type: "Ação",
        asset_subtype: "PN",
        sector: "Energia",
        subsector: "Petroleo",
        country: "Brasil",
        exchange: "B3",
        currency: "BRL",
        logo_url: "https://example.com/petr4.png",
        current_price: "38.42",
        change_percent: "1.10",
        last_updated: "2026-07-16T18:30:00Z",
        updated_at: "2026-07-16T18:30:00Z",
        provider: "BRAPI",
        limited_mode: false,
      },
    ];
    return HttpResponse.json(query.toLowerCase().includes("petro") || query === "PETR4" ? assets : []);
  }),
  http.post(`${api}/portfolio/investments`, () =>
    HttpResponse.json({ asset_id: "asset-1", operation_id: "op-1", asset_created: true }, { status: 201 }),
  ),
  http.post(`${api}/portfolio/import-initial`, () =>
    HttpResponse.json({ operations_created: 1, assets_created: 1 }, { status: 201 }),
  ),
  http.get(`${api}/intelligence/portfolio`, () =>
    HttpResponse.json({
      policy: {
        id: "policy-1",
        user_id: "user-1",
        name: "Minha estratégia",
        objective: "crescimento patrimonial",
        risk_profile: "moderado",
        investment_horizon: "longo prazo",
        monthly_contribution: "900",
        liquidity_need: "média",
        income_need: false,
        emergency_reserve_months: 6,
        maximum_weight_per_asset: "20",
        maximum_weight_per_sector: "30",
        maximum_weight_per_issuer: "30",
        rebalance_tolerance: "5",
        allocations: [
          {
            id: "allocation-1",
            asset_class: "Ações",
            target_percentage: "60",
            minimum_percentage: "50",
            maximum_percentage: "70",
            enabled: true,
          },
          {
            id: "allocation-2",
            asset_class: "Tesouro Direto",
            target_percentage: "40",
            minimum_percentage: "30",
            maximum_percentage: "50",
            enabled: true,
          },
        ],
        created_at: "2026-07-16T18:30:00Z",
        updated_at: "2026-07-16T18:30:00Z",
      },
      overview: {
        current_equity: "521.00",
        total_invested: "521.00",
        profit_loss: "0",
        profitability: "0",
        received_income: null,
        investments_count: 1,
        fixed_income_percentage: "0",
        variable_income_percentage: "100",
        portfolio_classification: "Carteira em formação",
        risk_level: "Alto",
        data_quality: "Boa",
        last_updated_at: "2026-07-16T18:30:00Z",
        market_data_status: "live",
        insufficient_data_message: "Dados insuficientes para calcular.",
      },
      diagnosis: {
        portfolio_score: "56.67",
        risk_level: "Alto",
        diversification_score: "20.00",
        concentration_score: "50.00",
        liquidity_score: null,
        income_score: null,
        data_quality: "Boa",
        warnings: ["Há concentração relevante em uma única posição."],
        strengths: ["Carteira possui posições consolidadas."],
        weaknesses: ["Há concentração relevante em uma única posição."],
        class_allocations: [
          {
            asset_class: "Ações",
            current_value: "521.00",
            current_percentage: "100",
            target_percentage: "60",
            minimum_percentage: "50",
            maximum_percentage: "70",
            difference_percentage: "-40",
            status: "Acima da estratégia",
          },
          {
            asset_class: "Tesouro Direto",
            current_value: "0",
            current_percentage: "0",
            target_percentage: "40",
            minimum_percentage: "30",
            maximum_percentage: "50",
            difference_percentage: "40",
            status: "Abaixo da estratégia",
          },
        ],
        unclassified_assets: [],
        calculated_at: "2026-07-16T18:30:00Z",
      },
      recommendations: [
        {
          asset_id: "asset-1",
          symbol: "Ações",
          name: "Ações",
          asset_class: "Ações",
          recommendation: "Reduzir exposição",
          valuation_status: "Dados insuficientes",
          confidence: "Média",
          current_weight: "71.05",
          target_weight: "20",
          current_value: "384.20",
          suggested_value: null,
          positive_reasons: ["Posição cadastrada na carteira."],
          risk_reasons: ["Peso atual acima de 50% da carteira."],
          missing_data: [],
          indicators: [
            {
              name: "Cotação atual",
              status: "disponível",
              value: "38.42",
              explanation: "Preço usado para calcular valor de mercado.",
            },
          ],
          generated_at: "2026-07-16T18:30:00Z",
          data_updated_at: "2026-07-16T18:30:00Z",
        },
      ],
      rebalancing: [
        {
          asset_class: "Ações",
          current_percentage: "100",
          target_percentage: "60",
          difference_percentage: "-40",
          current_value: "521.00",
          target_value: "312.60",
          suggested_contribution: "0",
          missing_value: "0",
          excess_value: "208.40",
          status: "Acima da estratégia",
          explanation: "Classe acima da política; evite novos aportes por enquanto.",
        },
        {
          asset_class: "Tesouro Direto",
          current_percentage: "0",
          target_percentage: "40",
          difference_percentage: "40",
          current_value: "0",
          target_value: "208.40",
          suggested_contribution: "900.00",
          missing_value: "208.40",
          excess_value: "0",
          status: "Abaixo da estratégia",
          explanation: "Classe abaixo da política; priorize novos aportes.",
        },
      ],
      opportunities: [
        {
          asset_class: "Ação",
          classification: "Dados insuficientes",
          indicators: [],
          highlight_reason: "Não há dados suficientes para destacar oportunidades com segurança.",
          risks: ["Aguarde integração de indicadores específicos da classe."],
          confidence: "Baixa",
          updated_at: "2026-07-16T18:30:00Z",
        },
      ],
      available_indicators: { Ação: ["P/L", "P/VP"] },
      unavailable_indicators: { Ação: ["ROE", "Dividend yield"] },
      generated_at: "2026-07-16T18:30:00Z",
    }),
  ),
  http.get(`${api}/intelligence/policy`, () =>
    HttpResponse.json({
      id: "policy-1",
      user_id: "user-1",
      name: "Minha estratégia",
      objective: "crescimento patrimonial",
      risk_profile: "moderado",
      investment_horizon: "longo prazo",
      monthly_contribution: "900",
      liquidity_need: "média",
      income_need: false,
      emergency_reserve_months: 6,
      maximum_weight_per_asset: "20",
      maximum_weight_per_sector: "30",
      maximum_weight_per_issuer: "30",
      rebalance_tolerance: "5",
      allocations: [
        {
          id: "allocation-1",
          asset_class: "Ações",
          target_percentage: "60",
          minimum_percentage: "50",
          maximum_percentage: "70",
          enabled: true,
        },
        {
          id: "allocation-2",
          asset_class: "Tesouro Direto",
          target_percentage: "40",
          minimum_percentage: "30",
          maximum_percentage: "50",
          enabled: true,
        },
      ],
      created_at: "2026-07-16T18:30:00Z",
      updated_at: "2026-07-16T18:30:00Z",
    }),
  ),
  http.put(`${api}/intelligence/policy`, async ({ request }) => {
    const body = await request.json() as { allocations?: unknown[] };
    return HttpResponse.json({
      ...body,
      id: "policy-1",
      user_id: "user-1",
      created_at: "2026-07-16T18:30:00Z",
      updated_at: "2026-07-16T18:30:00Z",
    });
  }),
  http.post(`${api}/intelligence/build-portfolio`, () =>
    HttpResponse.json({
      class_allocations: [
        {
          asset_class: "Ações",
          percentage: "60",
          amount: "6000.00",
          explanation: "Distribuição baseada na sua política de investimentos salva.",
        },
        {
          asset_class: "Tesouro Direto",
          percentage: "40",
          amount: "4000.00",
          explanation: "Distribuição baseada na sua política de investimentos salva.",
        },
      ],
      selections: [
        {
          asset_class: "Ações",
          message: "A seleção dos investimentos de cada classe será feita quando houver dados suficientes e critérios específicos integrados.",
          data_status: "indisponível",
        },
      ],
      generated_at: "2026-07-16T18:30:00Z",
    }),
  ),
  http.get(`${api}/assets`, () => HttpResponse.json([])),
  http.post(`${api}/backtesting/run`, () =>
    HttpResponse.json({
      final_equity: "10300",
      total_return_percent: "3",
      benchmark_return_percent: null,
      excess_return_percent: null,
      max_drawdown_percent: "1",
      total_fees: "0",
      trades_count: 1,
      win_rate_percent: "100",
      equity_curve: [],
      trades: [],
    }),
  ),
];

export const server = setupServer(...handlers);

import { setupServer } from "msw/node";
