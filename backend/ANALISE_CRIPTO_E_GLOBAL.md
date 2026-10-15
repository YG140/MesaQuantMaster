# Análise para criptomoedas, ativos internacionais, ETFs e BDRs

## O que mudou
- O programa **não pode mais converter a porcentagem de disponibilidade de
  dados em pontuação de investimento** para nenhuma dessas quatro classes.
  Sem métricas numéricas confiáveis, a nota fica `null`.
- O motor avalia indicadores específicos com data de referência, status
  `available`, confiança e fonte conhecida. Dados de usuário marcados como
  `manual` e números vencidos **não** criam notas artificiais.
- Os grupos da política do investidor (Criptomoedas, Ativos internacionais,
  BDRs e ETFs) passam a participar do ajuste da estratégia conforme suas
  alocações persistidas.

## Critérios por classe
| Classe | Qualidade | Risco | Liquidez e custos | Valuation |
| --- | --- | --- | --- | --- |
| Cripto | Sem nota de qualidade sem métricas de rede verificadas | Volatilidade, máxima queda histórica e concentração de detentores | Spread bid-ask | **Não há preço justo estabelecido** |
| Ações internacionais | ROE, ROA, ROIC; crescimento | Índices financeiros e volatilidade se disponíveis | Spread | P/L, P/VP, EV/EBITDA e eventual referência de pares da **mesma moeda e classe** |
| ETFs | Taxa de administração, tracking difference | Tracking error, volatilidade, drawdown, concentração | Spread | Prêmio/desconto ao valor patrimonial **quando publicado** |
| BDRs | Indicadores comprovados da empresa subjacente quando publicados | Exposição e concentração; risco cambial permanece necessário | Spread | **Sem correspondência confirmada entre moeda, paridade e fundamento, não inventar preço justo** |

## Bloqueios deliberados de recomendações automáticas
1. O pedido de montagem de carteira é em BRL. Um ativo cujo preço tem moeda
   diferente de BRL não pode ser convertido com uma taxa imaginária:
   a seleção é bloqueada até implementar conversão FX com taxa, data, fonte
   e regras de custos. Isso vale também para criptoativos cotados em USD.
2. **Cripto** pode exibir indicadores de risco, mas não recebe recomendação de
   compra automática enquanto faltarem critérios consistentes de custódia,
   segurança e avaliação de preço.
3. **BDRs e ações internacionais** sem faixa de avaliação de preço verificável
   não entram em aportes automáticos. Para internacional, uma referência
   relativa setorial só é possível com no mínimo três emissores distintos,
   todos na mesma classe e na mesma moeda; não é preço justo intrínseco.
4. ETFs exigem dados efetivos de custo/estrutura, risco, spread e
   prêmio/desconto; um preço ou volume sozinho não classifica o fundo como
   oportunidade. Se todos os elementos estão disponíveis, o motor considera
   a análise como uma **possibilidade de avaliar compra**, não uma ordem.
5. A política confirmada do usuário e os limites por classe/ativo/setor
   permanecem mandatórios, inclusive para ativos de alto risco.

## Provedores e escopo
- Os endpoints atuais continuam usando as integrações configuradas do
  programa. O catálogo passa a aceitar múltiplos de empresas internacionais
  e dados setoriais **quando o provedor realmente os entrega**.
- O resolver inclui aliases somente de campos cujo nome especifica
  explicitamente unidade percentual, para não confundir fração com pontos
  percentuais (por exemplo: `volatilityPercent`).
- **Não foi adicionado um serviço público de cotações de cripto ou bolsa
  estrangeira neste patch.** A BRAPI e outros provedores existentes podem
  não cobrir determinado ticker. Falta disponibilidade real = falta de nota.
  Integrações novas dependerão de credenciais, cobertura e validação de
  licenciamento, símbolos, datas e moeda.
- Dados históricos de volatilidade, tracking e drawdown precisam chegar
  efetivamente da origem; nunca são gerados a partir da variação de um dia.
- A infraestrutura de APK continua independente desta melhoria e depende
  de hospedagem HTTPS real do backend.

## Próximas evoluções antes de recomendação automática completa
Implementar conectores de preços/históricos dos mercados exteriores,
identidade imutável de criptomoedas por rede/contrato (não apenas ticker),
taxa FX verificada BRL/USD com timestamp e spread, riscos de custódia,
emissores/ativos subjacentes BDR por CNPJ e razão, pesquisa de pares mais
ampla e validação das faixas por dados fora da amostra.
