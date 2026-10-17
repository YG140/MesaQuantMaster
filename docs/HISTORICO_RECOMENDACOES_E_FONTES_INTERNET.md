# Histórico de recomendações + estratégia de dados públicos da internet

## Registro automático de decisões

Cada chamada autenticada `POST /intelligence/build-portfolio` gera **um novo registro persistente** em `portfolio_recommendation_runs`, **mesmo quando nenhuma compra é considerada elegível**.

A resposta mantém todos os campos anteriores e acrescenta `history_id`.

Para consultar:

- `GET /intelligence/recommendation-history?limit=20&offset=0`: registros do usuário autenticado, paginação 1 a 100.
- `GET /intelligence/recommendation-history/{history_id}`: dados originais da decisão, também restritos ao usuário autenticado; registro inexistente ou de outro usuário retorna 404.

São salvos: horário gerado e horário gravado, versão lógica do motor, hash SHA-256 do JSON, perfil/política de alocação aplicados, universo considerado e truncamento, diagnóstico de falhas dos provedores, carteira prévia agregada, candidatos selecionados e exclusões, quantidade/valor executáveis, cotação e momento observado, razões/riscos e os **indicadores realmente utilizados**, incluindo valor, fonte, tipo da fonte, data de competência, data de coleta, validade, status e comparação setorial, quando disponíveis.

Não são persistidos: respostas completas do questionário, renda pessoal declarada, dívidas, senhas, tokens ou operações do usuário. A rota não cria ordens, não envia negociações e não altera posições nem saldos.

**Limites:** um hash dos bytes salvos detecta corrupção e alterações casuais. Não constitui assinatura de terceiro nem certifica horário de divulgação. A versão `smart_portfolio_engine-v1` identifica a família lógica do motor, não o hash imutável de uma versão de código: antes de usar como prova de backtest reproduzível, precisa persistir ID de build/commit e os snapshots COMPLETOS do universo. O histórico começa a ser produzido **a partir da implantação**, sem inventar recomendações anteriores.

A retenção é intencionalmente append-only pela API: não há endpoints de edição/deleção do histórico. A migração não altera dados da carteira e não apaga a tabela em rollback acidental. Um administrador do banco ainda pode modificá-la; não há WORM externo.

## Usar a internet no lugar de provedores comerciais?

Podemos consultar a internet, mas páginas web **também são servidas por servidores**, e pesquisa aberta/HTML não garante cobertura, atualidade, licença ou estrutura. A solução mais segura e barata é **fontes oficiais abertas + provedores gratuitos com cotas + pesquisa pública auxiliar supervisionada**, em vez de substituir a cadeia de dados por scraping indiscriminado.

| Classe | Preferir | Complementos / cautelas |
|---|---|---|
| Ações brasileiras | CVM DFP/ITR e dados societários oficiais, cotação legalmente autorizada | BRAPI Free para preço com limites; não estimar balanços via trecho de notícia |
| FIIs | CVM dados abertos de informes mensais/trimestrais, demonstrações e documentos Fundos.NET | Data/competência e apresentação oficial verificadas; P/VP exige cotação válida |
| Tesouro | Tesouro Transparente (CSV de taxas e preços) | Séries de preços/taxas não são promessa de retorno |
| Macro | BCB SGS e dados oficiais | Validar unidade, defasagem e revisões |
| Criptoativos | API pública ou demo com limites claramente documentados | Preço/volume não substituem risco de custódia e liquidez |
| Internacional | Dados de emissores/reguladores e feeds gratuitos quando autorizados | Dólar/BRL, bolsas, moeda e horários precisam de conversão e validação |

### Política de coleta recomendada

1. Manter catálogo de indicadores obrigatórios por classe, selecionar fontes autorizadas por indicador; só consultar a segunda fonte se primeira estiver ausente/fora da validade ou para conferência independente.
2. Para cada observação, gravar símbolo/identidade, indicador, unidade, valor, competência, publicação quando comprovada, coleta, URL/domínio, provedor, validade e versão do parser.
3. Rejeitar dados de emissor incerto, unidades inconsistentes, fontes conflitantes e valores sem data verificável. **Ausente não é zero** e notas de cobertura não são chance de ganho.
4. Cache no backend com TTL por indicador, limites de tamanho, timeouts, limites por fonte, controle de chamadas e aviso de quota; operação sem token pago quando possível.
5. Sites públicos de terceiros só como **pesquisa auxiliar com respeito a robots, termos e direitos sobre os dados**; não acessar atrás de login, CAPTCHA, barreiras de acesso ou proibições contratuais.
6. HTML pesquisado não deve elevar sozinho `confidence` nem resultar em `ANALYZE_TO_BUY`. Só um dado estruturado com origem, instante e identidade verificáveis pode entrar em cálculo.
7. Não retirar **Neon** (contas/carteiras/histórico) nem **Render** (backend) por conta dessas mudanças; fontes de investimento e hospedagem são funções diferentes.

### Restrição importante da B3

A [página de cotações históricas da B3](https://www.b3.com.br/) informa que a série COTAHIST é **não ajustada por inflação e proventos** e impõe restrições à coleta automatizada. O projeto dispõe de parser offline e auditor com arquivos obtidos pelo usuário de modo permitido, sem crawling ou download automatizado por esta função.

### Fontes oficiais públicas identificadas

- CVM FII Informe Mensal Estruturado: https://dados.cvm.gov.br/dataset/fii-doc-inf_mensal
- Catálogo de Dados Abertos CVM: https://dados.cvm.gov.br/dataset/
- Tesouro Transparente: https://www.tesourotransparente.gov.br/temas/divida-publica-federal/estatisticas-e-relatorios-da-divida-publica-federal

## Próximas etapas

1. Adicionar acompanhamento futuro dos registros imutáveis por novas cotações e proventos verificados e cálculo de desempenho subsequente **sem reescrever a recomendação histórica**.
2. Adicionar identificação explícita de commit/build do algoritmo e prova de data de divulgação de dados financeiros para backtest rigoroso.
3. Ampliar catalogação e ingestão autorizada de fontes oficiais (FII, CVM DFP/ITR, Tesouro, macro, exterior), sem fingir dados ausentes.
4. Avaliar necessidade de normalização de unidades e comparação entre setores, preservando regras de elegibilidade e custo zero fixo como objetivo.
