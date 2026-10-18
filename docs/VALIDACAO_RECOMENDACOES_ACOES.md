# Validação das recomendações de ações — etapa 1

Este documento separa **qualidade dos dados** de **mérito financeiro de uma compra**.
Uma nota alta de cobertura NÃO representa probabilidade alta de ganho.

## Regra aplicada à montagem de NOVOS aportes em ações

A ação só entra como sugestão de novo aporte quando TODAS estas condições são atendidas:

1. Identidade do ativo e pilares essenciais já passam pela elegibilidade geral.
2. Confiança de dados do ativo é pelo menos média, sem bloqueio explícito de qualidade.
3. A recomendação atual é `analyze_to_buy` (analisar antes de comprar), não `hold`, `wait` ou `review_data`.
4. A avaliação é `attractive` / `very_attractive`, consistente com o detalhe de valuation.
5. A avaliação tem método e confiança pelo menos média, faixa numérica válida e data verificável.
6. Cotação e avaliação têm no máximo 7 dias em relação à análise, sem data futura incompatível.
7. A cotação fica pelo menos 20% abaixo do limite INFERIOR da faixa relativa estimada (nunca só abaixo da média).

Se falhar, o ativo aparece nas **exclusões com motivo**, e o montador NÃO transfere o dinheiro liberado automaticamente para uma ação fraca. A carteira pode ser parcial ou indisponível. Posições já possuídas permanecem registradas e avaliadas separadamente, sem venda automática. Não há ordem de bolsa executada por este filtro.

Este é um filtro **conservador e provisório**; usa a avaliação comparativa setorial já existente, que requer pares independentes e indicadores financeiros verificáveis. Não representa valor justo intrínseco, probabilidade de valorização, garantia de lucro ou aconselhamento individualizado. A reserva de emergência e os limites por perfil/classe/setor continuam vigentes.

## O que esta alteração NÃO valida ainda

O repositório dispõe de backtesting de operações, mas **não demonstrou o desempenho histórico das carteiras produzidas pelo SmartPortfolioEngine**. Não informar percentuais de acerto, retorno esperado ou confiança de acerto com base somente em testes unitários.

Critérios para a etapa de validação financeira antes de autonomia:

- Congelar snapshots de recomendação com **dados conhecidos na data** (sem look-ahead), data de cotação, universo de ativos e provedores disponíveis; identificar survivorship bias.
- Fazer simulação **walk-forward** e fora da amostra por pelo menos múltiplos regimes de mercado; separar períodos de ajuste de parâmetros e períodos de avaliação.
- Incluir custos, impostos aplicáveis, eventos societários, dividendos, liquidez, spread e possibilidade de não executar.
- Comparar carteira integral com benchmark adequado (p.ex. Ibovespa/IBOV para ações brasileiras, além de uma carteira passiva simples), respeitando aportes e datas.
- Relatar retorno líquido, volatilidade, drawdown máximo, estabilidade, concentração, giro, percentagem de meses positivos e resultados em janelas distintas.
- Testar limites setoriais específicos, bancos/seguradoras, commodities cíclicas e cenário de dados faltantes ou contraditórios.
- **Reprovar** recomendações que dependam de informações divulgadas apenas depois da data simulada.
- Só elevar a classificação de confiança comercial após medir resultados fora da amostra e documentar limitações e critérios objetivos de aceite.

## Regressões automatizadas

`tests/unit/test_stock_purchase_eligibility.py` cobre a regra de abstenção.
`tests/unit/test_smart_portfolio_engine.py` cobre limites de alocação e carteira existente.
`tests/unit/test_sector_relative_valuation.py` valida a construção da faixa de referência com pares reais no universo de teste.

Execute:

```bash
PYTHONPATH=backend pytest -q tests/unit/test_stock_purchase_eligibility.py tests/unit/test_smart_portfolio_engine.py tests/unit/test_sector_relative_valuation.py
```

Esses testes checam coerência do software, **não** o sucesso de investimento.