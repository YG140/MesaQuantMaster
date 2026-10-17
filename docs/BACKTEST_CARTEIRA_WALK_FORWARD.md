# Validação histórica walk-forward — primeira versão (SIMULAÇÃO)

## Estado atual

Novo endpoint autenticado `POST /backtesting/portfolio-walk-forward`.
**Não compra, vende, salva dados do usuário, altera a carteira, consulta provedores nem autentica o histórico enviado.**
A resposta sempre inclui `"validation_status": "simulation_only"`.

O objetivo é verificar coerência do cálculo sem confundir resultado de cenários fornecidos pelo cliente com acerto real das recomendações. **Ainda NÃO está demonstrado que o MesaQuantMaster escolhe as melhores ações.**

## O que já faz

- Analisa cronologicamente janelas consecutivas, **somente ações da B3 em BRL**, usando o SmartPortfolioEngine e o filtro de compras da PR #74.
- Cada janela carrega o Perfil/Request registrado **na época**, o universo e snapshots dos candidatos calculados com dados disponíveis até a decisão.
- Rejeita data de cotação, coleta ou referência de indicador, tentativa de resolução, cálculo do snapshot, data de valuation e registro do perfil **posteriores à decisão**.
- Rejeita datas sem fuso, períodos futuros, janelas sobrepostas/com lacunas, benchmark descontínuo, cotações históricas com mais de 7 dias e retorno de ativo selecionado ausente.
- Usa, *após a seleção*, índices positivos de retorno total ajustado para cada papel, com dividendos e eventos societários embutidos, e para o benchmark.
- Usa pesos **executáveis** do motor, respeita o caixa não alocado e computa retorno líquido de uma taxa informada em basis points (`fee_bps`) aplicada ao giro em cada rebalanceamento.
- Compara retorno percentual total, retorno do benchmark, diferença em pontos percentuais, evolução do capital, giro, custos, períodos positivos e **drawdown amostrado nas datas de avaliação**.
- As posições evoluem entre janelas e o custo considera mudança de pesos após a valorização/depreciação; resultados são determinísticos com `Decimal`.

## Insumo exigido e origem dos dados

Cada elemento de `periods` contém:

- `decision_at`, `evaluation_at`, `profile_recorded_at` (com fuso)
- `request`: BuildPortfolioRequest original da data da decisão (a API substitui apenas `available_amount` pelo patrimônio simulado na abertura)
- `candidates`: cada candidato inclui um `AssetIntelligenceSnapshot` completo já produzido na data, além de `sector`, `issuer` e `market_context="B3"`
- `realized_returns`: símbolos e pares `start_index/end_index` **de retorno total ajustado**, timestamps de observação e nome da fonte
- `benchmark`: `name`, índices de retorno total da janela, timestamps e fonte

Dados futuros de resultado nunca são passados ao SmartPortfolioEngine. A API verifica datas declaradas, mas **não consegue confirmar que os números ou essas datas são verdadeiros**. Citar uma fonte no JSON não é autenticação de provedor. O histórico de snapshots em tempo real do programa não está ligado automaticamente a este novo endpoint.

### Exemplo mínimo de invocação

```python
from app.engines.portfolio_walk_forward_engine import PortfolioWalkForwardEngine
from app.schemas.portfolio_validation import WalkForwardRequest

# Monte payload apenas com snapshots realmente datados na época da decisão
# e séries independentes de índices de retorno total ajustados verificados.
# Sem esse histórico, NÃO execute backtest nem exiba métricas estimadas.
request = WalkForwardRequest.model_validate(payload)
report = PortfolioWalkForwardEngine.run(request)
assert report.validation_status == "simulation_only"
```

## Limitações e cuidados importantes

1. **Sem teste fora da amostra autenticado**, sem proteção independente contra mudanças retrospectivas no universo (survivorship bias), sem registro imutável de versões de modelo, sem registro autenticado da data real da divulgação financeira.
2. O programa recebe snapshots já pontuados na época, mas ainda não **reexecuta o pipeline inteiro de indicadores a partir de fontes oficiais arquivadas**; não é validação independente do ranking.
3. A simulação exige série de índice ajustado (total return): preços sem ajustes e sem proventos não são suficientes.
4. Taxa percentual de transação simulada; tributos, slippage, spread, restrições operacionais e custos de custódia não estão modelados. Benchmark **bruto de custos**; isso deve ser considerado ao comparar.
5. Giro e pesos representam modelo de rebalanceamento entre janelas, não execução real na bolsa. O drawdown pode subestimar perdas intraperíodo.
6. Sem coleta automática, o resultado deve continuar rotulado **simulação**, ainda que positivo; lucros passados não garantem lucros futuros.

## Próximo passo para validação verdadeira

Criar dataset imutável de snapshots, prova de publicação, histórico ajustado desde a data da decisão e universo point-in-time com identificadores independentes. Rodar janelas de treino/teste **fora da amostra**, verificar custos e impostos, comparar com benchmark com metodologia equivalente e documentar critérios previamente fixados. Só depois se pode considerar evidência de desempenho. A issue #75 documenta a trilha de validação completa.

## Testes

```bash
PYTHONPATH=backend pytest -q \
  tests/unit/test_portfolio_walk_forward_engine.py \
  tests/integration/test_portfolio_walk_forward_api.py \
  tests/unit/test_smart_portfolio_engine.py \
  tests/unit/test_stock_purchase_eligibility.py
```

São testes com preços, índices e tickers **sintéticos**, NÃO dados reais.
