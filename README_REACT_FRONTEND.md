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
```

Nao versionar `.env` real, tokens, senhas ou chaves.

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

- O `BrapiProvider` ainda usa catalogo e precos simulados.
- O preco atual exibido no cadastro e demonstrativo, nao cotacao real.
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
