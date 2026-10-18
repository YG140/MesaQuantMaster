# Preço de entrada: comparação setorial prudente e auditável

## O que melhora
Este ajuste aprimora o mecanismo já existente de avaliação relativa de **ações** e, para fins analíticos, ativos internacionais na mesma moeda. A API, o APK, as telas, operações, usuários, posições e banco Neon **não recebem novos campos ou migrações**.

Antes, a mediana setorial de P/L podia usar três emissores e a mediana de P/VP outros três, mesmo sem três emissores com **ambos** os múltiplos. Agora a faixa só é calculada com:
- Três emissores distintos, de mesma classe, setor/segmento e **mesma moeda**;
- Cada par integrante da amostra tem **P/L e P/VP válidos simultaneamente**, observados com no máximo 90 dias de distância e com **cotação recente**;
- LPA/VPA do ativo positivo e com referências dentro de 120 dias um do outro;
- Concordância entre os dois métodos de referência (diferença de até 50%); se ultrapassar, a aplicação **se abstém**;
- Margem relativa mínima de 20% e avaliação fundamentada para que o filtro de novas compras permita considerar a ação. Não há preço intrínseco garantido ou promessa de ganho.

Se a amostra de pares encolher entre etapas/lotes, **revoga** a faixa, os antigos rótulos de comparação e os bônus setoriais anteriores em vez de manter uma aparente oportunidade. Não atribui bônus de valuation quando a própria faixa é insuficiente.

## O que NÃO muda
- A carteira atual permanece como está; nenhum ativo é vendido/removido.
- A auditoria de fontes CVM/SEC anterior e o controle de identidade/idade do preço continuam existentes.
- A seleção pode optar por não recomendar compras e deixar saldo livre se não houver evidência; isso não impede visualizar, adicionar ou acompanhar ativos que a pessoa já possui.
- Sem expansão de APIs pagas, scraping ou contatos de mercado novos. Continuam provedores gratuitos configurados.

## Limites e por que não chamar isso de "preço justo"
Uma comparação por múltiplos depende do universo analisado e do contexto macro; três empresas não representam todo o setor e o mercado pode precificar sistematicamente errado. A faixa é **referência relativa para triagem**, não valuation DCF, conclusão de compra, certeza de rentabilidade nem preço-alvo. Ganho real precisa ser medido posteriormente, incluindo dividendos, custos e risco.

## Testes
Inclui regressões específicas para múltiplos em grupos disjuntos, pares sem cotação atual, datas incompatíveis, pares incompletos, reavaliação após perda de pares, falsos sinais "baratos" previamente presentes e preservação das regras legadas.
