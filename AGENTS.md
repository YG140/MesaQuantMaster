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
