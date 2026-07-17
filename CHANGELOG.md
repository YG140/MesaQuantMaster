# Changelog

## v0.11.0 - Dados reais de mercado

- Substituido o catalogo simulado do `BrapiProvider` por chamadas HTTP reais aos
  endpoints v2 da brapi.dev.
- Adicionados `BRAPI_BASE_URL`, `BRAPI_API_KEY`, timeout e TTLs de cache ao
  backend.
- Criados cache em memoria, excecoes normalizadas de provider e cotacoes em
  lote via `POST /market/quotes`.
- Carteira e Dashboard passam a usar cotacoes em lote para precificacao,
  mantendo posicoes sem cotacao disponiveis com status parcial/indisponivel.
- Frontend React passou a exibir ultima cotacao disponivel, fonte, variacao,
  modo limitado, falhas de rate limit/timeout e botao "Atualizar cotacoes".
- Adicionados testes com mocks HTTP, sem dependencia de internet, e verificacao
  de que a chave BRAPI nao aparece no bundle.

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
# Unreleased

- Adicionado frontend MVP em Streamlit consumindo a API FastAPI via HTTP.
- Adicionados clientes HTTP centralizados para autenticacao, ativos, operacoes,
  carteira/dashboard e backtesting.
- Adicionados testes unitarios para formatadores e tratamento de erros do
  cliente HTTP do frontend.
# Frontend React inicial

- Criado `frontend_web/` com React, TypeScript, Vite, React Router e TanStack Query.
- Definido React como frontend oficial; Streamlit permanece congelado como
  prototipo temporario ate confirmacao de paridade funcional.
- Adicionado cliente HTTP centralizado com JWT Bearer, timeout e tratamento de erros.
- Implementadas telas de login, cadastro, dashboard, carteira, novo investimento,
  importacao, analises, simulador historico e ativos.
- Configurado CORS do FastAPI para origens explicitas do frontend web.
- Adicionados testes Vitest/MSW e Playwright para o novo frontend.
