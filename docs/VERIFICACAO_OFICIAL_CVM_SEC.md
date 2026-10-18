# Verificação oficial de dados — CVM (Brasil) e SEC EDGAR (EUA)

## O que esta melhoria faz

Nova API protegida pelo login `GET /intelligence/official-verification/{symbol}` retorna demonstrações e metadados rastreáveis **sem modificar indicadores do motor, notas de qualidade, recomendações, ordens, posições ou o Neon**.

**Brasil / ações:** usa o vínculo CNPJ/CVM já existente e as contas financeiras fixas, consolidadas e reportadas previamente importadas via DFP/ITR. Exibe valor, conceito, período, versão, código da conta, data de referência e momento de importação. Não faz scraping e não compara fatos financeiros com cotações B3.

**Brasil / FIIs:** usa vínculo ao CNPJ do fundo e, quando existir, apresenta a última taxa de vacância física do informe trimestral CVM previamente importado, na unidade `ratio`. Não cria dados de rendimento ou de P/VP.

**EUA / ações:** quando ativo `international` em USD e bolsa cadastrada `NASDAQ`, `NYSE` ou `NYSE AMERICAN`, com CIK explícito, consulta a SEC:
1. `https://data.sec.gov/submissions/CIK##########.json` para confirmar que CIK, ticker e bolsa correspondem;
2. `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` para buscar conceitos publicados da taxonomia US-GAAP em **USD**, com formulários e datas de publicação declaradas (10-K/10-Q/20-F/40-F, inclusive emendas).

Métricas nesta primeira etapa: `assets`, `equity`, `revenue`, `net_income`. Não mistura USD com BRL, ano com trimestre, identidade de empresa com ticker coincidente ou cotação atual com demonstração oficial.

## Configuração SEC — gratuita, respeitando limites

Defina no **backend**, nunca no APK/frontend, um contato verdadeiro e identificável:

```ini
SEC_USER_AGENT="MesaQuantMaster SeuContatoReal@SeuDominio.com"
```

Sem isso, o endpoint retorna `not_configured` e **não executa consulta SEC**. Não invente email, contato ou identidades. SEC exige User-Agent identificado, solicita acesso moderado e limita o tráfego automatizado (orientação oficial: até 10 requisições por segundo, agregadas por usuário). O aplicativo faz no máximo duas chamadas por CIK, armazena respostas por 1 hora, usa somente endpoints fixos HTTPS de `data.sec.gov`, timeout e tamanho máximo, sem seguir redirecionamentos. Essa versão é para testes e uso individual, não para execução massiva ou serviço de alta frequência.

Documentação SEC:
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/about/developer-resources

## Usar a API

Para `EXEM3` brasileiro (requer CNPJ vinculado e documento CVM já sincronizado):

```text
GET /intelligence/official-verification/EXEM3
Authorization: Bearer <seu-token>
```

Para uma ação americana cadastrada, com CIK oficial fornecido pelo usuário:

```text
GET /intelligence/official-verification/EXM?cik=320193
Authorization: Bearer <seu-token>
```

Os símbolos e dados acima são **apenas exemplos**. O serviço recusará combinações de CIK/ticker/bolsa diferentes das publicadas pela SEC. Não deduz um CIK a partir do nome ou da semelhança de tickers.

Estados retornados:
- `verified_filing`: emissor vinculado e pelo menos um fato financeiro validado com documento oficial;
- `not_linked`: sem CNPJ ou CIK explicitamente resolvido;
- `identity_mismatch`: ticker, bolsa e/ou CIK não correspondem ao cadastro oficial;
- `no_data`: emissor encontrado, mas indicador desta primeira etapa ausente ou não aplicável;
- `not_configured`: User-Agent SEC ausente;
- `source_unavailable`: fonte offline, limite, formato inválido ou falha de rede.

**Importante:** `verified_filing` NÃO comprova que preço, recomendação, preço justo ou retorno são bons. Não atribuir `confidence=high` pelo simples êxito de leitura da SEC/CVM.

## Restrição B3 e escopo internacional

A B3 tem canais oficiais de dados de negociação e políticas próprias de acesso/licenciamento. Não há nesta PR crawling de páginas B3 nem feed de bolsa americano pago. Para cotações continuam os adaptadores autorizados já existentes (BRAPI Free, Twelve Data com plano válido etc.), sempre identificando se dado é fechamento ou intradiário.

A SEC é regulador de demonstrações, **não uma bolsa e não uma fonte de preço de negociação**. As informações oficiais de outras bolsas/reguladores internacionais demandarão adaptadores próprios e verificação de licenças. Cripto/Tesouro/ETFs internacionais ficam fora desta rota nesta etapa e retornam HTTP 422 (sem dado fabricado).

## Implantação

Mudança sem migração, sem novas tabelas, sem mexer em carteiras/contas e sem ativação automática de ordens. Requer integração da PR e eventual configuração SEC_USER_AGENT no backend. Testes de integração usam HTTP simulado, sem atingir produção ou usar dados reais de investimento.

**Próximas etapas:** comparar os fatos oficiais com indicadores normalizados de mesmo conceito/unidade/período e bloquear apenas conflitos efetivamente demonstrados; armazenar CIK validado por emissor e proveniência de cada pesquisa; estender a mais classes e jurisdições.
