# Auditoria automática antes de novos aportes — sem complicar a carteira

## Escopo e objetivo

Integrada **somente** ao endpoint existente `POST /intelligence/build-portfolio`. Nenhuma tela nova, botão, tabela, alteração de configuração de conta, migração ou mudança nas operações da carteira. A leitura e manutenção das posições existentes continuam intactas, mesmo que um ativo deixe de ser recomendado para **um novo aporte**.

## Regras efetivamente executadas nesta PR

A classe `PrePurchaseAuditService` confere, para cada candidato recebido do analisador:

1. Indicadores de identidade com anomalias críticas explícitas `identifier_unresolved`, `issuer_identity_unresolved` ou `conflicting_sources`: suspendem **somente a nova seleção**;
2. Cotação cujo campo de data real `market_updated_at` seja mais de 5 minutos futuro, mais de 7 dias antigo para ativos negociados em bolsa, ou mais de 48h para criptomoedas: suspende **somente o novo aporte**. Cotação sem data não recebe uma data inventada e continua sujeita às proteções de confiança anteriores;
3. Para ação brasileira com CNPJ vinculado à CVM, se houver indicador monetário comparável `assets` ou `equity` com `reference_date`, compara contra o documento oficial já importado com **mesmo indicador, mesmo período, mesma moeda BRL, escopo consolidado**. Divergência acima de 1% ou R$ 1 (maior limiar) impede a seleção daquele papel para um novo aporte;
4. Quando o indicador afirmar ser oficial CVM e incluir CNPJ, o CNPJ da proveniência precisa concordar com o emissor oficial vinculado ao ativo. Divergência confirmada impede novo aporte.

Regras deliberadas para evitar travamentos e alarmes falsos:

- **Não baixar** bases CVM enormes para cada montagem: apenas leitura rápida do banco já sincronizado;
- **Não consultar SEC** por nome/ticker adivinhado: atualmente CIK exato não fica cadastrado permanentemente nos ativos. A API de verificação manual da PR #85 segue funcional, e o valor `SEC_USER_AGENT` continua necessário apenas nela;
- **Não comparar** dois períodos diferentes, moedas diferentes, capitalização/saldo com receita, nem contas repetidas cujos conceitos não possam ser conciliados;
- Falta de documento/CNPJ, erro temporário de consulta, indicador não comparável e ausência de proveniência não são prova de conflito e **não podem bloquear toda a carteira**;
- Fonte indisponível não transforma dados em `confidence=HIGH`; permanecem as regras de qualidade preexistentes;
- Ativo excluído não é removido da carteira nem é vendido. O mecanismo existente de alocação pode escolher outro elegível ou informar valor não alocado;
- Mantém limites por classe, emissor, setor, perfil, orçamento, necessidades financeiras, lotes e saldo não alocado.

## Garantias e limitações

Auditoria de dados **não significa** que a recomendação é lucrativa ou que cotações são oficialmente certificadas; demonstra apenas algumas consistências comprováveis. Informações contábeis de períodos diferentes não geram conflitos aparentes. A falta de CIK persistido impede consulta à SEC em massa, evitando latência e falsos correspondentes de empresas internacionais.

Nenhum dado real do usuário nem Neon de produção é alterado pelo código da auditoria. A implantação do backend é automática quando `main` é atualizado no Render; testar antes de integrar.

## Testes

- Caso de CVM: confronto com o mesmo período, com datas diferentes, divergência de CNPJ, fonte indisponível, moeda e bolsa incompatíveis.
- Caso de preços: dia antigo, data futura, data ausente e feriados.
- Caso de carteira: ativo auditado excluído da nova compra, posição existente continua visível; candidato alternativo ocupa seu lugar.
- Contrato antigo de `BuildPortfolioResponse` permanece igual para o frontend e APK.

*Próxima etapa opcional*: CIK oficial persistido/verificado para integração internacional ponto a ponto, sem obrigar todos a usar API adicional.
