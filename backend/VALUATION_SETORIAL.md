# Benchmark setorial e referência relativa de preço

Esta implementação substitui a falsa equivalência entre cobertura dos dados e
qualidade dos ativos por um benchmark **observacional** dentro do universo
analisado. O programa não inventa preços ou informações externas.

## O que ela calcula

1. Para cada ação, busca **outros** emissores do mesmo setor (e do mesmo
   segmento, quando identificado), com a mesma moeda. Deduplica ações do
   mesmo emissor. Exige pelo menos **três** pares distintos elegíveis.
2. Com indicadores `AVAILABLE`, datas de referência e validade coerentes,
   compara ROE, ROA, ROIC, P/L, P/VP, dívida líquida/PL e crescimento de receita
   (quando cada índice tem pelo menos três pares válidos).
3. A mediana dos P/L e P/VP dos pares é multiplicada pelo LPA e VPA
   positivos **do ativo analisado**, respectivamente:

   ```text
   referência_por_lucro = LPA_do_ativo * mediana_PL_pares
   referência_por_patrimônio = VPA_do_ativo * mediana_PVP_pares
   faixa = [mínimo(referências), máximo(referências)]
   ```

4. Recusa a faixa se o preço de mercado não é recente (até 7 dias), os
   dados de LPA/VPA são insuficientes/não positivos, os múltiplos não são
   comparáveis ou as duas estimativas discordam mais de 50%.
5. Um preço 20% abaixo do limite inferior classifica a ação como
   relativamente atrativa; 20% acima do superior indica preço elevado.
   Isso **não autoriza uma compra automaticamente**: a confiança e a
   qualidade financeira seguem necessárias, além do perfil/limites da
   carteira. No restante da faixa, não há sinal de compra.
6. As diferenças setoriais alteram as notas existentes no máximo 15 pontos
   por categoria; não criam notas para dados ausentes. O baseline é guardado
   para evitar ajustes duplicados quando o mesmo ativo é analisado duas vezes.

## Limites e medidas de proteção

- **Não é cálculo de valor justo intrínseco**, nem valuation auditado. Não
  considera fluxo de caixa descontado, estrutura de capital detalhada,
  custo de capital, ciclos de commodities, qualidade dos lucros, preço
  futuro, governança ou recuperação de crises.
- O universo analisado pode não representar o setor inteiro, introduzindo
  *viés de seleção*. Uma faixa numérica não significa que o mercado está
  precificando mal o ativo.
- Bancos, seguradoras, holdings e o setor financeiro genérico não recebem
  essa faixa: exigem modelos próprios e pares homogêneos.
- Indicadores manuais não são tratados como benchmarks independentes. Dados
  inválidos, não atuais, sem data, ou de empresas diferentes não entram.
- O motor não acessa sites não licenciados ou faz raspagem do Status Invest.
- Quando não houver pares e indicadores suficientes, apresenta diagnóstico
  de insuficiência em vez de gerar preço artificial.

## Próximos níveis de precisão

Um valor justo intrínseco requer demonstrações financeiras plurianuais,
fluxos de caixa e premissas transparentes com intervalos e cenários;
modelo próprio por setor, histórico de valuation e avaliação de robustez
fora da amostra. Não foram implementados por este patch.

## Arquivos relevantes

- `backend/app/engines/sector_relative_valuation.py`
- `backend/app/services/market_intelligence_service.py`
- `backend/app/services/intelligence_service.py`
- `frontend_web/src/pages/PortfolioIntelligencePage.tsx`
- `tests/unit/test_sector_relative_valuation.py`
