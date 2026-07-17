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
        asset_type: "Acao",
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
