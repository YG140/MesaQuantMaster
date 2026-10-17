# Auditoria de preços históricos COTAHIST — etapa 3 do MesaQuantMaster

## O que foi implementado

O backtest da PR #80 recebe séries ajustadas e snapshots informados pelo cliente. Esta etapa acrescenta um **auditor local de preços históricos da B3** que confronta os preços de cada snapshot com o campo **PREULT** de um ZIP COTAHIST (arquivo anual ou diário) fornecido pelo usuário.

O programa reutiliza o parser COTAHIST existente no projeto: valida nomes, header/trailer, contagem de registros, layout fixo, limites de ZIP, mercado à vista, tipo do papel, moeda e fator de cotação, sem interromper a leitura antes de terminar a verificação. Compara preço em `Decimal`, sem arredondamento de divergências.

### Origem e uso permitido

**Este recurso não busca, baixa, rastreia nem contorna restrições de coleta no site da B3**. Os arquivos são obtidos separadamente pelo usuário, pelos meios e condições de acesso permitidos. Não inclua dados de bolsa proprietários no repositório. A B3 informa que o COTAHIST é não ajustado por dividendos e outros eventos e possui termos próprios de uso.

Informações oficiais sobre o layout:
- https://www.b3.com.br/
- https://b3.com.br/data/files/C8/F3/08/B4/297BE410F816C9E492D828A8/SeriesHistoricas_Layout.pdf

### Como usar (offline, no computador)

1. Construa um `WalkForwardRequest` JSON como documentado em `docs/BACKTEST_CARTEIRA_WALK_FORWARD.md`, contendo dados realmente conhecidos nas datas de decisão.
2. Obtenha legalmente um ou mais ZIPs anuais COTAHIST cobrindo os pregões das cotações que aparecem em cada snapshot.
3. Execute, dentro do diretório do projeto:

```bash
PYTHONPATH=backend python backend/scripts/audit_b3_historical_prices.py \
  --request backtest-historico.json \
  --archive COTAHIST_A2024.ZIP \
  --archive COTAHIST_A2025.ZIP \
  --output auditoria-cotacoes.json
```

O utilitário recusa inconsistências e não produz relatório parcial em caso de falha. Nenhuma conexão de rede, banco de dados ou operação na carteira é necessária.

### O que significa o resultado

- `status = "source_price_checks_only"`: preço e pregão do snapshot batem com arquivo local no formato COTAHIST, **não** que o ganho previsto é comprovado.
- `sha256`: impressão digital **dos bytes da cópia auditada**; útil para reprodução, mas **não prova que o arquivo veio da B3**, nem quando foi publicado.
- `archive_sha256`, `trading_date`, `isin`, `close_price`, `quote_factor`: evidências da correspondência.
- `price_adjusted_for_events = false`: nenhuma correção por proventos, agrupamentos, desdobramentos ou inflação. É **incorreto** calcular retorno total apenas dividindo essas cotações.

Para reduzir antecipação de informações, a auditoria rejeita o fechamento do mesmo pregão da decisão, pois não conseguimos provar a hora em que o arquivo foi disponibilizado.

### Limitações ainda não resolvidas

- A auditoria comprova correspondência estrutural dos registros fornecidos, **não a autenticidade criptográfica da publicação** nem seu momento efetivo.
- O motor de backtest continua exigindo **índices de retorno total ajustados por proventos/eventos societários** de fonte independentemente verificável. Os preços COTAHIST brutos não podem substituí-los.
- A origem, o conhecimento histórico e a hora de publicação de cada indicador CVM, universo de empresas (inclusive as deslistadas), perfil de investimento e versões do algoritmo **ainda não foram auditados externamente**.
- A auditoria é offline e não está ligada automaticamente ao fluxo da API ou ao APK. A versão publicada do programa permanece intacta.
- **Nenhum resultado real de acurácia ou rentabilidade foi medido nesta etapa.** Os testes usam ZIPs sintéticos com o mesmo formato estrutural COTAHIST.

### Próximo passo

Acrescentar uma série de eventos corporativos e proventos devidamente datados, com fonte verificável, e um processo de arquivamento imutável de snapshots na data de cada recomendação. Só então a simulação poderá migrar gradualmente de `simulation_only` para um relatório histórico auditável, sempre evidenciando limitações e vieses.

### Executar testes

```bash
PYTHONPATH=backend pytest -q \
  tests/unit/test_b3_historical_price_audit.py \
  tests/unit/test_portfolio_walk_forward_engine.py \
  tests/integration/test_portfolio_walk_forward_api.py
```
