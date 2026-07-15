# Mesa Quant Master v0.8.1 - Estabilizacao e Testes do Nucleo

## Objetivo

Validar a centralizacao dos calculos financeiros no `PortfolioEngine`, corrigir residuos de lint/imports e criar testes automatizados para o nucleo da plataforma.

## Regras Validadas

- Compras aumentam quantidade e custo investido.
- Taxas e impostos entram no custo da compra.
- O preco medio e calculado por custo investido dividido pela quantidade.
- Vendas parciais reduzem quantidade e custo investido proporcionalmente, preservando o preco medio.
- Vendas totais removem a posicao consolidada da carteira.
- Vendas acima da posicao geram erro explicito, informando quantidade disponivel e solicitada.
- Operacoes sao processadas em ordem cronologica, mesmo quando chegam fora de ordem.
- Ativos diferentes sao consolidados de forma independente.
- Carteira vazia retorna totais zerados e listas vazias.

## Arquivos Alterados

- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/strategy.py`
- `tests/conftest.py`
- `tests/unit/test_portfolio_engine.py`
- `tests/unit/test_risk_engine.py`
- `tests/unit/test_scanner_engine.py`
- `tests/integration/test_portfolio_api.py`
- `CHANGELOG.md`
- `README_SPRINT_8_1.md`
- `TESTES.md`

## Validacoes

Comandos obrigatorios:

```powershell
python -m compileall backend/app
ruff check backend/app
pytest
```

Resultados executados nesta sprint:

- `python -m compileall backend/app`: aprovado.
- `ruff check backend/app`: aprovado, sem avisos.
- `pytest`: 19 testes coletados, 19 aprovados.

Aviso residual:

- O pytest exibe 6 `DeprecationWarning` do SQLAlchemy relacionados ao uso de `datetime.utcnow()` em defaults de models. A sprint nao alterou models porque nao havia necessidade funcional.
