# Mesa Quant Master - Guia Permanente do Codex

## Arquitetura

A plataforma segue a cadeia:

```text
API
 -> Service
 -> Engine
 -> Repository
 -> Database
```

Regras de responsabilidade:

- API apenas recebe dependencias, chama services e devolve schemas.
- Service apenas orquestra: busca dados, monta entradas e chama engines.
- Engine contem regras de negocio e calculos; nao acessa banco nem APIs externas.
- Repository acessa banco de dados.
- Provider acessa APIs externas.
- Chaves de providers externos ficam apenas no backend e nunca devem ser
  expostas em frontend, OpenAPI de resposta, logs ou bundle.

## Carteira

`PortfolioEngine` e o nucleo dos calculos financeiros da plataforma.

Todo calculo de carteira deve ficar nele, incluindo:

- patrimonio total
- valor investido
- lucro e prejuizo
- rentabilidade
- alocacao
- concentracao
- quantidade de posicoes
- peso de cada ativo
- consolidacao de posicoes a partir das operacoes

`PortfolioService` deve buscar operacoes e ativos, chamar `PortfolioEngine` e retornar o resultado.
Quando houver cotacoes de mercado, `PortfolioService` deve busca-las em lote via
`MarketService` e entregar os precos ao `PortfolioEngine`; nunca fazer N+1 por
ativo e nunca chamar provider dentro do engine.

## Scanner

`ScannerEngine` deve conter apenas regras de scanner, como comparacoes de preco e filtros.

Nao calcular no scanner:

- patrimonio
- alocacao
- concentracao
- lucro
- preco medio

Quando o scanner precisar de dados de carteira, usar `PortfolioEngine`.

## Risco

`RiskEngine` deve conter apenas regras de risco, como limites e alertas.

Dados como patrimonio, alocacao, concentracao e quantidade de posicoes devem vir de `PortfolioEngine`.

## Estrategias

`StrategyEngine` deve conter apenas regras de estrategias.

Nao calcular patrimonio, alocacao, concentracao ou preco medio em estrategias.

## Refatoracao

Ao alterar o projeto:

- nao criar funcionalidades novas sem pedido explicito
- preservar endpoints publicos sempre que possivel
- evitar breaking changes em schemas
- nao alterar models sem necessidade
- remover codigo morto e imports nao utilizados
- preferir compatibilidade e mudancas pequenas
- executar testes existentes ao final

## Frontend React

O frontend web proprio vive em `frontend_web/`.

Regras:

- manter o Streamlit em `frontend/` congelado como prototipo temporario enquanto a migracao estiver ativa
- novas funcionalidades de interface devem ser feitas em `frontend_web/`
- remover o Streamlit somente apos confirmacao de paridade funcional
- React acessa apenas endpoints FastAPI por HTTP/JSON
- React nao acessa banco, repositories, engines ou providers diretamente
- React nao replica calculos financeiros
- autenticacao do React fica centralizada em AuthProvider/useAuth/ProtectedRoute
- dados simulados de mercado devem ser informados claramente na interface
- dados reais de mercado devem sempre sair do backend; o frontend nunca conhece
  URL externa da BRAPI nem `BRAPI_API_KEY`
- nao versionar `.env`, tokens, senhas, bancos locais, caches ou `node_modules`
