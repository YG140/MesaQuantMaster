# Frontend React - Mesa Quant Master

Esta sprint cria o primeiro frontend web proprio em `frontend_web/`. A partir
desta versao, React e o frontend oficial para novas evolucoes do produto.

O frontend Streamlit em `frontend/` esta congelado como prototipo temporario.
Novas funcionalidades devem ser feitas em `frontend_web/`. A remocao do
Streamlit ocorrera somente apos confirmacao de paridade funcional.

## Arquitetura

React + TypeScript consome apenas HTTP/JSON do FastAPI. O backend continua sendo
a autoridade para autenticacao, carteira, calculos financeiros, simulador,
providers e persistencia.

```text
frontend_web React
  -> FastAPI
  -> Services
  -> Engines / Repositories
  -> Banco e Providers
```

## Stack

- React, TypeScript e Vite
- React Router
- TanStack Query
- React Hook Form e Zod
- Recharts para graficos leves em React
- Lucide React para icones
- Vitest, React Testing Library, MSW
- Playwright para navegacao real

## Execucao

Backend:

```powershell
cd C:\Dev\MesaQuantMaster\backend
python -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd C:\Dev\MesaQuantMaster\frontend_web
npm install
npm run dev
```

Abra `http://localhost:5173`.

## Configuracao

`frontend_web/.env.example`:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

`backend/.env.example` inclui:

```text
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
BRAPI_BASE_URL=https://brapi.dev
BRAPI_API_KEY=
BRAPI_TIMEOUT_SECONDS=10
BRAPI_QUOTE_CACHE_SECONDS=60
BRAPI_SEARCH_CACHE_SECONDS=600
BRAPI_PROFILE_CACHE_SECONDS=3600
```

Nao versionar `.env` real, tokens, senhas ou chaves.
`BRAPI_API_KEY` fica somente no backend. Nunca configure a chave como `VITE_*`.

## Dados Reais de Mercado

O backend consulta a API brapi.dev pelos endpoints v2:

- `GET /api/v2/tickers`
- `GET /api/v2/stocks/quote`
- `GET /api/v2/stocks/profile`

Sem token, o backend informa modo limitado e nao retorna dados simulados como
fallback. Em rate limit, timeout ou indisponibilidade, as telas exibem mensagens
claras e permitem cadastro manual.

O cache em memoria usa TTL curto: cotacoes por 60 segundos, pesquisa por 10
minutos e perfil por 1 hora. O cache nao armazena erros.

Na tela Adicionar investimento, "Ultima cotacao disponivel" e diferente de
"Preco de compra". O preco de compra so e preenchido quando o usuario aciona
"Usar esta cotacao como preco de compra".

Carteira e Dashboard usam cotacoes em lote. Se parte dos ativos ficar sem
cotacao, a carteira continua disponivel, marca status parcial e usa o valor
investido como base de alocacao para posicoes sem preco.

## Autenticacao

O frontend usa temporariamente JWT Bearer em memoria com restauracao por
`sessionStorage`. A sessao e centralizada em `AuthProvider`, `useAuth` e
`ProtectedRoute`. Respostas `401` limpam sessao e redirecionam para `/login`.

Uma sprint futura de seguranca deve substituir esse armazenamento temporario por
cookie HttpOnly.

## Rotas

- `/login`
- `/cadastro`
- `/`
- `/carteira`
- `/investimentos/novo`
- `/carteira/importar`
- `/analises`
- `/simulador-historico`
- `/ativos`

Todas as rotas exceto login e cadastro sao privadas.

## Limitacoes

- Dividendos, historico, noticias e fundamentos completos ainda nao foram
  implementados.
- A fonte externa pode limitar cobertura por plano e por ausencia de token.
- O Streamlit ainda existe em `frontend/` durante a migracao, congelado como
  prototipo temporario.
- A geracao automatica de tipos via OpenAPI esta documentada em
  `npm run api:types`, mas ainda nao foi ativada.
- O bundle inicial tem aviso de chunk grande; code splitting fica para uma
  sprint de otimizacao.

## Testes

```powershell
cd frontend_web
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

Os testes usam MSW/Playwright com mocks controlados e nao dependem da internet
real para dados de mercado.
