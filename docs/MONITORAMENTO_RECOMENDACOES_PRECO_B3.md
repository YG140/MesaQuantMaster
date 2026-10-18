# Medição honesta do desempenho das recomendações

## Objetivo

Consultar o histórico **imutável** de cada montagem de carteira e acompanhar a **variação bruta de preços** de uma carteira hipotética, com a bolsa B3 como fonte. O programa não registra transações reais, não modifica posições e não inventa proventos, custos, desdobramentos ou um resultado líquido.

## Endpoint

`GET /intelligence/recommendation-history/{run_id}/performance?horizon_months=0`

`horizon_months` aceita **0** (observação mais recente), **3**, **6** ou **12**. Requer autenticação normal; um usuário nunca consulta histórico de outro. O registro original é conferido por SHA-256 antes da avaliação. A API não escreve no banco.

- `pending`: o período ainda não acabou ou ainda não existe pregão posterior.
- `unavailable`: não existe evidência verificável completa e consistente; os percentuais ficam nulos.
- `price_only`: variação **bruta de preço não ajustada**, observável em fechamentos oficiais B3, de uma carteira hipotética sem alterações ou novos aportes. **Não** é resultado de investimento real, nem retorno total líquido.

## Fontes e condições

- COTAHIST diário B3 (arquivos públicos, sem chave paga), cotações não ajustadas. Ler/validar cada arquivo por inteiro e analisar todos os símbolos do dia no mesmo lote, evitando uma requisição por ativo. A janela é limitada a até 7 datas por comparação, com timeouts curtos e cache do provedor B3.
- O ponto inicial é o pregão comum **anterior ao dia da recomendação**, para impedir usar um fechamento posterior a uma decisão feita durante a sessão. O ponto final é um pregão comum até o horizonte fechado, nunca uma data futura.
- A quantidade simulada provém do histórico da decisão. Exigir preço de referência, valor executável coerente, data da cotação original, ticker B3 de negociação, identidade ISIN estável, mesma versão de distribuição, moeda BRL e cotação da fonte oficial. Divergências interrompem o cálculo.
- `BOVA11` é apenas um **proxy de preço** negociado na B3. A comparação com a variação do ETF não equivale ao Ibovespa de retorno total, CDI ou um benchmark de retorno total.
- Um ativo de renda fixa sem preço B3 ou uma carteira mista com elementos não conciliáveis resulta em `unavailable` **para a medição**, mas continua disponível para gerenciar a carteira real.
- Dividendos/JCP, impostos, corretagem, custo de custódia, subscrições, desdobramentos, reajustes e slippage **não são quantificados sem extratos oficiais e dados de eventos**. A resposta sempre mantém `total_return_status=not_calculated` e `realized_profit_status=not_calculated`.

## Garantias

Nenhuma alteração de tabela ou de saldo, operações, usuários, perfis, recomendações antigas ou frontend. Endpoint de leitura com autenticação existente. Sem tarefa recorrente em background; a consulta calcula o resultado quando solicitada. O objetivo é permitir construir, em etapa posterior, trilha de resultados totais baseada em proventos e eventos oficiais, sem transformar variação de preço em promessa de rentabilidade.

Testes sintéticos cobrem isolamento entre usuários, hash adulterado, horizonte futuro, cotações ausentes, identidade ISIN, número de distribuição, títulos incompatíveis, fontes misturadas, cálculo de variação e benchmark BOVA11.
