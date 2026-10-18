# Reserva de emergência — planejamento separado da carteira

## O que foi implementado

Nova aba **Planejar → Reserva** no web/app responsivo, disponível no computador e em clientes Android que usam a interface web atualizada. Prévia personalizada por Perfil do Investidor, sem mexer em operações, patrimônio, carteira ou contas da Neon.

Entrada mínima: (1) despesas essenciais mensais reais; (2) quanto já foi **efetivamente separado** na reserva; (3) quanto pretende guardar por mês; (4) renda estável/variável. Sem deduzir valores de renda por faixa ou do patrimônio investido.

O motor `EmergencyReserveEngine` utiliza meta em meses da política confirmada do usuário quando disponível, ou referência inicial explícita de 6 meses se não houver perfil. Acrescenta 3 meses para renda variável/sazonal e 1 mês quando há dependentes, limitado a 18 meses; é uma regra prudencial de simulação, não uma determinação regulatória. Metas e duração são aproximadas sem rendimentos, para não inventar taxas futuras.

Resultado: meta em reais, meses cobertos, lacuna, progresso, tempo aproximado com aportes constantes, próximo aporte sugerido para reserva, valor restante após a contribuição, e proposta de duas reservas-alvo: acesso imediato (1 ou 2 meses) e complementar (restante) em opções de liquidez verificável.

**Não** identifica investimentos específicos sem informações de liquidez, risco e cobertura. Conta remunerada, CDB e Tesouro Selic têm garantias, risco, tributação e disponibilidade distintos; resgate imediato precisa ser confirmado, e Tesouro Selic não é instantâneo em todas as condições. Poupança, Tesouro ou CDB não são tratados como posições automaticamente registradas.

## Precauções

- Endpoint `POST /intelligence/emergency-reserve/plan` usa autenticação e **não grava** valores pessoais, operações nem orçamento no banco.
- Os recursos já investidos (ações, FIIs, ETF, criptomoedas etc.) não são presumidos como reserva.
- Dívidas relevantes no perfil geram aviso, e a "sobra" calculada não constitui liberação automática para investimentos arriscados.
- Se ainda não há aporte positivo, prazo retorna `null`, sem juros imaginários; se há sobra após cobrir a meta, ela aparece separada e não é aplicada automaticamente.
- Sem alterações de esquema, importação de carteira, ordens, câmbio ou políticas existentes.
- Dados da prévia só permanecem enquanto a aba está aberta (não há cadastro permanente de saldo de reserva nesta etapa).

**Próximas evoluções possíveis**: registro opt-in de saldos de reserva por usuário e conciliação automática apenas quando existir confirmação da instituição financeira, sem duplicar patrimônio já lançado; validação de liquidez e FGC individualizada antes de nomear produtos.

## Testes
Regressões de cálculo, liquidez, renda sazonal, dependentes, dívida, zero aporte, meta completa, limites numéricos, permissão por usuário e ausência de gravação na carteira. A interface usa os componentes e endpoints já existentes.
