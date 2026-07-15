# Mesa Quant Master v0.9.0 - Backtesting Engine

## Objetivo

Criar a primeira implementacao do Backtesting Engine, com escopo pequeno,
deterministico e extensivel. Esta versao executa backtests long-only de um
unico ativo, sem corretoras, banco de dados, providers externos ou persistencia.

## Arquitetura

A rota segue o fluxo:

```text
API -> Service -> Engine
```

- `backend/app/api/backtesting.py`: recebe o request autenticado e devolve o
  response.
- `backend/app/services/backtesting_service.py`: converte schemas em entradas do
  engine e resolve sinais diretos ou estrategia suportada.
- `backend/app/engines/backtesting_engine.py`: executa toda a simulacao de forma
  pura, sem banco, FastAPI, arquivos ou APIs externas.

## Contrato da API

Endpoint:

```http
POST /backtesting/run
```

Request minimo com sinais diretos:

```json
{
  "initial_capital": "1000",
  "historical_data": [
    {"timestamp": "2026-01-01T10:00:00", "close": "10"},
    {"timestamp": "2026-01-02T10:00:00", "close": "12"},
    {"timestamp": "2026-01-03T10:00:00", "close": "15"}
  ],
  "signals": [
    {"timestamp": "2026-01-01T10:00:00", "signal": "BUY"},
    {"timestamp": "2026-01-03T10:00:00", "signal": "SELL"}
  ],
  "fee_percent": "0",
  "fixed_fee": "0"
}
```

Request com estrategia momentum:

```json
{
  "initial_capital": "1000",
  "historical_data": [
    {"timestamp": "2026-01-01T10:00:00", "close": "10"},
    {"timestamp": "2026-01-02T10:00:00", "close": "11"},
    {"timestamp": "2026-01-03T10:00:00", "close": "12"}
  ],
  "strategy": {
    "name": "momentum",
    "moving_average_window": 2
  }
}
```

Response inclui:

```text
initial_capital
final_equity
total_return_percent
benchmark_return_percent
excess_return_percent
max_drawdown_percent
total_fees
trades_count
winning_trades
losing_trades
win_rate_percent
open_position
equity_curve
trades
```

## Regras Financeiras

- O engine usa `Decimal` para valores financeiros.
- `BUY` compra a posicao integral usando o caixa disponivel.
- `BUY` com posicao aberta e ignorado.
- `SELL` sem posicao aberta e ignorado.
- `SELL` com posicao aberta encerra a posicao integralmente.
- Custo percentual e tarifa fixa sao cobrados em cada compra e venda.
- Custos reduzem caixa, lucro liquido, patrimonio final e retorno total.
- Trades fechados registram lucro bruto, taxas, lucro liquido e retorno.
- A taxa de acerto considera apenas trades fechados.

## Curva Patrimonial

Cada ponto contem:

```text
timestamp
cash
position_value
equity
drawdown_percent
```

O drawdown e calculado pela queda percentual do patrimonio em relacao ao pico
historico observado ate o ponto.

## Benchmark

Quando `benchmark_data` e informado, o retorno do benchmark e o buy-and-hold do
primeiro ao ultimo preco. O inicio e o fim do benchmark devem estar alinhados
com a serie historica principal.

Quando `benchmark_data` nao e informado, o proprio ativo e usado como benchmark
buy-and-hold padrao.

## Posicao Aberta

Posicao aberta no encerramento e marcada a mercado pelo ultimo preco. Ela entra
em `final_equity` e `total_return_percent`, mas nao e registrada como trade
fechado e nao entra na taxa de acerto.

## Limitacoes

- Um unico ativo por execucao.
- Apenas long-only.
- Sem alavancagem.
- Sem venda a descoberto.
- Sem slippage.
- Sem impostos.
- Sem persistencia de resultados.
- Sem consulta a banco, corretora ou provider externo.

## Validacoes

Entradas invalidas geram erro explicito para:

- capital inicial zero ou negativo;
- serie historica vazia;
- preco menor ou igual a zero;
- datas duplicadas;
- datas fora de ordem;
- custos negativos;
- sinais fora da serie ou duplicados;
- estrategia nao suportada;
- uso simultaneo de sinais diretos e estrategia.

## Comandos

```powershell
python -m compileall backend/app
ruff check backend/app tests
black --check backend/app tests
pytest
```

