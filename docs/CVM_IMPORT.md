# Importação CVM DFP e ITR

## Fonte e periodicidade

O importador usa exclusivamente os Dados Abertos oficiais da CVM:

- `https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp`
- `https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr`

Os conjuntos são atualizados semanalmente e podem conter reapresentações. DFP é
anual; ITR contém informações intermediárias que, em DRE, DFC e DVA, podem ser
acumuladas desde o início do exercício.

## Estrutura observada

Os ZIPs anuais contêm CSVs separados por demonstração e escopo. O importador
suporta BPA, BPP, DRE, DFC pelo método direto ou indireto e DVA. Arquivos `_con_`
são consolidados e `_ind_` são individuais. Os CSVs oficiais usam delimitador
`;`, encoding Windows-1252 e campos como `CNPJ_CIA`, `CD_CVM`, `VERSAO`,
`ORDEM_EXERC`, `CD_CONTA`, `VL_CONTA`, `MOEDA` e `ESCALA_MOEDA`.

Somente `ORDEM_EXERC=ÚLTIMO` é importada. A escala é aplicada com `Decimal`, mas
valor e escala originais também são preservados.

## Seleção e vínculo

- O documento consolidado é preferido ao individual.
- Dentro do mesmo escopo, prevalece a maior versão.
- A identidade inclui emissor, tipo, referência, versão, demonstração, escopo e
  fim do período, garantindo idempotência.
- Ativos só recebem dados CVM após vínculo explícito com um emissor por CNPJ e
  código CVM. Nenhum ticker é inferido pelo nome da companhia.

## Períodos

DFP é marcada como anual. ITR com início em janeiro é preservada como acumulada
no ano (`year_to_date`). Um trimestre isolado só pode ser calculado pela
diferença de dois acumulados compatíveis, para a mesma companhia, conta, escopo
e início de exercício. O método fica identificado como calculado.

## Cache e segurança

O cache padrão é `.cache/cvm/`, ignorado pelo Git. Downloads usam timeout,
limites comprimido e descompactado, ETag, Last-Modified e requisições
condicionais. ZIP inválido, path traversal e expansão acima do limite são
rejeitados. A leitura ocorre diretamente do ZIP, sem extração.

Configurações disponíveis:

- `CVM_CACHE_DIR`
- `CVM_TIMEOUT_SECONDS`
- `CVM_MAX_DOWNLOAD_BYTES`
- `CVM_MAX_UNCOMPRESSED_BYTES`
- `CVM_CACHE_TTL_HOURS`

## Sincronização

`POST /intelligence/cvm/sync` agenda uma tarefa local e exige superusuário. O
processamento não acontece em consultas comuns de inteligência. Como o projeto
ainda não possui fila distribuída, a tarefa em memória não sobrevive ao reinício
do servidor; produção deve migrar esse contrato para um worker confiável.

Status, documentos locais, emissores e vínculos estão disponíveis nas demais
rotas sob `/intelligence/cvm`.

## Limitações

- O mapeamento inicial usa somente códigos de contas fixas explicitamente
  cadastrados. Contas não fixas ou não mapeadas permanecem armazenadas sem virar
  indicador.
- O total de fluxo de investimentos não é apresentado como CAPEX.
- DVA é importada, mas ainda não gera indicadores principais.
- O importador não deduz emissor por semelhança textual e não inicia downloads
  durante análises comuns.
