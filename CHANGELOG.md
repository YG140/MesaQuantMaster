# Changelog

## v0.9.0 - Backtesting Engine

- Criado `BacktestingEngine` puro para simulacao long-only de um unico ativo.
- Adicionado endpoint autenticado `POST /backtesting/run`.
- Suportados sinais diretos `BUY`, `SELL` e `HOLD`.
- Adicionada integracao inicial com `StrategyEngine` para estrategia `momentum`.
- Implementados custos fixos e percentuais por operacao com impacto em caixa,
  resultado, patrimonio e retorno.
- Implementadas curva patrimonial, trades fechados, drawdown maximo, benchmark
  buy-and-hold, excesso de retorno e taxa de acerto.
- Criados testes unitarios e de integracao para o Backtesting Engine.
- Documentados contrato, limitacoes e comandos de validacao da sprint 9.0.

## v0.8.1 - Estabilizacao e Testes do Nucleo

- Criados testes unitarios para `PortfolioEngine`, `ScannerEngine` e `RiskEngine`.
- Criado teste de integracao para `GET /portfolio` com SQLite isolado e override de autenticacao.
- Corrigidos avisos do Ruff em `backend/app`.
- Corrigidas anotacoes avaliadas em tempo de import quando metodos `list` sombreavam o builtin `list`.
- Instalado `python-multipart` no venv local para permitir import das rotas FastAPI durante os testes.
- Documentadas as regras de preco medio, vendas, ordem cronologica e taxas.

## v0.8.1.1 - Fechamento e Higiene

- Venda acima da posicao passou a lancar erro explicito em vez de limitar silenciosamente.
- Corrigidos defaults `datetime.utcnow()` nos models para callables com `datetime.now(timezone.utc)`.
- Banco SQLite residual de teste passou a ser ignorado no `.gitignore`.

## v0.8.0 - Refatoracao Arquitetural do Portfolio

- Centralizados os calculos financeiros de carteira no `PortfolioEngine`.
- Services de portfolio, scanner, risco e dashboard foram simplificados para orquestracao.
- Criado `AGENTS.md` com regras permanentes de arquitetura.
