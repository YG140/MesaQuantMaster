# Agente de IA V1

O endpoint autenticado `POST /ai-agent/chat` fornece uma camada conversacional
sobre os cálculos e dados produzidos pelo MesaQuantMaster. O LLM interpreta; os
services e engines existentes continuam responsáveis por dados e cálculos.

## Privacidade e transmissão ao provedor

Ao enviar uma pergunta ao Agente de IA, a mensagem e os dados financeiros
estritamente necessários para respondê-la podem ser transmitidos à OpenAI. Isso
pode incluir carteira, política de investimento, indicadores, cotações, valuation,
risco e resultados dos motores, conforme as ferramentas selecionadas para a pergunta.

O backend não envia senhas, JWTs, tokens, e-mail, chaves de API ou dados de outros
usuários. Identificadores internos desnecessários são removidos dos payloads. A
identidade vem exclusivamente de `current_user`; nenhuma ferramenta aceita
`user_id`. Mensagens, prompts e payloads financeiros completos não são registrados
nos logs.

Todas as ferramentas da V1 são somente leitura. O agente não compra, vende,
registra operações nem altera carteira ou política.

## Configuração

- `AI_AGENT_ENABLED=false` mantém o recurso desativado por padrão.
- `OPENAI_API_KEY` existe somente no ambiente do backend.
- `OPENAI_MODEL` permite trocar o modelo sem alteração de código.
- Os limites de timeout, mensagem, iterações e tool calls são configuráveis por
  variáveis `AI_AGENT_*`, incluindo o limite máximo de tokens da resposta.

Quando desativado ou não configurado, apenas o endpoint do agente responde `503`;
os demais recursos do MesaQuantMaster continuam independentes.
