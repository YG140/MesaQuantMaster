# Mesa Quant Master Web

Frontend React + TypeScript oficial da Mesa Quant Master a partir desta versao.

## Instalar

```powershell
npm install
```

## Rodar localmente

```powershell
npm run dev
```

Configure `VITE_API_BASE_URL` em um `.env` local se o backend nao estiver em
`http://127.0.0.1:8000`.

Nao configure chave da BRAPI no frontend. A credencial pertence somente ao
`.env` do backend.

## Mercado

As telas consomem apenas endpoints internos do FastAPI. Pesquisa, perfil,
cotacao unica e cotacoes em lote saem do backend para a brapi.dev. A tela de
novo investimento separa "Ultima cotacao disponivel" de "Preco de compra"; o
preco de compra nunca e preenchido sem acao explicita do usuario.

Carteira e Inicio exibem status de mercado: atualizado, parcial ou
indisponivel. O botao "Atualizar cotacoes" invalida o cache do frontend e
solicita novamente os endpoints internos, respeitando o cache temporario do
backend.

## Scripts

- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`
- `npm run test:e2e`
- `npm run api:types`

## Coexistencia com Streamlit

O diretorio `frontend/` continua preservado e congelado como prototipo
temporario. Novas funcionalidades devem evoluir em `frontend_web/` sem importar
codigo Python e sem replicar regras financeiras.

A remocao do Streamlit ocorrera somente apos confirmacao de paridade funcional.
