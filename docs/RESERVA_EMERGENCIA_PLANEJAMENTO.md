# Reserva de emergência — planejamento separado da carteira

## O que foi implementado

Nova aba **Planejar → Reserva** no web/app responsivo, disponível no computador e em clientes Android que usam a interface web atualizada. Prévia personalizada por Perfil do Investidor, sem mexer em operações, patrimônio, carteira ou contas da Neon.

Entrada da tela **Planejar → Reserva**: (1) despesas essenciais mensais reais; (2) quanto pretende guardar por mês; (3) renda estável/variável. Para esta simulação, a reserva inicial é **sempre R$ 0**, sem perguntar quanto o usuário já guardou. A API continua aceitando o campo `current_reserve` para compatibilidade, mas a interface envia `0` explicitamente. Sem deduzir saldo do patrimônio investido ou de faixas de renda.

O motor `EmergencyReserveEngine` utiliza meta em meses da política confirmada do usuário quando disponível, ou referência inicial explícita de 6 meses se não houver perfil. Acrescenta 3 meses para renda variável/sazonal e 1 mês quando há dependentes, limitado a 18 meses; é uma regra prudencial de simulação, não uma determinação regulatória. Metas e duração são aproximadas sem rendimentos, para não inventar taxas futuras.

Resultado: meta em reais, lacuna integral a partir de R$ 0, progresso inicial de 0%, tempo aproximado com aportes constantes, próximo aporte sugerido para reserva, valor restante após a contribuição, e proposta de duas reservas-alvo: acesso imediato (1 ou 2 meses) e complementar (restante) em opções de liquidez verificável. O cartão de saldo já guardado foi retirado da interface.

**Não** identifica investimentos específicos sem informações de liquidez, risco e cobertura. Conta remunerada, CDB e Tesouro Selic têm garantias, risco, tributação e disponibilidade distintos; resgate imediato precisa ser confirmado, e Tesouro Selic não é instantâneo em todas as condições. Poupança, Tesouro ou CDB não são tratados como posições automaticamente registradas.

## Precauções

- Endpoint `POST /intelligence/emergency-reserve/plan` usa autenticação e **não grava** valores pessoais, operações nem orçamento no banco.
- Os recursos já investidos (ações, FIIs, ETF, criptomoedas etc.) não são presumidos como reserva.
- Dívidas relevantes no perfil geram aviso, e a "sobra" calculada não constitui liberação automática para investimentos arriscados.
- Se ainda não há aporte positivo, prazo retorna `null`, sem juros imaginários; se há sobra após cobrir a meta, ela aparece separada e não é aplicada automaticamente.
- Sem alterações de esquema, importação de carteira, ordens, câmbio ou políticas existentes.
- Dados da prévia só permanecem enquanto a aba está aberta (não há cadastro permanente de saldo de reserva nesta etapa). Assumir zero no planejador não exclui aplicações nem saldos existentes da carteira.

**Próximas evoluções possíveis**: registro opt-in de saldos de reserva por usuário e conciliação automática apenas quando existir confirmação da instituição financeira, sem duplicar patrimônio já lançado; validação de liquidez e FGC individualizada antes de nomear produtos.

## Testes
Regressões de cálculo, liquidez, renda sazonal, dependentes, dívida, zero aporte, meta completa, limites numéricos, permissão por usuário e ausência de gravação na carteira. A interface usa os componentes e endpoints já existentes.


## Plano por instrumento (interface)

A tela exibe o próximo aporte e a meta para duas categorias de instrumentos: primeiro uma parcela de acesso imediato (exemplo: CDB de resgate imediato com condições verificadas; caso não seja efetivamente acessível, manter saldo disponível em conta), depois Tesouro Selic para a parcela complementar. O backend calcula esses valores a partir das despesas, meses do perfil, renda instável, saldo inicial e aporte mensal. Na interface o saldo inicial continua **R$ 0**. A soma das metas por tipo de ativo é igual à reserva-alvo e a soma das parcelas do próximo aporte é igual à contribuição sugerida à reserva. Não há consulta ou validação de emissor, vencimento, título ofertado ou preço do dia: esta etapa **não informa ticker, quantidade negociável nem ordem de compra**. Condições de resgate, tributação e risco devem ser verificadas antes da aplicação.

Os dois blocos explicativos anteriores à montagem foram retirados; a interface prioriza formulário, resultado, valores por instrumento e advertências pontuais.
