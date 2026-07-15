# Testes

## Como Executar

```powershell
python -m compileall backend/app
ruff check backend/app tests
black --check backend/app tests
pytest
```

## Cobertura Criada na Sprint 9.0

### BacktestingEngine

- Serie vazia.
- Capital inicial zero ou negativo.
- Preco invalido.
- Datas fora de ordem.
- Datas duplicadas.
- Nenhuma operacao.
- Compra e venda com lucro.
- Compra e venda com prejuizo.
- Custos fixos.
- Custos percentuais.
- Posicao aberta no encerramento.
- `BUY` duplicado enquanto ja comprado.
- `SELL` sem posicao.
- Calculo de patrimonio final.
- Curva patrimonial.
- Drawdown maximo.
- Taxa de acerto.
- Benchmark buy-and-hold.
- Excesso de retorno.
- Estrategia momentum com janela pequena.
- Resultado deterministico para a mesma entrada.

### Integracao

- `POST /backtesting/run` usa override de autenticacao existente.
- O teste envia serie pequena e deterministica.
- Valida status HTTP, patrimonio final, numero de operacoes, curva patrimonial
  e metricas principais.

## Cobertura Criada na Sprint 8.1

### PortfolioEngine

- Compra unica.
- Compras multiplas com taxas e impostos.
- Venda parcial.
- Venda total.
- Venda acima da posicao.
- Garantia de que venda acima da posicao nao altera o estado valido da posicao.
- Ordem cronologica.
- Taxas e impostos no custo.
- Multiplos ativos.
- Carteira vazia.

### RiskEngine

- Concentracao calculada via `PortfolioEngine`.
- Alerta de concentracao.
- Carteira vazia.
- Quantidade de posicoes via `PortfolioEngine`.
- Patrimonio total via `PortfolioEngine`.

### ScannerEngine

- Preco acima do alvo.
- Preco abaixo do alvo.
- Preco igual ao alvo retorna falso para ambas as regras.
- Reutilizacao de dados calculados pelo `PortfolioEngine`.
- Ausencia de metodos duplicados de patrimonio ou concentracao.

### Integracao

- `GET /portfolio` cria usuario, ativo e operacao em banco SQLite isolado.
- A autenticacao e sobrescrita por dependencia de teste.
- O teste valida status HTTP, quantidade, preco medio, valor investido e estrutura da resposta.

## Banco de Teste

Os testes usam `sqlite:///./.pytest_cache/test_mesa_quant_master.db`, configurado em `tests/conftest.py`, sem acessar o banco de desenvolvimento.

## Resultado Atual

```text
collected 44 items
44 passed
```

Comandos validados:

```text
python -m compileall backend/app -> aprovado
ruff check backend/app tests -> aprovado
black --check backend/app tests -> aprovado
pytest -> 44 testes coletados, 44 aprovados
```
